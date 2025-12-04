"""Flash loan arbitrage executor using the EnhancedHighSpeedArbRunner contract.

This module provides Python integration with the Solidity flash loan contract,
enabling seamless arbitrage execution from the existing arbitrage_runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

import structlog
from eth_typing import ChecksumAddress, HexStr
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from web3 import Web3
from web3.contract import Contract
from web3.types import TxParams, TxReceipt, Wei

log = structlog.get_logger()


class FlashLoanSettings(BaseSettings):
    """Configuration for flash loan arbitrage contract."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Contract addresses
    arb_contract_address: Optional[str] = Field(default=None, alias="ARB_CONTRACT_ADDRESS")
    aave_pool_address: str = Field(
        default="0x87870Bca3f5FD6335c3f4d4C530Eed06fb5de523",  # Mainnet Aave V3
        alias="AAVE_POOL_ADDRESS",
    )
    uni_v3_router: str = Field(
        default="0xE592427A0AEce92De3Edee1F18E0157C05861564",  # Mainnet Uniswap V3
        alias="UNI_V3_ROUTER",
    )
    weth_address: str = Field(
        default="0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # Mainnet WETH
        alias="WETH_ADDRESS",
    )
    usdc_address: str = Field(
        default="0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # Mainnet USDC
        alias="USDC_ADDRESS",
    )

    # Web3 connection
    eth_rpc_url: Optional[str] = Field(default=None, alias="ETH_RPC_URL")
    private_key: Optional[str] = Field(default=None, alias="PRIVATE_KEY")

    # Gas settings
    max_gas_price_gwei: int = Field(default=100, alias="MAX_GAS_PRICE_GWEI")
    gas_estimate: int = Field(default=350000, alias="GAS_ESTIMATE")

    # Arbitrage parameters
    min_profit_threshold_eth: float = Field(default=0.5, alias="MIN_PROFIT_THRESHOLD_ETH")
    slippage_tolerance_bps: int = Field(default=50, alias="SLIPPAGE_TOLERANCE_BPS")  # 0.5%

    @field_validator("eth_rpc_url", "private_key", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Strip whitespace and control characters from sensitive strings."""
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "FlashLoanSettings":
        """Ensure that required environment variables are set."""
        if not self.arb_contract_address:
            raise ValueError("ARB_CONTRACT_ADDRESS must be set in environment or .env file")
        if not self.eth_rpc_url:
            raise ValueError("ETH_RPC_URL must be set in environment or .env file")
        if not self.private_key:
            raise ValueError("PRIVATE_KEY must be set in environment or .env file")
        return self


@dataclass
class ArbPlan:
    """Arbitrage execution plan matching the Solidity struct."""

    router_address: ChecksumAddress
    swap_data: bytes
    final_token: ChecksumAddress
    min_profit: Wei
    expected_profit: Wei
    gas_estimate: int


@dataclass
class ProfitabilityCheck:
    """Profitability analysis results."""

    gross_profit: Wei
    flash_loan_fee: Wei
    gas_cost: Wei
    slippage_cost: Wei
    net_profit: Wei
    is_profitable: bool
    roi_bps: int
    break_even_bps: int


class FlashLoanExecutor:
    """Execute flash loan arbitrage using the EnhancedHighSpeedArbRunner contract."""

    # Contract ABI (minimal - only what we need)
    CONTRACT_ABI = [
        {
            "inputs": [
                {"internalType": "address", "name": "loanAsset", "type": "address"},
                {"internalType": "uint256", "name": "loanAmount", "type": "uint256"},
                {"internalType": "bytes", "name": "arbData", "type": "bytes"},
            ],
            "name": "requestFlashLoan",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "address", "name": "pairAddress1", "type": "address"},
                {"internalType": "address", "name": "pairAddress2", "type": "address"},
                {"internalType": "uint256", "name": "borrowAmount", "type": "uint256"},
                {"internalType": "bool", "name": "zeroForOne", "type": "bool"},
            ],
            "name": "simulateArbitrage",
            "outputs": [
                {"internalType": "uint256", "name": "expectedProfit", "type": "uint256"},
                {"internalType": "uint256", "name": "priceImpact1", "type": "uint256"},
                {"internalType": "uint256", "name": "priceImpact2", "type": "uint256"},
                {"internalType": "bool", "name": "isProfitable", "type": "bool"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "borrowAmount", "type": "uint256"},
                {"internalType": "uint256", "name": "expectedGrossProfit", "type": "uint256"},
                {"internalType": "uint256", "name": "gasEstimate", "type": "uint256"},
            ],
            "name": "calculateProfitability",
            "outputs": [
                {
                    "components": [
                        {"internalType": "uint256", "name": "grossProfit", "type": "uint256"},
                        {"internalType": "uint256", "name": "flashLoanFee", "type": "uint256"},
                        {"internalType": "uint256", "name": "gasCost", "type": "uint256"},
                        {"internalType": "uint256", "name": "slippageCost", "type": "uint256"},
                        {"internalType": "uint256", "name": "netProfit", "type": "uint256"},
                        {"internalType": "bool", "name": "isProfitable", "type": "bool"},
                    ],
                    "internalType": "struct EnhancedHighSpeedArbRunner.ProfitabilityCheck",
                    "name": "check",
                    "type": "tuple",
                }
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "borrowAmount", "type": "uint256"},
                {"internalType": "uint256", "name": "gasEstimate", "type": "uint256"},
            ],
            "name": "calculateBreakEvenSpread",
            "outputs": [{"internalType": "uint256", "name": "breakEvenBps", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
    ]

    # Uniswap V3 Router ABI (for encoding swaps)
    UNI_V3_ROUTER_ABI = [
        {
            "inputs": [
                {
                    "components": [
                        {"internalType": "bytes", "name": "path", "type": "bytes"},
                        {"internalType": "address", "name": "recipient", "type": "address"},
                        {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                        {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                        {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                    ],
                    "internalType": "struct ISwapRouter.ExactInputParams",
                    "name": "params",
                    "type": "tuple",
                }
            ],
            "name": "exactInput",
            "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
            "stateMutability": "payable",
            "type": "function",
        }
    ]

    def __init__(
        self,
        settings: Optional[FlashLoanSettings] = None,
        w3: Optional[Web3] = None,
    ):
        """Initialize the flash loan executor."""
        self.settings = settings or FlashLoanSettings()

        # The model validator ensures these are set, but this satisfies the linter
        if not self.settings.eth_rpc_url or not self.settings.private_key or not self.settings.arb_contract_address:
            raise ValueError(
                "Required settings (ETH_RPC_URL, PRIVATE_KEY, ARB_CONTRACT_ADDRESS) are missing."
            )

        if w3 is None:
            self.w3 = Web3(Web3.HTTPProvider(self.settings.eth_rpc_url))
        else:
            self.w3 = w3

        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to Ethereum node at {self.settings.eth_rpc_url}")

        self.account = self.w3.eth.account.from_key(self.settings.private_key)
        self.contract: Contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.settings.arb_contract_address),
            abi=self.CONTRACT_ABI,
        )

        self.uni_router: Contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.settings.uni_v3_router),
            abi=self.UNI_V3_ROUTER_ABI,
        )

        log.info(
            "flash_loan_executor.initialized",
            contract=self.settings.arb_contract_address,
            account=self.account.address,
        )

    def encode_swap_path(
        self,
        token_in: str,
        token_out: str,
        fee_tier: int = 3000,
        intermediate_token: Optional[str] = None,
    ) -> bytes:
        """Encode Uniswap V3 swap path.

        Args:
            token_in: Input token address
            token_out: Output token address
            fee_tier: Pool fee in basis points (500, 3000, or 10000)
            intermediate_token: Optional intermediate token for multi-hop

        Returns:
            Encoded path bytes
        """
        def _addr_bytes(addr: str) -> bytes:
            return Web3.to_bytes(hexstr=Web3.to_checksum_address(addr))

        fee_bytes = fee_tier.to_bytes(3, "big")
        token_in_bytes = _addr_bytes(token_in)
        token_out_bytes = _addr_bytes(token_out)

        if intermediate_token:
            # Multi-hop: token_in -> intermediate -> token_out
            path = (
                token_in_bytes
                + fee_bytes
                + _addr_bytes(intermediate_token)
                + fee_bytes
                + token_out_bytes
            )
        else:
            # Direct swap: token_in -> token_out
            path = (
                token_in_bytes
                + fee_bytes
                + token_out_bytes
            )

        return path

    def encode_swap_data(
        self,
        path: bytes,
        amount_in: Wei,
        min_amount_out: Wei,
        deadline_seconds: int = 1200,
    ) -> HexStr:
        """Encode Uniswap V3 exactInput swap data.

        Args:
            path: Encoded swap path
            amount_in: Input amount in wei
            min_amount_out: Minimum output amount (slippage protected)
            deadline_seconds: Seconds until deadline (default 20 minutes)

        Returns:
            Encoded function call data
        """
        latest_block = self.w3.eth.get_block("latest")
        timestamp = latest_block.get("timestamp")
        if timestamp is None:
            raise ValueError("Could not get timestamp from the latest block")
        deadline = timestamp + deadline_seconds

        # eth-abi requires tuple/list for struct params; dicts trigger a
        # TupleEncoder error, so pass an ordered tuple matching ExactInputParams.
        assert self.settings.arb_contract_address is not None
        swap_params = (
            path,
            Web3.to_checksum_address(self.settings.arb_contract_address),
            deadline,
            int(amount_in),
            int(min_amount_out),
        )

        # Encode the exactInput function call using web3.py v6+ API
        return self.uni_router.functions.exactInput(swap_params)._encode_transaction_data()

    def encode_arb_plan(self, plan: ArbPlan) -> bytes:
        """Encode ArbPlan struct for contract call.

        Args:
            plan: Arbitrage plan with swap details

        Returns:
            ABI-encoded bytes
        """
        return self.w3.codec.encode(
            ["(address,bytes,address,uint256,uint256,uint256)"],
            [
                (
                    plan.router_address,
                    plan.swap_data,
                    plan.final_token,
                    plan.min_profit,
                    plan.expected_profit,
                    plan.gas_estimate,
                )
            ],
        )

    def calculate_profitability(
        self,
        borrow_amount: Wei,
        expected_profit: Wei,
        gas_estimate: Optional[int] = None,
    ) -> ProfitabilityCheck:
        """Calculate profitability using the contract's view function.

        Args:
            borrow_amount: Amount to borrow in wei
            expected_profit: Expected gross profit in wei
            gas_estimate: Gas estimate (uses default if None)

        Returns:
            ProfitabilityCheck with detailed analysis
        """
        gas_est = gas_estimate or self.settings.gas_estimate

        try:
            result = self.contract.functions.calculateProfitability(
                borrow_amount, expected_profit, gas_est
            ).call()

            # Parse the tuple result
            gross_profit, flash_fee, gas_cost, slippage_cost, net_profit, is_profitable = result

            # Calculate additional metrics
            roi_bps = (net_profit * 10000) // borrow_amount if borrow_amount > 0 else 0
            break_even = self.contract.functions.calculateBreakEvenSpread(
                borrow_amount, gas_est
            ).call()

            return ProfitabilityCheck(
                gross_profit=Wei(gross_profit),
                flash_loan_fee=Wei(flash_fee),
                gas_cost=Wei(gas_cost),
                slippage_cost=Wei(slippage_cost),
                net_profit=Wei(net_profit),
                is_profitable=bool(is_profitable),
                roi_bps=int(roi_bps),
                break_even_bps=int(break_even),
            )
        except Exception:
            log.exception("flash_loan.profitability_check_failed")
            raise

    def simulate_arbitrage(
        self,
        pair_address_1: str,
        pair_address_2: str,
        borrow_amount: Wei,
        zero_for_one: bool = True,
    ) -> Dict[str, Any]:
        """Simulate arbitrage opportunity using on-chain data.

        Args:
            pair_address_1: First DEX pair address
            pair_address_2: Second DEX pair address
            borrow_amount: Amount to borrow
            zero_for_one: Swap direction

        Returns:
            Dict with simulation results
        """
        try:
            result = self.contract.functions.simulateArbitrage(
                Web3.to_checksum_address(pair_address_1),
                Web3.to_checksum_address(pair_address_2),
                borrow_amount,
                zero_for_one,
            ).call()

            expected_profit, price_impact_1, price_impact_2, is_profitable = result

            return {
                "expected_profit": expected_profit,
                "price_impact_1_bps": price_impact_1,
                "price_impact_2_bps": price_impact_2,
                "is_profitable": is_profitable,
                "net_profit_eth": Web3.from_wei(expected_profit, "ether"),
            }
        except Exception:
            log.exception("flash_loan.simulation_failed")
            raise

    def execute_flash_loan(
        self,
        loan_asset: str,
        loan_amount: Wei,
        arb_plan: ArbPlan,
        dry_run: bool = True,
    ) -> Optional[TxReceipt]:
        """Execute flash loan arbitrage.

        Args:
            loan_asset: Token to borrow (e.g., WETH)
            loan_amount: Amount to borrow in wei
            arb_plan: Arbitrage execution plan
            dry_run: If True, only simulate (don't send tx)

        Returns:
            Transaction receipt if executed, None if dry run
        """
        # Encode the arb plan
        arb_data = self.encode_arb_plan(arb_plan)

        # Check profitability first
        profitability = self.calculate_profitability(
            loan_amount, arb_plan.expected_profit, arb_plan.gas_estimate
        )

        log.info(
            "flash_loan.profitability_check",
            net_profit_eth=Web3.from_wei(profitability.net_profit, "ether"),
            roi_bps=profitability.roi_bps,
            is_profitable=profitability.is_profitable,
        )

        if not profitability.is_profitable:
            log.warning("flash_loan.not_profitable", check=profitability)
            return None

        # Check gas price
        current_gas_price = self.w3.eth.gas_price
        max_gas_price = Web3.to_wei(self.settings.max_gas_price_gwei, "gwei")

        if current_gas_price > max_gas_price:
            log.warning(
                "flash_loan.gas_too_high",
                current_gwei=Web3.from_wei(current_gas_price, "gwei"),
                max_gwei=self.settings.max_gas_price_gwei,
            )
            return None

        if dry_run:
            log.info("flash_loan.dry_run", loan_amount=loan_amount, expected_profit=arb_plan.expected_profit)
            return None

        # Build transaction
        tx_params: TxParams = {
            "from": self.account.address,
            "gas": arb_plan.gas_estimate,
            "gasPrice": current_gas_price,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
        }

        try:
            # Build the transaction
            tx = self.contract.functions.requestFlashLoan(
                Web3.to_checksum_address(loan_asset), loan_amount, arb_data
            ).build_transaction(tx_params)

            # Sign and send
            signed_tx = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            log.info("flash_loan.tx_submitted", tx_hash=tx_hash.hex())

            # Wait for receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

            log.info(
                "flash_loan.tx_confirmed",
                tx_hash=tx_hash.hex(),
                status=receipt["status"],
                gas_used=receipt["gasUsed"],
            )

            return receipt

        except Exception:
            log.exception("flash_loan.execution_failed")
            raise

    def build_weth_usdc_arb_plan(
        self,
        borrow_amount_eth: float,
        expected_profit_eth: float,
        min_profit_eth: Optional[float] = None,
    ) -> ArbPlan:
        """Build a standard WETH/USDC circular arbitrage plan.

        Args:
            borrow_amount_eth: ETH to borrow (will be converted to wei)
            expected_profit_eth: Expected profit in ETH
            min_profit_eth: Minimum profit threshold (uses default if None)

        Returns:
            Complete ArbPlan ready for execution
        """
        borrow_amount = Web3.to_wei(borrow_amount_eth, "ether")
        expected_profit = Web3.to_wei(expected_profit_eth, "ether")
        min_profit = Web3.to_wei(
            min_profit_eth or self.settings.min_profit_threshold_eth, "ether"
        )

        # Encode path: WETH -> USDC -> WETH
        path = self.encode_swap_path(
            token_in=self.settings.weth_address,
            token_out=self.settings.weth_address,
            intermediate_token=self.settings.usdc_address,
            fee_tier=3000,  # 0.3%
        )

        # Calculate minimum output with slippage
        expected_output = borrow_amount + expected_profit
        slippage_multiplier = (10000 - self.settings.slippage_tolerance_bps) / 10000
        min_amount_out = Wei(int(expected_output * slippage_multiplier))

        # Encode swap data
        swap_data = self.encode_swap_data(
            path=path, amount_in=Wei(borrow_amount), min_amount_out=min_amount_out
        )

        return ArbPlan(
            router_address=Web3.to_checksum_address(self.settings.uni_v3_router),
            swap_data=bytes.fromhex(swap_data[2:]),  # Remove '0x' prefix
            final_token=Web3.to_checksum_address(self.settings.weth_address),
            min_profit=Wei(min_profit),
            expected_profit=Wei(expected_profit),
            gas_estimate=self.settings.gas_estimate,
        )
