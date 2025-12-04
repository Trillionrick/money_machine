Simulate flash loan arbitrage execution:

1. Initialize FlashLoanExecutor (src/dex/flash_loan_executor.py)
2. Ask user: borrow amount ETH, target pair, expected edge bps
3. Construct arbitrage path:
   - Borrow WETH from Aave V3
   - Swap on DEX (quote from Uniswap)
   - Buy on CEX (simulated)
   - Repay loan + fee
4. Calculate:
   - Total gas cost (~300k gas units)
   - Flash loan fee (0.09%)
   - Net profit after all costs
5. Simulate transaction (eth_call, no broadcast)
6. Display: profit/loss, breakeven edge, execution risk

Contract: 0x8d2DF8b754154A3c16338353Ad9f7875B210D9B0
