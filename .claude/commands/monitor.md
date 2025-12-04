Start live arbitrage monitoring (no execution):

1. Initialize ArbitrageSystem with DRY_RUN=true
2. Start continuous scan loop (5s interval)
3. Stream results to terminal in real-time:
   - Timestamp
   - Symbol
   - CEX price | DEX price | Edge (bps)
   - Profitable? (✓/✗)
   - Reason if not executable
4. Run dashboard WebSocket server on localhost:8080 concurrently
5. Display: opportunity count per minute, best edge seen
6. Stop gracefully on Ctrl+C

Use src/live/arbitrage_runner.py. This is safe - no trades executed.
