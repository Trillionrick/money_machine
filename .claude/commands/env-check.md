Validate .env configuration:

1. Read .env file (do not display secrets)
2. Check presence of required variables:
   - ETHEREUM_RPC_URL or ETH_RPC_URL
   - POLYGON_RPC_URL
   - KRAKEN_API_KEY + KRAKEN_API_SECRET
   - ALPACA_API_KEY + ALPACA_API_SECRET (if used)
   - PRIVATE_KEY or WALLET_PRIVATE_KEY
3. Validate format:
   - RPC URLs start with https://
   - Private key is 64 hex chars (without 0x) or 66 with 0x
   - API keys not empty strings
4. Check optional but recommended:
   - THEGRAPH_API_KEY
   - ONEINCH_API_KEY
   - MIN_EDGE_BPS (default: 25)
   - GAS_PRICE_CAP_ETH (default: 60)
5. Display: ✓ configured, ✗ missing, ⚠ using default

Security: never log actual secret values.
