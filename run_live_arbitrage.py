"""
Complete live arbitrage system combining CEX and DEX trading.

This script:
1. Fetches prices from CEX (Binance, etc.)
2. Gets quotes from DEX (Uniswap)
3. Calculates arbitrage opportunities
4. Executes profitable trades (CEX or flash loans)

SAFETY: Starts in DRY_RUN mode by default!
"""

import asyncio
import os
import sys
from decimal import Decimal

import structlog
from dotenv import load_dotenv
from pydantic import SecretStr

# Load environment variables
load_dotenv()

# from src.brokers.binance_adapter import BinanceAdapter  # Disabled: geo-blocked in US
from src.brokers.price_fetcher import CEXPriceFetcher
from src.brokers.routing import OrderRouter
from src.brokers.alpaca_adapter import AlpacaAdapter
from src.brokers.kraken_adapter import KrakenAdapter
from src.brokers.oanda_adapter import OandaAdapter
from src.brokers.oanda_config import OandaConfig
from src.core.types import Symbol
from src.dex.config import UniswapConfig, Chain
from src.dex.uniswap_connector import UniswapConnector
from src.live.flash_arb_runner import FlashArbConfig, FlashArbitrageRunner

log = structlog.get_logger()


class ArbitrageSystem:
    """Complete arbitrage trading system."""

    def __init__(
        self,
        dry_run: bool = True,
        enable_flash_loans: bool = True,
    ):
        """Initialize arbitrage system.

        Args:
            dry_run: If True, no real trades are executed
            enable_flash_loans: Enable flash loan arbitrage
        """
        self.dry_run = dry_run
        self.enable_flash_loans = enable_flash_loans

        # Initialize components
        log.info("arbitrage_system.initializing", dry_run=dry_run)

        self.polygon_chain_id = int(os.getenv("POLYGON_CHAIN_ID", "137"))
        polygon_rpc_raw = os.getenv("POLYGON_RPC_URL") or os.getenv("POLYGON_RPC")
        self.polygon_rpc_url = polygon_rpc_raw.strip() if polygon_rpc_raw else None
        self.enable_polygon_execution = (
            os.getenv("ENABLE_POLYGON_EXECUTION", "false").lower() == "true"
        )
        self.gas_cap_eth_gwei = self._parse_float_env("GAS_PRICE_CAP_ETH") or 60.0
        self.gas_cap_polygon_gwei = self._parse_float_env("GAS_PRICE_CAP_POLYGON") or 80.0
        self.min_margin_bps = self._parse_float_env("MIN_MARGIN_BPS") or 5.0
        oneinch_key_raw = os.getenv("ONEINCH_API_KEY") or os.getenv("ONEINCH_TOKEN")
        self.oneinch_api_key = oneinch_key_raw.strip() if oneinch_key_raw else None
        self.eth_native_token_price = self._parse_float_env("ETH_NATIVE_TOKEN_PRICE")
        self.polygon_native_token_price = self._parse_float_env(
            "POLYGON_NATIVE_TOKEN_PRICE"
        ) or self._parse_float_env("MATIC_PRICE")

        # 1. CEX Price Fetcher
        self.price_fetcher = CEXPriceFetcher(
            binance_enabled=False,  # Disabled: geo-blocked in US
            alpaca_enabled=False,   # Enable if you need US equities
            kraken_enabled=True,    # Kraken as primary for crypto
        )

        # 1b. DEX shared config
        eth_rpc_raw = os.getenv("ETH_RPC_URL") or os.getenv("ETHEREUM_RPC_URL")
        eth_rpc = eth_rpc_raw.strip() if eth_rpc_raw else None
        private_key_raw = os.getenv("PRIVATE_KEY") or os.getenv("WALLET_PRIVATE_KEY")
        private_key = private_key_raw.strip() if private_key_raw else None
        graph_key = os.getenv("THEGRAPH_API_KEY", "").strip()

        self.uniswap_config = UniswapConfig(
            THEGRAPH_API_KEY=SecretStr(graph_key) if graph_key else SecretStr(""),
            ETHEREUM_RPC_URL=SecretStr(eth_rpc) if eth_rpc else None,
            POLYGON_RPC_URL=SecretStr(self.polygon_rpc_url) if self.polygon_rpc_url else None,
            WALLET_PRIVATE_KEY=SecretStr(private_key) if private_key else None,
        )

        # 2. DEX Connector (Uniswap)
        self.dex = self._init_uniswap(chain=Chain.ETHEREUM)
        self.polygon_dex = self._init_polygon_uniswap()

        # 3. CEX Order Router
        self.router = self._init_router()

        # 4. Token addresses (mainnet)
        self.token_addresses = {
            # Major tokens
            "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
            "ETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "BTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # WBTC
            "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",

            # Stablecoins
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",

            # Layer 2 / Ecosystem tokens
            "MATIC": "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0",
            "LINK": "0x514910771AF9Ca656af840dff83E8264EcF986CA",
            "UNI": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
            "AAVE": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",

            # DeFi tokens
            "MKR": "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2",
            "CRV": "0xD533a949740bb3306d119CC777fa900bA034cd52",
            "SNX": "0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F",
            "COMP": "0xc00e94Cb662C3520282E6f5717214004A7f26888",
            "GRT": "0xc944E90C64B2c07662A292be6244BDf05Cda44a7",   # The Graph

            # Meme/Community tokens (high volume)
            "SHIB": "0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE",  # Shiba Inu
            "PEPE": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",  # Pepe

            # Liquid staking tokens (for statistical arbitrage)
            "stETH": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",  # Lido Staked ETH
            "rETH": "0xae78736Cd615f374D3085123A210448E74Fc6393",   # Rocket Pool ETH

            # Additional DeFi blue chips
            "LDO": "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32",   # Lido DAO
            "APE": "0x4d224452801ACEd8B2F0aebE155379bb5D594381",   # ApeCoin
        }
        # Polygon token addresses
        self.polygon_token_addresses = {
            "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
            "USDC": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # bridged USDC.e
            "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
            "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
            "ETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",  # WETH
            "BTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",  # WBTC
            "WBTC": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",
            "MATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
            "LINK": "0x53E0bca35eC356Bd5ddDFebbD1Fc0fD03Fabad39",
            "UNI": "0xb33EaAd8d922B1083446DC23f610c2567Fb5180f",
            "AAVE": "0xD6DF932A45C0f255f85145f286eA0b292B21C90B",
            "GRT": "0x5Fe2B58c013d7601147DCdd68C143A77499f5531",
            "SHIB": "0x6f8a06447Ff6FcF75d803135a7de15CE88C1d4ec",  # Polygon bridged SHIB
            "stETH": "0x9bcef72be871e61ed4fbbc7630889bee758eb81d",  # Polygon wstETH (bridged)
            "LDO": "0xC3C7d422809852031b44ab29EEC9F1EfF2A58756",
            "APE": "0xb7b31a6BC18e48888545Ce79e83E06003be70930",
            "rETH": "0x0266f4f08d82372cf0fcbccc0ff74309089c74d1",  # Polygon rETH (verify liquidity)
        }

        self.token_decimals = {
            # Stablecoins
            "USDC": 6,
            "USDT": 6,
            "DAI": 18,

            # Major tokens
            "WETH": 18,
            "ETH": 18,
            "BTC": 8,
            "WBTC": 8,

            # Layer 2 / Ecosystem
            "MATIC": 18,
            "LINK": 18,
            "UNI": 18,
            "AAVE": 18,

            # DeFi tokens
            "MKR": 18,
            "CRV": 18,
            "SNX": 18,
            "COMP": 18,
            "GRT": 18,

            # Meme/Community tokens
            "SHIB": 18,
            "PEPE": 18,

            # Liquid staking tokens
            "stETH": 18,
            "rETH": 18,

            # Additional DeFi
            "LDO": 18,
            "APE": 18,
        }

        # 5. Configure arbitrage parameters
        # Read flash loan settings from environment (with defaults)
        min_flash_profit = float(os.getenv("MIN_FLASH_PROFIT_ETH", "0.05"))
        max_flash_borrow = float(os.getenv("MAX_FLASH_BORROW_ETH", "10.0"))
        flash_threshold = float(os.getenv("FLASH_LOAN_THRESHOLD_BPS", "50.0"))
        slippage_bps = int(os.getenv("SLIPPAGE_TOLERANCE_BPS", "50"))

        self.config = FlashArbConfig(
            # Scanning settings
            min_edge_bps=25.0,  # 0.25% minimum spread for regular arb
            poll_interval=5.0,  # Check every 5 seconds
            max_notional=1000.0,  # $1000 max for regular arb

            # Flash loan settings (from .env)
            enable_flash_loans=enable_flash_loans,
            min_flash_profit_eth=min_flash_profit,
            max_flash_borrow_eth=max_flash_borrow,
            flash_loan_threshold_bps=flash_threshold,

            # Position/risk settings
            max_position=1.0,  # Max 1 unit position
            slippage_tolerance=slippage_bps / 10000.0,  # From .env (in bps)

            # Safety
            enable_execution=not dry_run,  # Only execute if not dry run

            # Polygon
            enable_polygon=bool(self.polygon_rpc_url),
            enable_polygon_execution=self.enable_polygon_execution,
            polygon_chain_id=self.polygon_chain_id,
            polygon_rpc_url=self.polygon_rpc_url,
            eth_native_token_price=self.eth_native_token_price,
            polygon_native_token_price=self.polygon_native_token_price,
            gas_price_cap_gwei={
                "ethereum": self.gas_cap_eth_gwei,
                "polygon": self.gas_cap_polygon_gwei,
            },
            min_margin_bps=self.min_margin_bps,
        )

        # Symbols to scan
        self.symbols = [
            # Major pairs (highest volume)
            "ETH/USDC",
            "WETH/USDC",
            "ETH/USDT",
            "BTC/USDT",
            "WBTC/USDC",

            # Stablecoin pairs (low volatility, frequent arb)
            "USDT/USDC",
            "DAI/USDC",

            # DeFi blue chips
            "LINK/USDC",
            "LINK/ETH",
            "UNI/USDC",
            "UNI/ETH",
            "AAVE/USDC",
            "AAVE/ETH",
            "GRT/USDC",
            "GRT/ETH",

            # Layer 2 / Ecosystem
            "MATIC/USDC",
            "MATIC/ETH",

            # Meme/Community tokens (high volume, volatile)
            "SHIB/USDC",
            "SHIB/ETH",

            # Statistical arbitrage (liquid staking derivatives) -- Polygon disabled for stETH/rETH for now
            "WBTC/BTC",    # WBTC should track BTC 1:1

            # Additional DeFi
            "LDO/USDC",
            "LDO/ETH",
            "APE/USDC",
            "APE/ETH",

            # Add more pairs as needed
        ]

        log.info(
            "arbitrage_system.ready",
            symbols=self.symbols,
            dry_run=dry_run,
            flash_loans=enable_flash_loans,
        )

    def _init_uniswap(self, chain: Chain) -> UniswapConnector:
        """Initialize Uniswap connector."""
        return UniswapConnector(self.uniswap_config, chain=chain)

    def _init_polygon_uniswap(self) -> UniswapConnector | None:
        """Initialize Polygon Uniswap connector if RPC present."""
        if not self.polygon_rpc_url:
            return None
        try:
            return UniswapConnector(self.uniswap_config, chain=Chain.POLYGON)
        except Exception:
            log.warning("arbitrage_system.polygon_init_failed")
            return None

    def _init_router(self) -> OrderRouter:
        """Initialize order router with available connectors."""
        # For now, create a simple router
        # You can enhance this to connect to actual CEX adapters
        connectors = {}
        active = []

        # Binance disabled: geo-blocked in US
        # if os.getenv("BINANCE_API_KEY") and os.getenv("BINANCE_API_KEY") != "your_binance_key_here":
        #     try:
        #         binance = BinanceAdapter(
        #             api_key=os.getenv("BINANCE_API_KEY", ""),
        #             api_secret=os.getenv("BINANCE_API_SECRET", ""),
        #             testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
        #         )
        #         connectors["binance"] = binance
        #         active.append("binance")
        #         log.info("arbitrage_system.binance_connected")
        #     except Exception as e:
        #         log.warning("arbitrage_system.binance_failed", error=str(e))

        # Add Alpaca if credentials available
        if os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET"):
            try:
                alpaca = AlpacaAdapter(
                    api_key=os.getenv("ALPACA_API_KEY", ""),
                    api_secret=os.getenv("ALPACA_API_SECRET", ""),
                    paper=os.getenv("ALPACA_PAPER", "true").lower() == "true",
                )
                connectors["alpaca"] = alpaca
                active.append("alpaca")
                log.info("arbitrage_system.alpaca_connected")
            except Exception as e:
                log.warning("arbitrage_system.alpaca_failed", error=str(e))

        # Add Kraken if credentials available
        if os.getenv("KRAKEN_API_KEY") and os.getenv("KRAKEN_API_SECRET"):
            try:
                kraken = KrakenAdapter(
                    api_key=os.getenv("KRAKEN_API_KEY", ""),
                    api_secret=os.getenv("KRAKEN_API_SECRET", ""),
                )
                connectors["kraken"] = kraken
                active.append("kraken")
                log.info("arbitrage_system.kraken_connected")
            except Exception as e:
                log.warning("arbitrage_system.kraken_failed", error=str(e))

        # Add Oanda if credentials available
        oanda_token = os.getenv("OANDA_API_TOKEN")
        oanda_account = os.getenv("OANDA_ACCOUNT_ID")
        if oanda_token and oanda_account:
            try:
                # Create OandaConfig: inspect the model fields (works for pydantic v1 and v2)
                try:
                    model_fields = getattr(OandaConfig, "__fields__", None) or getattr(OandaConfig, "model_fields", None) or {}
                    field_names = set(model_fields.keys())

                    # Common candidate field names mapped to values
                    candidates = {
                        "api_token": SecretStr(oanda_token),
                        "account_id": oanda_account,
                        "OANDA_API_TOKEN": SecretStr(oanda_token),
                        "OANDA_ACCOUNT_ID": oanda_account,
                    }

                    # Build kwargs only for accepted fields to avoid TypeError
                    kwargs = {k: v for k, v in candidates.items() if k in field_names}

                    if kwargs:
                        oanda_config = OandaConfig(**kwargs)
                    else:
                        # Fallback: try parse_obj with common keys (allows aliases)
                        oanda_config = OandaConfig.parse_obj(
                            {"OANDA_API_TOKEN": oanda_token, "OANDA_ACCOUNT_ID": oanda_account}
                        )
                except Exception:
                    # As a final fallback, parse from a dict to let pydantic handle aliases
                    oanda_config = OandaConfig.parse_obj(
                        {"OANDA_API_TOKEN": oanda_token, "OANDA_ACCOUNT_ID": oanda_account}
                    )

                oanda = OandaAdapter(config=oanda_config)
                connectors["oanda"] = oanda
                active.append("oanda")
                log.info("arbitrage_system.oanda_connected")
            except Exception as e:
                log.warning("arbitrage_system.oanda_failed", error=str(e))

        self.active_connectors = active
        return OrderRouter(connectors=connectors)

    async def run(self):
        """Run the arbitrage system."""
        print("=" * 70)
        print("🤖 LIVE ARBITRAGE SYSTEM")
        print("=" * 70)
        print(f"Mode: {'🧪 DRY RUN' if self.dry_run else '💰 LIVE TRADING'}")
        print(f"Flash Loans: {'✅ Enabled' if self.enable_flash_loans else '❌ Disabled'}")
        print(f"Symbols: {', '.join(self.symbols)}")
        print(f"Min Edge: {self.config.min_edge_bps} bps")
        print("=" * 70)
        print()

        if not self.dry_run:
            print("⚠️  WARNING: LIVE TRADING ENABLED!")
            print("⚠️  Real money will be used!")
            print()
            response = input("Type 'START' to confirm: ")
            if response != "START":
                print("❌ Cancelled")
                return

        print("🔍 Starting scanner... Press Ctrl+C to stop")
        print()

        runner: FlashArbitrageRunner | None = None
        try:
            # Create price fetcher wrapper
            async def price_fetcher(symbol: Symbol):
                return await self.price_fetcher.get_price(symbol)

            # Create and run arbitrage runner
            runner = FlashArbitrageRunner(
                router=self.router,
                dex=self.dex,
                price_fetcher=price_fetcher,
                token_addresses=self.token_addresses,
                polygon_token_addresses=self.polygon_token_addresses,
                config=self.config,
                token_decimals=self.token_decimals,
                polygon_dex=self.polygon_dex,
            )

            # Optional dry-run validation of Polygon quote/decimals/protocols
            if self.config.enable_polygon and self.oneinch_api_key:
                await self._validate_polygon_quote(runner)

            await runner.run(self.symbols)

        except KeyboardInterrupt:
            print("\n\n⏹️  System stopped by user")
            stats = runner.get_stats() if runner else {}
            log.info("arbitrage_system.stopped", stats=stats)
            print(f"\n📊 Final Stats: {stats}")

        except Exception as e:
            print(f"\n\n❌ System error: {e}")
            log.exception("arbitrage_system.error")
            raise

    async def _validate_polygon_quote(self, runner: FlashArbitrageRunner) -> None:
        """Fetch a single 1inch Polygon quote to confirm decimals/protocols."""
        target_symbol = next((s for s in self.symbols if "/" in s), None)
        if not target_symbol:
            return
        base, quote = target_symbol.split("/", 1)
        token_in = self.polygon_token_addresses.get(quote)
        token_out = self.polygon_token_addresses.get(base)
        if not token_in or not token_out:
            return

        data = await runner._maybe_fetch_polygon_quote(
            symbol=target_symbol,
            base_symbol=base,
            quote_symbol=quote,
            token_in=token_in,
            token_out=token_out,
            amount_in=Decimal("1"),
        )
        if data:
            log.info(
                "arbitrage_system.polygon_quote_validation",
                symbol=target_symbol,
                price=data["price"],
                dst_decimals=data["metadata"].get("dst_decimals"),
                protocols=data["metadata"].get("protocols"),
            )

    @staticmethod
    def _parse_float_env(key: str) -> float | None:
        raw = os.getenv(key)
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None


async def main():
    """Main entry point."""

    # Parse command line arguments
    dry_run = "--live" not in sys.argv
    enable_flash = "--no-flash" not in sys.argv

    if not dry_run:
        print("⚠️  LIVE MODE REQUESTED")
        print()

    # Create and run system
    system = ArbitrageSystem(
        dry_run=dry_run,
        enable_flash_loans=enable_flash,
    )

    await system.run()


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("💰 ARBITRAGE SYSTEM - MAINNET")
    print("=" * 70)
    print()
    print("Usage:")
    print("  python run_live_arbitrage.py           # Dry run mode (safe)")
    print("  python run_live_arbitrage.py --live    # Live trading (⚠️  real money!)")
    print("  python run_live_arbitrage.py --no-flash # Disable flash loans")
    print()

    asyncio.run(main())
