Calculate optimal position size using target optimizer:

Ask user for:
- Current capital USD
- Target wealth USD
- Expected edge (basis points)
- Risk tolerance (conservative/moderate/aggressive)

Then:
1. Import TargetOptimizer from src/core/target_optimizer.py
2. Create TargetObjective with current → target path
3. Calculate optimal leverage (will be 2-5x Kelly)
4. Run Monte Carlo simulation (10k paths)
5. Display:
   - Recommended position size USD
   - Probability of hitting target
   - Probability of ruin
   - Expected attempts needed
   - Variance (prepare for drawdown)

Warning: This is mathematically optimal but psychologically brutal.
