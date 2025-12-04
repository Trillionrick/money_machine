Debug specific arbitrage trade execution:

Ask user for trade details or recent timestamp.

Then:
1. Search logs for trade execution events
2. Reconstruct trade flow:
   - Price quotes (CEX vs DEX)
   - Gas estimation
   - Transaction simulation result
   - Execution attempt (if any)
   - Final outcome
3. Identify failure point if trade didn't execute:
   - Insufficient edge after gas?
   - Slippage exceeded?
   - RPC failure?
   - Gas price spike?
4. Calculate what edge would have been needed for profitability
5. Recommend: config adjustments or wait for better opportunity

Use structured logs from src/live/arbitrage_runner.py.
