Run comprehensive system health check:

1. Test RPC connectivity (Ethereum + Polygon) - report block numbers and latency
2. Validate CEX APIs (Kraken, Alpaca) - fetch ETH/USDC price from each
3. Test DEX quotes (Uniswap V3, 1inch) - verify WETH/USDC quote on both chains
4. Check gas oracle functionality - display current gas prices
5. Verify flash loan executor initialization
6. Display current config from .env (MIN_EDGE_BPS, GAS_PRICE_CAP_*, DRY_RUN)

Report results in compact table format. Flag any failures as critical.
