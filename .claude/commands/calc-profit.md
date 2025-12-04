Calculate arbitrage profitability for specific opportunity:

Ask user for:
- Trading pair (default: ETH/USDC)
- CEX price
- DEX price
- Trade size in USD (default: 1000)

Then compute:
1. Gross edge in bps
2. Gas cost estimate (Ethereum mainnet)
3. Slippage impact (use MAX_SLIPPAGE_BPS from config)
4. Flash loan fee (if applicable - 0.09% Aave V3)
5. Net profit USD and percentage
6. Required minimum edge for breakeven

Display: executable (yes/no), risk factors, recommended action.
