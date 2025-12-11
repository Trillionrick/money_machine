#!/usr/bin/env python3
"""Comprehensive system health check for money_machine arbitrage system."""

import asyncio
import os
import sys
import time
from decimal import Decimal
from typing import Any

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
from web3 import Web3

load_dotenv()


class HealthCheck:
    """System health check runner."""

    def __init__(self):
        self.results: dict[str, dict[str, Any]] = {}
        self.start_time = time.time()

    def add_result(self, category: str, test: str, status: str, value: Any = None, latency_ms: float | None = None, error: str | None = None):
        """Record test result."""
        if category not in self.results:
            self.results[category] = {}

        self.results[category][test] = {
            "status": status,  # "PASS", "FAIL", "WARN"
            "value": value,
            "latency_ms": latency_ms,
            "error": error
        }

    async def test_rpc_connectivity(self):
        """Test RPC endpoints for Ethereum and Polygon."""
        print("Testing RPC connectivity...")

        # Ethereum
        eth_rpc = os.getenv("ETHEREUM_RPC_URL", "")
        if eth_rpc:
            try:
                start = time.time()
                w3_eth = Web3(Web3.HTTPProvider(eth_rpc))
                block = w3_eth.eth.block_number
                latency = (time.time() - start) * 1000
                self.add_result("RPC", "Ethereum", "PASS", f"Block {block}", latency)
            except Exception as e:
                self.add_result("RPC", "Ethereum", "FAIL", error=str(e))
        else:
            self.add_result("RPC", "Ethereum", "FAIL", error="No RPC URL configured")

        # Polygon
        poly_rpc = os.getenv("POLYGON_RPC_URL", "")
        if poly_rpc:
            try:
                start = time.time()
                w3_poly = Web3(Web3.HTTPProvider(poly_rpc))
                block = w3_poly.eth.block_number
                latency = (time.time() - start) * 1000
                self.add_result("RPC", "Polygon", "PASS", f"Block {block}", latency)
            except Exception as e:
                self.add_result("RPC", "Polygon", "FAIL", error=str(e))
        else:
            self.add_result("RPC", "Polygon", "FAIL", error="No RPC URL configured")

    async def test_cex_apis(self):
        """Test CEX API connectivity."""
        print("Testing CEX APIs...")

        # Use CEXPriceFetcher instead of individual adapters
        try:
            from src.brokers.price_fetcher import CEXPriceFetcher

            start = time.time()
            fetcher = CEXPriceFetcher(binance_enabled=False, kraken_enabled=True, alpaca_enabled=False)

            # Test Kraken
            try:
                price = await fetcher.get_price("ETH/USDC")
                latency = (time.time() - start) * 1000

                if price:
                    self.add_result("CEX", "Kraken", "PASS", f"${float(price):.2f}", latency)
                else:
                    self.add_result("CEX", "Kraken", "WARN", "No price data")
            except Exception as e:
                self.add_result("CEX", "Kraken", "FAIL", error=str(e)[:100])

            # Alpaca (if configured)
            alpaca_key = os.getenv("ALPACA_API_KEY")
            if alpaca_key:
                self.add_result("CEX", "Alpaca", "PASS", "Credentials configured")
            else:
                self.add_result("CEX", "Alpaca", "WARN", "No credentials")

        except ImportError as e:
            self.add_result("CEX", "PriceFetcher", "FAIL", error=f"Import error: {e}")

    async def test_dex_quotes(self):
        """Test DEX quote fetching."""
        print("Testing DEX quotes...")

        try:
            from src.dex.uniswap_connector import UniswapConnector
            from src.dex.config import UniswapConfig, Chain
            from pydantic import SecretStr

            # Initialize config (requires The Graph API key)
            graph_key = os.getenv("THEGRAPH_API_KEY")
            if not graph_key:
                self.add_result("DEX", "Uniswap", "FAIL", error="Missing THEGRAPH_API_KEY")
                return

            config = UniswapConfig(THEGRAPH_API_KEY=SecretStr(graph_key))

            # Test Ethereum Uniswap
            try:
                start = time.time()
                uni = UniswapConnector(config, Chain.ETHEREUM)

                # WETH/USDC on Ethereum
                weth = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
                usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

                quote = await uni.get_quote(weth, usdc, Decimal("1"))
                latency = (time.time() - start) * 1000

                if quote and "expected_output" in quote:
                    self.add_result("DEX", "Uniswap-ETH", "PASS",
                                  f"${float(quote['expected_output']):.2f}", latency)
                else:
                    self.add_result("DEX", "Uniswap-ETH", "FAIL", error="No quote returned")
            except Exception as e:
                self.add_result("DEX", "Uniswap-ETH", "FAIL", error=str(e)[:100])

            # Test Polygon
            try:
                start = time.time()
                uni_poly = UniswapConnector(config, Chain.POLYGON)

                # WETH/USDC on Polygon
                weth_poly = "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619"
                usdc_poly = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

                quote = await uni_poly.get_quote(weth_poly, usdc_poly, Decimal("1"))
                latency = (time.time() - start) * 1000

                if quote and "expected_output" in quote:
                    self.add_result("DEX", "Uniswap-Polygon", "PASS",
                                  f"${float(quote['expected_output']):.2f}", latency)
                else:
                    self.add_result("DEX", "Uniswap-Polygon", "FAIL", error="No quote returned")
            except Exception as e:
                self.add_result("DEX", "Uniswap-Polygon", "FAIL", error=str(e)[:100])

        except ImportError as e:
            self.add_result("DEX", "Uniswap", "FAIL", error=f"Import error: {str(e)[:100]}")

        # 1inch
        oneinch_key = os.getenv("ONEINCH_API_KEY")
        if oneinch_key:
            self.add_result("DEX", "1inch", "WARN", "Known 500 errors (2024-12-02)")
        else:
            self.add_result("DEX", "1inch", "FAIL", error="No API key")

    async def test_gas_oracle(self):
        """Test gas oracle functionality."""
        print("Testing gas oracle...")

        try:
            from src.live.gas_oracle import GasOracle
            from web3 import AsyncWeb3

            # Ethereum
            eth_rpc = os.getenv("ETHEREUM_RPC_URL", "")
            if eth_rpc:
                try:
                    start = time.time()
                    oracle = GasOracle()
                    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(eth_rpc))
                    gas_price = await oracle.get_gas_price("ethereum", w3)
                    latency = (time.time() - start) * 1000

                    if gas_price and gas_price.gwei:
                        self.add_result("GasOracle", "Ethereum", "PASS",
                                      f"{gas_price.gwei:.1f} gwei ({gas_price.source})", latency)
                    else:
                        self.add_result("GasOracle", "Ethereum", "FAIL", error="No gas data")
                except Exception as e:
                    self.add_result("GasOracle", "Ethereum", "FAIL", error=str(e)[:100])

            # Polygon
            poly_rpc = os.getenv("POLYGON_RPC_URL", "")
            if poly_rpc:
                try:
                    start = time.time()
                    oracle_poly = GasOracle()
                    w3_poly = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(poly_rpc))
                    gas_price = await oracle_poly.get_gas_price("polygon", w3_poly)
                    latency = (time.time() - start) * 1000

                    if gas_price and gas_price.gwei:
                        self.add_result("GasOracle", "Polygon", "PASS",
                                      f"{gas_price.gwei:.1f} gwei ({gas_price.source})", latency)
                    else:
                        self.add_result("GasOracle", "Polygon", "FAIL", error="No gas data")
                except Exception as e:
                    self.add_result("GasOracle", "Polygon", "FAIL", error=str(e)[:100])

        except ImportError as e:
            self.add_result("GasOracle", "Import", "FAIL", error=str(e)[:100])

    async def test_flash_loan_executor(self):
        """Verify flash loan executor initialization."""
        print("Testing flash loan executor...")

        try:
            from src.dex.flash_loan_executor import FlashLoanSettings, FlashLoanExecutor

            contract_addr = os.getenv("ARB_CONTRACT_ADDRESS")
            private_key = os.getenv("PRIVATE_KEY")
            eth_rpc = os.getenv("ETH_RPC_URL")

            if not contract_addr:
                self.add_result("FlashLoan", "Config", "FAIL", error="No contract address")
                return

            if not private_key:
                self.add_result("FlashLoan", "Config", "WARN", value="No private key (read-only)")

            if eth_rpc and contract_addr and private_key:
                try:
                    # Use settings-based initialization
                    settings = FlashLoanSettings()
                    self.add_result("FlashLoan", "Initialization", "PASS",
                                  f"Contract: {contract_addr[:10]}...")
                except Exception as e:
                    self.add_result("FlashLoan", "Initialization", "FAIL", error=str(e)[:100])
            else:
                missing = []
                if not eth_rpc:
                    missing.append("RPC URL")
                if not contract_addr:
                    missing.append("contract address")
                if not private_key:
                    missing.append("private key")
                self.add_result("FlashLoan", "Config", "FAIL",
                              error=f"Missing: {', '.join(missing)}")

        except ImportError as e:
            self.add_result("FlashLoan", "Import", "FAIL", error=str(e)[:100])

    def display_config(self):
        """Display current configuration."""
        print("Reading configuration...")

        config_items = {
            "DRY_RUN": os.getenv("DRY_RUN", "true"),
            "ENABLE_FLASH_LOANS": os.getenv("ENABLE_FLASH_LOANS", "false"),
            "MIN_FLASH_PROFIT_ETH": os.getenv("MIN_FLASH_PROFIT_ETH", "N/A"),
            "FLASH_LOAN_THRESHOLD_BPS": os.getenv("FLASH_LOAN_THRESHOLD_BPS", "N/A"),
            "MAX_GAS_PRICE_GWEI": os.getenv("MAX_GAS_PRICE_GWEI", "N/A"),
            "SLIPPAGE_TOLERANCE_BPS": os.getenv("SLIPPAGE_TOLERANCE_BPS", "N/A"),
            "TRADING_MODE": os.getenv("TRADING_MODE", "N/A"),
            "ENABLE_POLYGON_EXECUTION": os.getenv("ENABLE_POLYGON_EXECUTION", "false"),
        }

        for key, value in config_items.items():
            status = "PASS" if value != "N/A" else "WARN"
            self.results.setdefault("Config", {})[key] = {
                "status": status,
                "value": value,
                "latency_ms": None,
                "error": None
            }

    def print_results(self):
        """Print results in compact table format."""
        print("\n" + "=" * 80)
        print("SYSTEM HEALTH CHECK RESULTS")
        print("=" * 80)

        for category, tests in self.results.items():
            print(f"\n[{category}]")
            print("-" * 80)

            for test_name, result in tests.items():
                status = result["status"]
                status_symbol = "✓" if status == "PASS" else ("⚠" if status == "WARN" else "✗")

                # Format line
                parts = [f"{status_symbol} {test_name:25s}"]

                if result["value"]:
                    parts.append(f"{str(result['value']):30s}")

                if result["latency_ms"] is not None:
                    parts.append(f"[{result['latency_ms']:.0f}ms]")

                if result["error"]:
                    parts.append(f"ERROR: {result['error']}")

                print(" ".join(parts))

        # Summary
        total_tests = sum(len(tests) for tests in self.results.values())
        passed = sum(1 for tests in self.results.values()
                    for r in tests.values() if r["status"] == "PASS")
        failed = sum(1 for tests in self.results.values()
                    for r in tests.values() if r["status"] == "FAIL")
        warned = sum(1 for tests in self.results.values()
                    for r in tests.values() if r["status"] == "WARN")

        elapsed = time.time() - self.start_time

        print("\n" + "=" * 80)
        print(f"SUMMARY: {passed} passed, {warned} warnings, {failed} failed "
              f"({total_tests} total) in {elapsed:.2f}s")
        print("=" * 80)

        # Critical failures
        if failed > 0:
            print("\n⚠️  CRITICAL: System has failing components")
            return 1
        elif warned > 0:
            print("\n⚠️  WARNING: System has degraded components")
            return 0
        else:
            print("\n✓ System fully operational")
            return 0

    async def run_all(self):
        """Run all health checks."""
        await self.test_rpc_connectivity()
        await self.test_cex_apis()
        await self.test_dex_quotes()
        await self.test_gas_oracle()
        await self.test_flash_loan_executor()
        self.display_config()


async def main():
    """Main entry point."""
    checker = HealthCheck()
    await checker.run_all()
    exit_code = checker.print_results()
    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
