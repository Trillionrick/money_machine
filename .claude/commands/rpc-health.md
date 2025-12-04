Check RPC failover system status:

1. Import PolygonRPCManager from src/core/rpc_failover.py
2. Get health status: circuit_state, health_scores, consecutive_failures for each endpoint
3. Display current active endpoint
4. Show recent failure history (if any)
5. Test latency to all configured endpoints
6. Recommend: reset circuits if needed, add new endpoints if all degraded

This addresses the 2024-12-02 1inch 500 error issue.
