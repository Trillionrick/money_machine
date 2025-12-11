"""BSC Flash Loan Executor for AQUA arbitrage.

Modern 2025 implementation using PancakeSwap V3 flash swaps.
Integrates with AQUABSCArbitrage.sol contract for automated execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog
from eth_typing import ChecksumAddress
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from web3 import Web3
from web3.contract import Contract
from web3.types import TxParams, TxReceipt, Wei

from src.ai.alert_system import get_alert_system
from src.ai.circuit_breakers import get_circuit_breaker_manager
from src.ai.production_safety import get_production_safety_guard
from src.ai.transaction_logger import TradeDecision, TradeExecution, get_transaction_logger

log = structlog.get_logger()


class BSCFlashLoanSettings(BaseSettings):
    """Configuration for BSC flash loan arbitrage."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Contract addresses
    bsc_aqua_contract: str | None = Field(default=None, alias="BSC_AQUA_CONTRACT")

    # Token addresses
    wbnb_address: str = Field(
        default="0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        alias="WBNB_ADDRESS",
    )
    aqua_address: str = Field(
        default="0x72B7D61E8fC8cF971960DD9cfA59B8C829D91991",
        alias="AQUA_ADDRESS",
    )

    # DEX addresses
    pancake_v3_pool_aqua_wbnb: str | None = Field(
        default=None,
        alias="PANCAKE_V3_POOL_AQUA_WBNB",
    )

    # Web3 connection
    bsc_rpc_url: str = Field(
        default="https://bsc-dataseed1.binance.org:443",
        alias="BSC_RPC_URL",
    )
    bsc_private_key: str | None = Field(default=None, alias="BSC_PRIVATE_KEY")

    # Gas settings (BSC is much cheaper than Ethereum)
    max_gas_price_gwei: int = Field(default=5, alias="BSC_MAX_GAS_PRICE_GWEI")
    gas_estimate: int = Field(default=250000, alias="BSC_GAS_ESTIMATE")

    # Arbitrage parameters
    min_profit_threshold_bnb: float = Field(default=0.05, alias="MIN_PROFIT_THRESHOLD_BNB")
    slippage_tolerance_bps: int = Field(default=100, alias="SLIPPAGE_TOLERANCE_BPS")  # 1%

    @field_validator("bsc_rpc_url", "bsc_private_key", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Strip whitespace from strings."""
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "BSCFlashLoanSettings":
        """Ensure required environment variables are set."""
        if not self.bsc_aqua_contract:
            log.warning("BSC_AQUA_CONTRACT not set - contract must be deployed first")
        if not self.bsc_rpc_url:
            raise ValueError("BSC_RPC_URL must be set in environment or .env file")
        if not self.bsc_private_key:
            raise ValueError("BSC_PRIVATE_KEY must be set in environment or .env file")
        return self


@dataclass
class ArbOpportunity:
    """AQUA arbitrage opportunity."""

    borrow_amount_bnb: Decimal
    expected_profit_bnb: Decimal
    buy_on_pancake: bool  # True = buy AQUA on Pancake, sell on Biswap
    min_profit_bnb: Decimal
    gas_estimate: int


class BSCFlashLoanExecutor:
    """Execute AQUA arbitrage using BSC flash loans."""

    # AQUABSCArbitrage contract ABI (minimal - only what we need)
    CONTRACT_ABI = [
        {
            "inputs": [
                {"internalType": "uint256", "name": "borrowAmount", "type": "uint256"},
                {"internalType": "bool", "name": "buyOnPancake", "type": "bool"},
            ],
            "name": "executeAQUAArbitrage",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "borrowAmount", "type": "uint256"},
                {"internalType": "bool", "name": "buyOnPancake", "type": "bool"},
            ],
            "name": "simulateArbitrage",
            "outputs": [
                {"internalType": "uint256", "name": "estimatedProfit", "type": "uint256"},
                {"internalType": "uint256", "name": "estimatedAquaReceived", "type": "uint256"},
                {"internalType": "bool", "name": "isProfitable", "type": "bool"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "getStats",
            "outputs": [
                {"internalType": "uint256", "name": "_totalArbitrages", "type": "uint256"},
                {"internalType": "uint256", "name": "_totalProfit", "type": "uint256"},
                {"internalType": "uint256", "name": "_failedAttempts", "type": "uint256"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "address", "name": "_aquaWbnbPoolPancake", "type": "address"},
                {"internalType": "address", "name": "_aquaWbnbPoolBiswap", "type": "address"},
            ],
            "name": "configurePools",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "inputs": [{"internalType": "uint256", "name": "_minProfitBPS", "type": "uint256"}],
            "name": "setMinProfitBPS",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
    ]

    def __init__(
        self,
        settings: BSCFlashLoanSettings | None = None,
        w3: Web3 | None = None,
    ):
        """Initialize BSC flash loan executor."""
        self.settings = settings or BSCFlashLoanSettings()

        if not self.settings.bsc_rpc_url or not self.settings.bsc_private_key:
            raise ValueError("BSC_RPC_URL and BSC_PRIVATE_KEY are required")

        if w3 is None:
            self.w3 = Web3(Web3.HTTPProvider(self.settings.bsc_rpc_url))
        else:
            self.w3 = w3

        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to BSC at {self.settings.bsc_rpc_url}")

        self.account = self.w3.eth.account.from_key(self.settings.bsc_private_key)

        # Initialize contract if address is set
        self.contract: Contract | None = None
        if self.settings.bsc_aqua_contract:
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.settings.bsc_aqua_contract),
                abi=self.CONTRACT_ABI,
            )

        # Production safety systems
        self.safety_guard = get_production_safety_guard()
        self.tx_logger = get_transaction_logger()
        self.alert_system = get_alert_system()
        self.circuit_breakers = get_circuit_breaker_manager()

        log.info(
            "bsc_flash.initialized",
            contract=self.settings.bsc_aqua_contract,
            account=self.account.address,
            chain_id=self.w3.eth.chain_id,
        )

    def execute_arbitrage(
        self,
        borrow_amount_bnb: float,
        buy_on_pancake: bool = True,
        dry_run: bool = True,
    ) -> TxReceipt | None:
        """Execute AQUA arbitrage.

        Args:
            borrow_amount_bnb: Amount of BNB to borrow
            buy_on_pancake: True = buy AQUA on Pancake, sell on Biswap
            dry_run: If True, only simulate (don't send tx)

        Returns:
            Transaction receipt if executed, None if dry run or failed
        """
        if not self.contract:
            log.error("bsc_flash.contract_not_configured")
            return None

        # 1. CHECK CIRCUIT BREAKERS
        allowed, breaker_reason = self.circuit_breakers.is_trading_allowed()
        if not allowed:
            log.warning("bsc_flash.circuit_breaker_blocked", reason=breaker_reason)
            self.alert_system.send_circuit_breaker_triggered(
                breaker_type="trading",
                reason=breaker_reason or "unspecified",
                value=0.0,
                threshold=0.0,
            )
            return None

        borrow_amount = Web3.to_wei(borrow_amount_bnb, "ether")

        # 2. SIMULATE PROFITABILITY (if contract supports it)
        try:
            result = self.contract.functions.simulateArbitrage(
                borrow_amount, buy_on_pancake
            ).call()
            estimated_profit, aqua_received, is_profitable = result

            log.info(
                "bsc_flash.simulation",
                borrow_bnb=borrow_amount_bnb,
                estimated_profit_bnb=Web3.from_wei(estimated_profit, "ether"),
                aqua_received=Web3.from_wei(aqua_received, "ether"),
                is_profitable=is_profitable,
            )

            if not is_profitable:
                log.warning("bsc_flash.not_profitable")
                return None

        except Exception:
            log.warning("bsc_flash.simulation_failed", msg="Proceeding without simulation")

        # 3. CHECK GAS PRICE
        current_gas_price = self.w3.eth.gas_price
        max_gas_price = Web3.to_wei(self.settings.max_gas_price_gwei, "gwei")

        if current_gas_price > max_gas_price:
            log.warning(
                "bsc_flash.gas_too_high",
                current_gwei=Web3.from_wei(current_gas_price, "gwei"),
                max_gwei=self.settings.max_gas_price_gwei,
            )
            return None

        # 4. PRODUCTION SAFETY VALIDATION
        estimated_profit_bnb = 0.0  # Would get from simulation
        gas_cost_bnb = float(
            Web3.from_wei(current_gas_price * self.settings.gas_estimate, "ether")
        )
        current_gas_price_gwei = float(Web3.from_wei(current_gas_price, "gwei"))

        validated, safety_reason = self.safety_guard.validate_trade(
            position_size_eth=borrow_amount_bnb,
            expected_profit_eth=estimated_profit_bnb,
            estimated_gas_cost_eth=gas_cost_bnb,
            estimated_gas_price_gwei=current_gas_price_gwei,
            pool_liquidity_eth=100.0,  # Would query actual pool liquidity
            expected_slippage_bps=self.settings.slippage_tolerance_bps / 100.0,
            trade_type="bsc_flash_loan",
        )

        if not validated:
            log.warning("bsc_flash.safety_rejected", reason=safety_reason)
            return None

        # 5. LOG DECISION
        from datetime import datetime

        trade_decision = TradeDecision(
            timestamp=datetime.utcnow().isoformat(),
            opportunity_id=f"aqua_arb_{borrow_amount_bnb}",
            trade_type="bsc_flash_loan",
            symbol="AQUA/BNB",
            action="EXECUTE",
            ai_confidence=0.8,
            expected_profit_eth=estimated_profit_bnb,
            expected_profit_usd=estimated_profit_bnb * 600,  # Est. BNB price
            edge_bps=50.0,  # Would calculate from actual spread
            kelly_fraction=0.25,
            position_size_eth=borrow_amount_bnb,
            estimated_gas_cost_eth=gas_cost_bnb,
            estimated_slippage_bps=self.settings.slippage_tolerance_bps / 100.0,
            max_potential_loss_eth=gas_cost_bnb * 2,
            pool_liquidity_eth=100.0,
            gas_price_gwei=current_gas_price_gwei,
            approved=True,
        )
        decision_id = self.tx_logger.log_decision(trade_decision)

        if dry_run:
            log.info(
                "bsc_flash.dry_run",
                borrow_amount_bnb=borrow_amount_bnb,
                buy_on_pancake=buy_on_pancake,
            )
            return None

        # 6. EXECUTE TRANSACTION
        tx_params: TxParams = {
            "from": self.account.address,
            "gas": self.settings.gas_estimate,
            "gasPrice": current_gas_price,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
        }

        try:
            # Build transaction
            tx = self.contract.functions.executeAQUAArbitrage(
                borrow_amount, buy_on_pancake
            ).build_transaction(tx_params)

            # Sign and send
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            log.info("bsc_flash.tx_submitted", tx_hash=tx_hash.hex())

            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

            log.info(
                "bsc_flash.tx_confirmed",
                tx_hash=tx_hash.hex(),
                status=receipt["status"],
                gas_used=receipt["gasUsed"],
            )

            # 7. LOG EXECUTION RESULT
            success = receipt["status"] == 1
            gas_used = receipt.get("gasUsed", 0)
            effective_gas_price = receipt.get("effectiveGasPrice", current_gas_price)
            actual_gas_cost_bnb = float(Web3.from_wei(gas_used * effective_gas_price, "ether"))

            # Estimate actual profit (would parse from event logs)
            actual_profit_bnb = estimated_profit_bnb - actual_gas_cost_bnb if success else 0.0

            trade_execution = TradeExecution(
                decision_id=decision_id,
                timestamp=datetime.utcnow().isoformat(),
                tx_hash=tx_hash.hex(),
                block_number=receipt.get("blockNumber", 0),
                executed=success,
                actual_profit_eth=actual_profit_bnb,
                actual_profit_usd=actual_profit_bnb * 600,
                actual_gas_cost_eth=actual_gas_cost_bnb,
                actual_gas_price_gwei=float(Web3.from_wei(effective_gas_price, "gwei")),
                actual_slippage_bps=self.settings.slippage_tolerance_bps / 100.0,
            )
            self.tx_logger.log_execution(decision_id, trade_execution)

            # 8. RECORD IN CIRCUIT BREAKERS
            self.circuit_breakers.record_trade(
                success=success,
                profit=actual_profit_bnb,
                gas_cost=actual_gas_cost_bnb,
                slippage_bps=self.settings.slippage_tolerance_bps / 100.0,
                expected_slippage_bps=self.settings.slippage_tolerance_bps / 100.0,
                symbol="AQUA/BNB",
            )

            # 9. UPDATE SAFETY GUARD
            pnl_bnb = actual_profit_bnb if success else -actual_gas_cost_bnb
            self.safety_guard.record_trade_result(
                pnl_eth=pnl_bnb,
                gas_cost_eth=actual_gas_cost_bnb,
            )

            # 10. SEND ALERTS
            if success and actual_profit_bnb > 0.01:
                self.alert_system.send_trade_executed(
                    symbol="AQUA/BNB",
                    profit_eth=actual_profit_bnb,
                    profit_usd=actual_profit_bnb * 600,
                    confidence=0.8,
                    tx_hash=tx_hash.hex(),
                )
            elif not success:
                self.alert_system.send_trade_failed(
                    symbol="AQUA/BNB",
                    loss_eth=actual_gas_cost_bnb,
                    loss_usd=actual_gas_cost_bnb * 600,
                    reason="Flash loan execution failed",
                )

            return receipt

        except Exception as e:
            log.exception("bsc_flash.execution_failed")

            # Log failed execution
            trade_execution = TradeExecution(
                decision_id=decision_id,
                timestamp=datetime.utcnow().isoformat(),
                tx_hash="",
                block_number=0,
                executed=False,
                actual_profit_eth=0.0,
                actual_profit_usd=0.0,
                actual_gas_cost_eth=0.0,
                actual_gas_price_gwei=current_gas_price_gwei,
                actual_slippage_bps=0.0,
            )
            self.tx_logger.log_execution(decision_id, trade_execution)

            self.alert_system.send_trade_failed(
                symbol="AQUA/BNB",
                loss_eth=0.0,
                loss_usd=0.0,
                reason=f"Execution error: {str(e)}",
            )

            raise

    def get_contract_stats(self) -> dict[str, int]:
        """Get statistics from the arbitrage contract."""
        if not self.contract:
            return {"total_arbitrages": 0, "total_profit": 0, "failed_attempts": 0}

        try:
            stats = self.contract.functions.getStats().call()
            return {
                "total_arbitrages": stats[0],
                "total_profit": stats[1],
                "failed_attempts": stats[2],
            }
        except Exception:
            log.exception("bsc_flash.stats_fetch_failed")
            return {"total_arbitrages": 0, "total_profit": 0, "failed_attempts": 0}
