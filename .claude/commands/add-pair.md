Add new trading pair to arbitrage system:

Ask user for symbol (e.g., LINK/USDC)

Then:
1. Verify pair available on Kraken/Alpaca (check via ccxt)
2. Get token addresses from Etherscan:
   - Token0 address (e.g., LINK: 0x514910771af9ca656af840dff83e8264ecf986ca)
   - Token1 address (e.g., USDC: 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48)
3. Add to src/core/arbitrage.py SUPPORTED_SYMBOLS
4. Add to TOKEN_ADDRESSES dict in dex/uniswap_connector.py
5. Test price fetch from CEX
6. Test quote from Uniswap V3 (verify pool exists)
7. Run single dry-run scan with new pair

Display: configuration changes made, test results.
