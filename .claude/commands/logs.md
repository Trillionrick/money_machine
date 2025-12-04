Analyze recent arbitrage logs:

1. Read last 100 lines from logs/arbitrage.log
2. Parse structured JSON logs (structlog format)
3. Extract key events:
   - Opportunities detected (count, avg edge)
   - Execution attempts (success/fail count)
   - RPC failures (which endpoints)
   - Gas price spikes
   - Profit realized (total USD)
4. Display timeline of significant events
5. Flag anomalies: repeated failures, abnormal gas costs, RPC degradation

Use: tail -100 logs/arbitrage.log | jq for parsing.
