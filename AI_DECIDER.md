## AI Decider (Off-Chain Brain) - How to Use

This is a lightweight scaffold to let an external AI service score opportunities and (optionally) trigger flash-loan execution.

### Endpoints

- `POST /api/ai/score`
  - Body:
    ```json
    {
      "execute": false,
      "candidates": [
        {
          "symbol": "ETH/USDC",
          "edge_bps": 55.0,
          "notional_quote": 20000,
          "gas_cost_quote": 50,
          "flash_fee_quote": 10,
          "slippage_quote": 25,
          "cex_price": 2405.12,
          "dex_price": 2392.88,
          "confidence": 0.7,
          "chain": "ethereum"
        }
      ]
    }
    ```
  - Response: `{"decision": {...}, "executed": bool, "execution_result": {...}}`
  - Set `"execute": true` to hand the best decision to the running scanner (only works when the scanner is running, flash loans enabled, and execution enabled).

### Runtime Config (env)

- `AI_MIN_PROFIT_ETH` (default: `MIN_FLASH_PROFIT_ETH` or `0.05`)
- `AI_CONFIDENCE_THRESHOLD` (default: `0.6`)
- `AI_MAX_GAS_GWEI` (default: `MAX_GAS_PRICE_GWEI` or `120`)

### Flow to Test Safely

1. Keep `Dry run` ON in the dashboard.
2. Start the scanner (`/api/start` or the UI).
3. POST candidates to `/api/ai/score` (execute=false) and review the returned decision.
4. When ready to simulate execution, set `execute=true` (still in dry run to avoid on-chain calls).
5. For live trading: fund gas, turn OFF dry run, keep auto-execute ON, and call `/api/ai/score` with `execute=true` for flash-loan candidates.

### Notes

- The decider uses a simple heuristic today. Swap in an ML/RL model later by replacing the scoring inside `src/ai/decider.py`.
- Execution path uses the existing flash-loan pipeline (`FlashArbitrageRunner.execute_ai_flash_decision`) and re-runs profitability checks on-chain.
- The dashboard “Apply Config” now forwards AI inputs (`ai_min_profit_eth`, `ai_confidence_threshold`, `ai_max_gas_gwei`) to the backend so your off-chain decider can react to UI changes.
- `ai_min_profit_eth` and `ai_max_gas_gwei` also synchronize into the on-chain config: `min_flash_profit_eth` and Ethereum gas cap respectively. The confidence threshold remains off-chain only.
- Gas-aware prefilter: candidates with non-positive net after costs (gas + flash_fee + slippage) are dropped; optional hop penalty (`hop_penalty_quote`) can reduce net for multi-hop routes. Provide `hop_count` in candidates to inform the scorer.
- Dashboard AI field added: `AI hop penalty (quote units)` updates `ai_hop_penalty_quote` for penalizing multi-hop routes; sent via Apply Config.
