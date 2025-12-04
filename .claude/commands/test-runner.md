Run arbitrage system test suite:

1. Execute: pytest tests/ -v --asyncio-mode=auto
2. Focus on critical paths:
   - tests/test_arbitrage.py (core logic)
   - tests/test_price_fetcher.py (CEX integration)
   - tests/test_flash_loan.py (flash loan simulation)
   - tests/test_rpc_failover.py (RPC circuit breakers)
3. Report: pass/fail count, coverage percentage
4. If failures: display first 3 failure tracebacks
5. Check for deprecation warnings (Python/library updates)

Run from project root. Virtual environment must be activated.
