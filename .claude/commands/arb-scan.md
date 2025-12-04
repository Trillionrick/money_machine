Execute single arbitrage scan cycle in dry-run mode:

1. Initialize ArbitrageSystem with current config
2. Scan primary pairs: ETH/USDC, WETH/USDC, BTC/USDT, USDT/USDC
3. For each opportunity found:
   - Display: symbol, CEX price, DEX price, edge (bps), estimated profit (USD)
   - Calculate: gas cost, net profit after fees
   - Determine: executable (yes/no with reason)
4. Summary: total opportunities, profitable count, best edge found

Use src/core/arbitrage.py. Do not execute trades.
