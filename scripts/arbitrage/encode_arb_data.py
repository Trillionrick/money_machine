#!/usr/bin/env python3
"""Flash loan arbitrage data encoder for Ethereum/Polygon.

Modern Python implementation (2025) replacing deprecated ethers.js v5.
Integrates with Money Machine's core arbitrage infrastructure.

Usage:
    # Interactive mode with defaults
    python encode_arb_data.py

    # Custom parameters
    python encode_arb_data.py --borrow 100 --min-profit 0.5 --expected-profit 2

    # JSON output for automation
    python encode_arb_data.py --json > arb_params.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import structlog
from eth_abi.abi import encode
from web3 import Web3

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.dex.config import ROUTER_ADDRESSES, TOKEN_ADDRESSES

log = structlog.get_logger()


@dataclass
class ArbConfig:
    """Arbitrage configuration parameters."""

    contract_address: str
    borrow_amount_eth: Decimal
    min_profit_eth: Decimal
    expected_profit_eth: Decimal
    gas_estimate: int
    slippage_bps: int = 50  # 0.5% default
    gas_price_gwei: int = 50
    chain: str = "ethereum"

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.borrow_amount_eth <= 0:
            msg = "Borrow amount must be positive"
            raise ValueError(msg)
        if self.min_profit_eth <= 0:
            msg = "Min profit must be positive"
            raise ValueError(msg)
        if self.expected_profit_eth < self.min_profit_eth:
            msg = "Expected profit must be >= min profit"
            raise ValueError(msg)
        if not Web3.is_address(self.contract_address):
            msg = f"Invalid contract address: {self.contract_address}"
            raise ValueError(msg)


@dataclass
class ConfigDict:
    """Configuration dictionary structure."""

    contract_address: str
    borrow_amount_eth: str
    min_profit_eth: str
    expected_profit_eth: str
    gas_estimate: int
    slippage_bps: int
    gas_price_gwei: int


@dataclass
class EncodedArbData:
    """Encoded arbitrage data ready for execution."""

    # Configuration
    config: ConfigDict

    # Encoded calldata
    swap_data: str
    arb_data: str

    # Profitability analysis
    flash_loan_fee_eth: Decimal
    gas_cost_eth: Decimal
    slippage_cost_eth: Decimal
    net_profit_eth: Decimal
    roi_bps: int
    break_even_bps: int

    # Execution parameters
    loan_asset: str
    loan_amount_wei: int
    deadline: int

    # Safety checks
    checks_passed: bool
    warnings: list[str]


class ArbitrageEncoder:
    """Encode arbitrage parameters for flash loan execution."""

    # Uniswap V3 fee tiers
    FEE_LOW = 500       # 0.05%
    FEE_MEDIUM = 3000   # 0.3%
    FEE_HIGH = 10000    # 1%

    # Aave V3 flash loan fee
    AAVE_FEE_BPS = 5    # 0.05%

    def __init__(self, config: ArbConfig):
        """Initialize encoder with configuration.

        Args:
            config: Arbitrage configuration parameters
        """
        self.config = config
        self.w3 = Web3()  # For encoding only, no provider needed

        # Get token addresses from project config
        self.weth = Web3.to_checksum_address(
            TOKEN_ADDRESSES[config.chain].get("WETH", TOKEN_ADDRESSES["ethereum"]["WETH"])
        )
        self.usdc = Web3.to_checksum_address(
            TOKEN_ADDRESSES[config.chain].get("USDC", TOKEN_ADDRESSES["ethereum"]["USDC"])
        )
        self.router = Web3.to_checksum_address(
            ROUTER_ADDRESSES[config.chain]["uniswap_v3"]
        )

        log.info(
            "encoder.initialized",
            chain=config.chain,
            weth=self.weth,
            usdc=self.usdc,
            router=self.router,
        )

    def encode_swap_path(self) -> bytes:
        """Encode Uniswap V3 swap path.

        Returns:
            Encoded path: WETH → USDC → WETH
        """
        # Pack: token0, fee, token1, fee, token2
        path = b"".join([
            bytes.fromhex(self.weth[2:]),
            self.FEE_MEDIUM.to_bytes(3, "big"),
            bytes.fromhex(self.usdc[2:]),
            self.FEE_MEDIUM.to_bytes(3, "big"),
            bytes.fromhex(self.weth[2:]),
        ])

        log.debug(
            "swap_path.encoded",
            path_hex=path.hex(),
            route="WETH→USDC→WETH",
            fee_tier=self.FEE_MEDIUM / 10000,
        )

        return path

    def encode_swap_data(self, path: bytes, borrow_amount_wei: int) -> str:
        """Encode Uniswap V3 exactInput swap calldata.

        Args:
            path: Encoded swap path
            borrow_amount_wei: Amount to swap in wei

        Returns:
            Hex-encoded swap calldata
        """
        deadline = int((datetime.now(timezone.utc) + timedelta(minutes=20)).timestamp())

        # Calculate minimum output with slippage
        expected_output = borrow_amount_wei + int(
            self.config.expected_profit_eth * 10**18
        )
        min_amount_out = expected_output * (10000 - self.config.slippage_bps) // 10000

        # ExactInputParams struct
        params = (
            path,                                    # bytes path
            self.config.contract_address,            # address recipient
            deadline,                                # uint256 deadline
            borrow_amount_wei,                       # uint256 amountIn
            min_amount_out,                          # uint256 amountOutMinimum
        )

        # Encode function call: exactInput((bytes,address,uint256,uint256,uint256))
        function_signature = Web3.keccak(text="exactInput((bytes,address,uint256,uint256,uint256))")[:4]
        encoded_params = encode(
            ["bytes", "address", "uint256", "uint256", "uint256"],
            params,
        )

        swap_data = (function_signature + encoded_params).hex()

        log.debug(
            "swap_data.encoded",
            deadline=datetime.fromtimestamp(deadline, tz=timezone.utc).isoformat(),
            min_output_eth=Decimal(min_amount_out) / 10**18,
            slippage_bps=self.config.slippage_bps,
        )

        return swap_data

    def encode_arb_data(self, swap_data: str) -> str:
        """Encode ArbPlan struct for flash loan callback.

        Args:
            swap_data: Encoded swap calldata

        Returns:
            Hex-encoded ArbPlan struct
        """
        min_profit_wei = int(self.config.min_profit_eth * 10**18)
        expected_profit_wei = int(self.config.expected_profit_eth * 10**18)

        # ArbPlan struct
        arb_plan = (
            self.router,                     # address routerAddress
            bytes.fromhex(swap_data[2:]),    # bytes swapData
            self.weth,                       # address finalToken
            min_profit_wei,                  # uint256 minProfit
            expected_profit_wei,             # uint256 expectedProfit
            self.config.gas_estimate,        # uint256 gasEstimate
        )

        # Encode as tuple
        encoded = encode(
            ["address", "bytes", "address", "uint256", "uint256", "uint256"],
            arb_plan,
        )

        log.debug(
            "arb_data.encoded",
            router=self.router,
            final_token=self.weth,
            min_profit_eth=self.config.min_profit_eth,
            expected_profit_eth=self.config.expected_profit_eth,
        )

        return encoded.hex()

    def calculate_profitability(self, borrow_amount_wei: int) -> tuple[Decimal, Decimal, Decimal, Decimal, int, int]:
        """Calculate profitability metrics.

        Args:
            borrow_amount_wei: Flash loan amount in wei

        Returns:
            Tuple of (flash_loan_fee_eth, gas_cost_eth, slippage_cost_eth,
                     net_profit_eth, roi_bps, break_even_bps)
        """
        borrow_eth = Decimal(borrow_amount_wei) / 10**18

        # Flash loan fee (Aave V3: 0.05%)
        flash_loan_fee_eth = borrow_eth * self.AAVE_FEE_BPS / 10000

        # Gas cost
        gas_cost_eth = (
            Decimal(self.config.gas_estimate) * self.config.gas_price_gwei / 10**9
        )

        # Slippage cost estimate
        slippage_cost_eth = borrow_eth * self.config.slippage_bps / 10000

        # Total costs
        total_costs_eth = flash_loan_fee_eth + gas_cost_eth + slippage_cost_eth

        # Net profit
        net_profit_eth = self.config.expected_profit_eth - total_costs_eth

        # ROI (basis points)
        roi_bps = int((net_profit_eth / borrow_eth) * 10000)

        # Break-even spread
        break_even_cost_eth = flash_loan_fee_eth + gas_cost_eth
        break_even_bps = int((break_even_cost_eth / borrow_eth) * 10000)

        log.info(
            "profitability.calculated",
            flash_loan_fee_eth=float(flash_loan_fee_eth),
            gas_cost_eth=float(gas_cost_eth),
            slippage_cost_eth=float(slippage_cost_eth),
            net_profit_eth=float(net_profit_eth),
            roi_bps=roi_bps,
            break_even_bps=break_even_bps,
        )

        return (
            flash_loan_fee_eth,
            gas_cost_eth,
            slippage_cost_eth,
            net_profit_eth,
            roi_bps,
            break_even_bps,
        )

    def run_safety_checks(
        self,
        net_profit_eth: Decimal,
        roi_bps: int,
    ) -> tuple[bool, list[str]]:
        """Run pre-flight safety checks.

        Args:
            net_profit_eth: Net profit in ETH
            roi_bps: ROI in basis points

        Returns:
            Tuple of (all_passed, warnings)
        """
        checks = []
        warnings = []

        # Net profit positive
        net_profit_positive = net_profit_eth > 0
        checks.append(net_profit_positive)
        if not net_profit_positive:
            warnings.append("Net profit is NEGATIVE - transaction will lose money!")

        # Net profit > min profit
        profit_exceeds_min = net_profit_eth > self.config.min_profit_eth
        checks.append(profit_exceeds_min)
        if not profit_exceeds_min:
            warnings.append(f"Net profit below minimum threshold ({self.config.min_profit_eth} ETH)")

        # ROI > 1%
        roi_acceptable = roi_bps > 100
        checks.append(roi_acceptable)
        if not roi_acceptable:
            warnings.append(f"ROI too low: {roi_bps / 100}%")

        # Gas price reasonable
        gas_reasonable = self.config.gas_price_gwei <= 100
        checks.append(gas_reasonable)
        if not gas_reasonable:
            warnings.append(f"Gas price very high: {self.config.gas_price_gwei} Gwei")

        # Contract address set
        contract_valid = self.config.contract_address != "0xYOUR_DEPLOYED_CONTRACT_ADDRESS"
        checks.append(contract_valid)
        if not contract_valid:
            warnings.append("Contract address not configured!")

        all_passed = all(checks)

        log.info(
            "safety_checks.completed",
            passed=sum(checks),
            failed=len(checks) - sum(checks),
            all_passed=all_passed,
        )

        return all_passed, warnings

    def encode(self) -> EncodedArbData:
        """Encode complete arbitrage data.

        Returns:
            Complete encoded data ready for execution
        """
        log.info("encoding.started", config=asdict(self.config))

        # Convert amounts to wei
        borrow_amount_wei = int(self.config.borrow_amount_eth * 10**18)

        # Step 1: Encode swap path
        path = self.encode_swap_path()

        # Step 2: Encode swap data
        swap_data = self.encode_swap_data(path, borrow_amount_wei)

        # Step 3: Encode arb data
        arb_data = self.encode_arb_data(swap_data)

        # Step 4: Calculate profitability
        (
            flash_loan_fee_eth,
            gas_cost_eth,
            slippage_cost_eth,
            net_profit_eth,
            roi_bps,
            break_even_bps,
        ) = self.calculate_profitability(borrow_amount_wei)

        # Step 5: Run safety checks
        checks_passed, warnings = self.run_safety_checks(net_profit_eth, roi_bps)

        # Calculate deadline
        deadline = int((datetime.now(timezone.utc) + timedelta(minutes=20)).timestamp())

        result = EncodedArbData(
            config=ConfigDict(
                contract_address=self.config.contract_address,
                borrow_amount_eth=str(self.config.borrow_amount_eth),
                min_profit_eth=str(self.config.min_profit_eth),
                expected_profit_eth=str(self.config.expected_profit_eth),
                gas_estimate=self.config.gas_estimate,
                slippage_bps=self.config.slippage_bps,
                gas_price_gwei=self.config.gas_price_gwei,
            ),
            swap_data=f"0x{swap_data}",
            arb_data=f"0x{arb_data}",
            flash_loan_fee_eth=flash_loan_fee_eth,
            gas_cost_eth=gas_cost_eth,
            slippage_cost_eth=slippage_cost_eth,
            net_profit_eth=net_profit_eth,
            roi_bps=roi_bps,
            break_even_bps=break_even_bps,
            loan_asset=self.weth,
            loan_amount_wei=borrow_amount_wei,
            deadline=deadline,
            checks_passed=checks_passed,
            warnings=warnings,
        )

        log.info("encoding.completed", checks_passed=checks_passed)

        return result


def print_encoded_data(data: EncodedArbData) -> None:
    """Print encoded data in human-readable format.

    Args:
        data: Encoded arbitrage data
    """
    print("=" * 80)
    print("MONEY MACHINE - ARBITRAGE DATA ENCODER (Python)")
    print("=" * 80)

    print(f"\n✅ Contract Address: {data.config.contract_address}")

    print("\n📊 Configuration:")
    print(f"   Borrow Amount: {data.config.borrow_amount_eth} WETH")
    print(f"   Min Profit: {data.config.min_profit_eth} WETH")
    print(f"   Expected Profit: {data.config.expected_profit_eth} WETH")
    print(f"   Gas Estimate: {data.config.gas_estimate:,} units")
    print(f"   Gas Price: {data.config.gas_price_gwei} Gwei")
    print(f"   Slippage: {data.config.slippage_bps / 100}%")

    print("\n💰 Profitability Analysis:")
    print(f"   Expected Gross Profit: {data.config.expected_profit_eth} WETH")
    print(f"   Flash Loan Fee (0.05%): {data.flash_loan_fee_eth:.6f} WETH")
    print(f"   Gas Cost ({data.config.gas_price_gwei} Gwei): {data.gas_cost_eth:.6f} ETH")
    print(f"   Slippage Cost ({data.config.slippage_bps / 100}%): {data.slippage_cost_eth:.6f} WETH")
    print(f"   {'─' * 50}")
    print(f"   Net Profit: {data.net_profit_eth:.6f} WETH")
    print(f"   Profitable: {'✅ YES' if data.net_profit_eth > 0 else '❌ NO'}")
    print(f"   Break-Even Spread: {data.break_even_bps / 100:.2f}%")
    print(f"   ROI: {data.roi_bps / 100:.2f}%")

    print("\n📦 Encoded Data:")
    print("=" * 80)
    print(f"\n✅ arbData (Copy for transaction):")
    print(data.arb_data)

    print("\n🚀 Execution Parameters:")
    print(f"   - loanAsset: {data.loan_asset}")
    print(f"   - loanAmount: {data.loan_amount_wei}")
    print(f"   - arbData: [See above]")
    print(f"   - deadline: {datetime.fromtimestamp(data.deadline, tz=timezone.utc)}")

    print("\n⚠️  Pre-Flight Checklist:")
    print("=" * 80)
    if data.checks_passed:
        print("✅ ALL CHECKS PASSED - READY TO EXECUTE!")
    else:
        print("❌ SOME CHECKS FAILED - REVIEW BEFORE EXECUTING!")

    if data.warnings:
        print("\n⚠️  WARNINGS:")
        for warning in data.warnings:
            print(f"   - {warning}")

    print("\n⚠️  CRITICAL SAFETY REMINDERS:")
    print("   1. TEST ON TESTNET FIRST!")
    print("   2. Verify liquidity in pools")
    print("   3. Check current gas prices")
    print("   4. Simulate transaction first")
    print("   5. Monitor for MEV attacks")
    print("=" * 80)


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    parser = argparse.ArgumentParser(
        description="Encode arbitrage data for flash loan execution"
    )
    parser.add_argument(
        "--contract",
        default=os.getenv("ARB_CONTRACT_ADDRESS", "0xYOUR_DEPLOYED_CONTRACT_ADDRESS"),
        help="Deployed flash loan contract address",
    )
    parser.add_argument(
        "--borrow",
        type=float,
        default=float(os.getenv("BORROW_AMOUNT", "100")),
        help="Borrow amount in ETH (default: 100)",
    )
    parser.add_argument(
        "--min-profit",
        type=float,
        default=float(os.getenv("MIN_PROFIT", "0.5")),
        help="Minimum profit in ETH (default: 0.5)",
    )
    parser.add_argument(
        "--expected-profit",
        type=float,
        default=float(os.getenv("EXPECTED_PROFIT", "2")),
        help="Expected profit in ETH (default: 2)",
    )
    parser.add_argument(
        "--gas-estimate",
        type=int,
        default=int(os.getenv("GAS_ESTIMATE", "350000")),
        help="Gas estimate in units (default: 350000)",
    )
    parser.add_argument(
        "--gas-price",
        type=int,
        default=int(os.getenv("GAS_PRICE", "50")),
        help="Gas price in Gwei (default: 50)",
    )
    parser.add_argument(
        "--slippage",
        type=int,
        default=50,
        help="Slippage tolerance in bps (default: 50 = 0.5%%)",
    )
    parser.add_argument(
        "--chain",
        default="ethereum",
        choices=["ethereum", "polygon"],
        help="Target chain (default: ethereum)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable format",
    )

    args = parser.parse_args()

    try:
        # Create configuration
        config = ArbConfig(
            contract_address=args.contract,
            borrow_amount_eth=Decimal(str(args.borrow)),
            min_profit_eth=Decimal(str(args.min_profit)),
            expected_profit_eth=Decimal(str(args.expected_profit)),
            gas_estimate=args.gas_estimate,
            gas_price_gwei=args.gas_price,
            slippage_bps=args.slippage,
            chain=args.chain,
        )

        # Encode data
        encoder = ArbitrageEncoder(config)
        result = encoder.encode()

        # Output
        if args.json:
            # JSON output for automation
            output = {
                "config": {
                    "contract_address": result.config.contract_address,
                    "borrow_amount_eth": result.config.borrow_amount_eth,
                    "min_profit_eth": result.config.min_profit_eth,
                    "expected_profit_eth": result.config.expected_profit_eth,
                    "gas_estimate": result.config.gas_estimate,
                    "slippage_bps": result.config.slippage_bps,
                    "gas_price_gwei": result.config.gas_price_gwei,
                },
                "encoded": {
                    "swap_data": result.swap_data,
                    "arb_data": result.arb_data,
                },
                "execution": {
                    "loan_asset": result.loan_asset,
                    "loan_amount_wei": result.loan_amount_wei,
                    "deadline": result.deadline,
                },
                "analysis": {
                    "flash_loan_fee_eth": str(result.flash_loan_fee_eth),
                    "gas_cost_eth": str(result.gas_cost_eth),
                    "slippage_cost_eth": str(result.slippage_cost_eth),
                    "net_profit_eth": str(result.net_profit_eth),
                    "roi_bps": result.roi_bps,
                    "break_even_bps": result.break_even_bps,
                },
                "safety": {
                    "checks_passed": result.checks_passed,
                    "warnings": result.warnings,
                },
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-readable output
            print_encoded_data(result)

        return 0 if result.checks_passed else 1

    except Exception as e:
        log.error("encoding.failed", error=str(e))
        print(f"\n❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
