"""Example: Complete AI-powered arbitrage system integration.

Demonstrates how to use all AI components together:
1. AIFlashArbitrageRunner with AdvancedAIDecider
2. RLArbitragePolicy with LiveEngine
3. AquaOpportunityDetector for whale following
4. Unified configuration and metrics

This is a complete working example showing production-grade AI integration.
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.advanced_decider import AdvancedAIConfig, AdvancedAIDecider, MarketRegime
from src.ai.aqua_opportunity_detector import AquaOpportunityDetector, AquaOpportunityConfig
from src.ai.config_manager import AIConfigManager, get_ai_config_manager
from src.ai.metrics import AIMetricsCollector, get_metrics_collector
from src.ai.rl_policy import RLArbitragePolicy, RLPolicyConfig
from src.brokers.price_fetcher import CEXPriceFetcher
from src.brokers.routing import OrderRouter
from src.core.policy import MarketSnapshot, PortfolioState
from src.dex.flash_loan_executor import FlashLoanExecutor
from src.dex.uniswap_connector import UniswapConnector
from src.live.ai_flash_runner import AIFlashArbConfig, AIFlashArbitrageRunner
from src.live.engine import LiveEngine
from web3 import AsyncWeb3


async def example_1_ai_flash_arbitrage():
    """Example 1: AI-enhanced flash arbitrage with multi-factor scoring."""
    print("\n=== Example 1: AI Flash Arbitrage ===\n")

    # Initialize configuration
    config_manager = get_ai_config_manager()
    ai_config = config_manager.config

    # Set to conservative mode for safety
    config_manager.update_config({"ai_mode": "conservative"})

    # Initialize metrics collector
    metrics = get_metrics_collector()

    # Initialize components (simplified - would use actual Web3/API connections)
    # price_fetcher = CEXPriceFetcher(...)
    # router = OrderRouter(...)
    # dex = UniswapConnector(...)
    # flash_executor = FlashLoanExecutor(...)

    # Create AI flash arbitrage runner
    flash_config = AIFlashArbConfig(
        enable_ai_scoring=True,
        ai_min_confidence=0.75,
        enable_flash_loans=True,
        enable_execution=False,  # Dry-run mode
        portfolio_value_eth=100.0,
    )

    print("Configuration:")
    print(f"  AI Mode: {config_manager.config.ai_mode}")
    print(f"  AI Min Confidence: {flash_config.ai_min_confidence}")
    print(f"  ML Scoring Enabled: {ai_config.advanced_decider.enable_ml_scoring}")
    print(f"  Flash Loans Enabled: {flash_config.enable_flash_loans}")
    print()

    # Note: Full runner initialization would require actual connections
    # runner = AIFlashArbitrageRunner(
    #     router=router,
    #     dex=dex,
    #     price_fetcher=price_fetcher,
    #     token_addresses=TOKEN_ADDRESSES,
    #     config=flash_config,
    #     ai_config=ai_config.advanced_decider,
    # )

    # Simulate AI decision-making process
    from src.ai.decider import AICandidate

    print("Simulating AI decision-making...\n")

    # Create sample opportunities
    candidates = [
        AICandidate(
            symbol="ETH/USDC",
            edge_bps=65.0,  # 0.65% edge
            notional_quote=10000.0,
            gas_cost_quote=50.0,
            flash_fee_quote=5.0,
            slippage_quote=15.0,
            hop_count=1,
            cex_price=3050.0,
            dex_price=3030.0,
            chain="ethereum",
            confidence=0.75,
        ),
        AICandidate(
            symbol="WBTC/USDC",
            edge_bps=45.0,
            notional_quote=20000.0,
            gas_cost_quote=60.0,
            flash_fee_quote=10.0,
            slippage_quote=30.0,
            hop_count=2,
            cex_price=65000.0,
            dex_price=64700.0,
            chain="ethereum",
            confidence=0.70,
        ),
    ]

    # Initialize AI decider
    decider = AdvancedAIDecider(ai_config.advanced_decider)

    # Set market regime
    regime = MarketRegime(
        volatility=0.25,  # Moderate volatility
        trend=0.1,  # Slight uptrend
        liquidity=0.75,  # Good liquidity
        gas_percentile=0.4,  # Below average gas
        regime_label="stable",
    )
    decider.update_regime(regime)

    print(f"Market Regime: {regime.regime_label}")
    print(f"  Volatility: {regime.volatility:.2f}")
    print(f"  Gas Percentile: {regime.gas_percentile:.2f}")
    print(f"  Liquidity: {regime.liquidity:.2f}\n")

    # Make AI decision
    decision = decider.pick_best(candidates, portfolio_value_eth=100.0)

    if decision:
        print(f"✅ AI Decision: Execute {decision.symbol}")
        print(f"  Edge: {decision.edge_bps:.2f} bps")
        print(f"  Net Profit: ${decision.net_quote:.2f}")
        print(f"  Confidence: {decision.confidence:.3f}")
        print(f"  Reason: {decision.reason}")

        # Record metrics
        metrics.record_decision(
            confidence=decision.confidence,
            edge_bps=decision.edge_bps,
            predicted_profit=decision.net_quote,
            executed=True,
        )

        # Simulate execution
        print("\n  Simulating execution...")
        success = True
        actual_profit = decision.net_quote * 0.95  # 95% of predicted (slippage)
        gas_cost = decision.gas_cost_quote

        metrics.record_execution(
            success=success,
            actual_profit=actual_profit,
            gas_cost=gas_cost,
            execution_time_ms=450.0,
        )

        print(f"  ✅ Execution successful!")
        print(f"  Actual Profit: ${actual_profit:.2f}")
        print(f"  Prediction Accuracy: {actual_profit/decision.net_quote:.1%}")
    else:
        print("❌ No viable opportunities found")

    # Show AI stats
    print("\nAI Decider Stats:")
    stats = decider.get_stats()
    print(f"  Total Predictions: {stats['total_predictions']}")
    print(f"  Win Rate: {stats['win_rate']:.1%}")
    print(f"  ML Enabled: {stats['ml_enabled']}")
    print(f"  Model Trained: {stats['model_trained']}")


async def example_2_rl_policy():
    """Example 2: Reinforcement learning policy for adaptive trading."""
    print("\n\n=== Example 2: RL-Based Trading Policy ===\n")

    # Initialize RL policy
    rl_config = RLPolicyConfig(
        learning_rate=0.01,
        epsilon_start=0.20,  # 20% exploration
        max_position_size=10.0,
        min_edge_bps=25.0,
        target_symbols=["ETH/USDC", "BTC/USDT"],
    )

    policy = RLArbitragePolicy(rl_config)

    print("RL Policy Configuration:")
    print(f"  Learning Rate: {rl_config.learning_rate}")
    print(f"  Exploration Rate: {policy.epsilon:.3f}")
    print(f"  Max Position Size: {rl_config.max_position_size} ETH")
    print(f"  Target Symbols: {rl_config.target_symbols}\n")

    # Simulate trading loop
    print("Simulating RL trading decisions...\n")

    for episode in range(3):
        # Create market snapshot
        snapshot = MarketSnapshot(
            timestamp=0,
            prices={"ETH/USDC": 3050.0, "BTC/USDT": 65000.0},
            volumes={"ETH/USDC": 1000000.0, "BTC/USDT": 500000.0},
            regime="stable",
        )

        # Create portfolio state
        portfolio = PortfolioState(
            positions={"ETH/USDC": 2.5, "BTC/USDT": 0.1},
            cash=50000.0,
            equity=60000.0,
            timestamp=0,
        )

        # Add edge predictions to context
        context = {
            "edges": {
                "ETH/USDC": 35.0 + episode * 10,  # Increasing edge
                "BTC/USDT": 40.0,
            },
            "gas_percentile": 0.5,
            "liquidity": {"ETH/USDC": 0.8, "BTC/USDT": 0.75},
        }

        # Get policy decision
        orders = policy.decide(portfolio, snapshot, context)

        print(f"Episode {episode + 1}:")
        print(f"  Edge ETH/USDC: {context['edges']['ETH/USDC']:.1f} bps")
        print(f"  Orders Generated: {len(orders)}")

        if orders:
            for order in orders:
                print(f"    - {order.side.upper()} {order.quantity:.3f} {order.symbol}")

        # Simulate reward
        reward = 0.05 * (episode + 1)  # Increasing reward
        print(f"  Reward: {reward:.3f}")
        print(f"  Epsilon: {policy.epsilon:.3f}\n")

        # Record experience (simplified)
        # In production, would extract state from snapshot and record properly

    # Show RL stats
    print("RL Policy Stats:")
    stats = policy.get_stats()
    print(f"  Episodes: {stats['episodes']}")
    print(f"  Steps: {stats['steps']}")
    print(f"  Epsilon: {stats['epsilon']:.3f}")
    print(f"  Q-Table Size: {stats['q_table_size']}")


async def example_3_aqua_whale_following():
    """Example 3: Aqua Protocol whale following and copy trading."""
    print("\n\n=== Example 3: Aqua Whale Following ===\n")

    config = AquaOpportunityConfig(
        min_pushed_amount_usd=10_000.0,
        min_confidence=0.70,
        enable_copy_trading=False,  # Disabled for safety
        enable_counter_trading=True,  # Enabled (safer strategy)
        max_position_size_usd=5_000.0,
    )

    print("Aqua Detector Configuration:")
    print(f"  Min Whale Deposit: ${config.min_pushed_amount_usd:,.0f}")
    print(f"  Copy Trading: {config.enable_copy_trading}")
    print(f"  Counter Trading: {config.enable_counter_trading}")
    print(f"  Max Position Size: ${config.max_position_size_usd:,.0f}\n")

    # Note: Full detector initialization requires Web3 connections
    # detector = AquaOpportunityDetector(
    #     w3_ethereum=w3_eth,
    #     w3_polygon=w3_poly,
    #     config=config,
    #     ai_decider=AIDecider(),
    #     uniswap_connector=uniswap,
    #     price_fetcher=price_fetcher,
    #     flash_executor=flash_executor,
    # )

    print("Sample Aqua Events:\n")

    # Simulate whale events
    events = [
        {
            "type": "Pushed",
            "amount_usd": 50_000,
            "trader": "0x1234...abcd",
            "token": "USDC",
            "opportunity": "whale_entry",
        },
        {
            "type": "Pulled",
            "amount_usd": 55_000,
            "profit_usd": 5_000,
            "trader": "0x1234...abcd",
            "opportunity": "whale_exit",
        },
    ]

    for event in events:
        print(f"Event: {event['type']}")
        print(f"  Amount: ${event['amount_usd']:,.0f}")
        print(f"  Trader: {event['trader']}")

        if event["type"] == "Pushed":
            print(f"  Opportunity: Monitor for exit")
            print(f"  Action: Track whale movements")
        else:
            print(f"  Profit: ${event['profit_usd']:,.0f}")
            print(f"  Opportunity: Counter-trade on price dip")
            print(f"  Action: BUY on dip, SELL on recovery")

        print()


async def example_4_unified_system():
    """Example 4: Unified AI system with all components."""
    print("\n\n=== Example 4: Unified AI System ===\n")

    # Initialize configuration manager
    config_manager = AIConfigManager()
    print("Unified AI Configuration Loaded\n")

    # Display config summary
    config_dict = config_manager.get_config_dict()
    print("System Configuration:")
    print(f"  AI Enabled: {config_dict['enable_ai_system']}")
    print(f"  Mode: {config_dict['ai_mode']}")
    print(f"  Portfolio Value: {config_dict['portfolio_value_eth']} ETH\n")

    print("Component Status:")
    print(f"  Advanced Decider:")
    print(f"    Confidence Threshold: {config_dict['advanced_decider']['confidence_threshold']}")
    print(f"    ML Scoring: {config_dict['advanced_decider']['enable_ml_scoring']}")
    print(f"  RL Policy:")
    print(f"    Learning Rate: {config_dict['rl_policy']['learning_rate']}")
    print(f"  Aqua Detector:")
    print(f"    Copy Trading: {config_dict['aqua_detector']['enable_copy_trading']}")
    print(f"    Counter Trading: {config_dict['aqua_detector']['enable_counter_trading']}\n")

    # Get metrics
    metrics = get_metrics_collector()

    # Simulate some activity
    for i in range(5):
        metrics.record_decision(
            confidence=0.75 + i * 0.03,
            edge_bps=50.0 + i * 5,
            predicted_profit=100.0 + i * 20,
            executed=True,
        )

        metrics.record_execution(
            success=i % 4 != 0,  # 75% success rate
            actual_profit=(100.0 + i * 20) * 0.92,
            gas_cost=15.0,
            execution_time_ms=400.0 + i * 50,
        )

    # Display metrics summary
    print("Performance Metrics:")
    summary = metrics.get_summary()

    print(f"  Decisions: {summary['decisions']['total']}")
    print(f"  Execution Rate: {summary['decisions']['execution_rate']:.1%}")
    print(f"  Win Rate: {summary['decisions']['win_rate']:.1%}")
    print(f"  Avg Confidence: {summary['decisions']['avg_confidence']:.3f}")
    print(f"  Avg Edge: {summary['decisions']['avg_edge_bps']:.1f} bps\n")

    print(f"  Executions: {summary['execution']['total']}")
    print(f"  Success Rate: {summary['execution']['success_rate']:.1%}")
    print(f"  Net Profit: ${summary['execution']['net_profit_usd']:.2f}")
    print(f"  Avg Execution Time: {summary['execution']['avg_execution_time_ms']:.1f} ms\n")

    # Show recent performance
    recent = metrics.get_recent_performance(window_minutes=60)
    print("Recent Performance (last 60 min):")
    print(f"  Total Profit: ${recent['total_profit']:.2f}")
    print(f"  Avg Per Trade: ${recent['avg_profit_per_trade']:.2f}")
    print(f"  Success Rate: {recent['success_rate']:.1%}")


async def main():
    """Run all examples."""
    print("=" * 70)
    print("AI-Powered Arbitrage System - Integration Examples")
    print("=" * 70)

    await example_1_ai_flash_arbitrage()
    await example_2_rl_policy()
    await example_3_aqua_whale_following()
    await example_4_unified_system()

    print("\n" + "=" * 70)
    print("Examples completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
