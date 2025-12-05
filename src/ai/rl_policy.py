"""Reinforcement Learning-based trading policy for arbitrage execution.

Implements intelligent trading strategy using:
- Q-learning for action selection (buy/sell/hold decisions)
- State representation (market conditions, positions, edge quality)
- Reward shaping (profit - costs + execution success bonus)
- Experience replay for stable learning
- Epsilon-greedy exploration with decay
"""

from __future__ import annotations

import pickle
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import msgspec
import numpy as np
import polars as pl
import structlog

from src.core.execution import Order, OrderSeq, OrderType, Side
from src.core.policy import MarketSnapshot, PortfolioState
from src.core.types import ContextMap, Symbol

log = structlog.get_logger()

Action = Literal["buy", "sell", "hold", "flash_arb"]
State = tuple[float, float, float, float, float, float]  # 6-dim state vector


@dataclass
class RLPolicyConfig:
    """Configuration for RL-based trading policy."""

    # Learning parameters
    learning_rate: float = 0.01  # Q-learning alpha
    discount_factor: float = 0.95  # Gamma for future rewards
    epsilon_start: float = 0.30  # Initial exploration rate
    epsilon_end: float = 0.05  # Final exploration rate
    epsilon_decay: float = 0.9995  # Decay per step

    # Experience replay
    replay_buffer_size: int = 10_000
    batch_size: int = 32
    min_replay_size: int = 100  # Min experiences before learning

    # Trading constraints
    max_position_size: float = 10.0  # Max position per symbol (ETH)
    min_edge_bps: float = 25.0  # Minimum edge to consider trading
    max_leverage: float = 3.0  # Maximum flash loan leverage

    # Reward shaping
    profit_reward_scale: float = 100.0  # Scale profits to [-1, 1] range
    execution_success_bonus: float = 0.1  # Bonus for successful execution
    failed_execution_penalty: float = -0.2  # Penalty for failed execution
    holding_cost: float = -0.001  # Small penalty for holding positions

    # Model persistence
    model_path: Path = field(default_factory=lambda: Path("models/rl_policy_model.pkl"))
    save_frequency: int = 100  # Save model every N episodes

    # Target symbols
    target_symbols: list[Symbol] = field(
        default_factory=lambda: ["ETH/USDC", "WETH/USDC", "BTC/USDT", "WBTC/USDC"]
    )


@dataclass
class Experience:
    """Single experience tuple for replay buffer."""

    state: State
    action: Action
    reward: float
    next_state: State
    done: bool
    symbol: Symbol


class QNetwork:
    """Q-function approximator using tabular Q-learning.

    For production, would use deep neural network (DQN), but tabular Q-learning
    is simpler and works well for discrete state/action spaces.
    """

    def __init__(self, state_bins: tuple[int, ...], actions: list[Action]):
        """Initialize Q-network.

        Args:
            state_bins: Number of bins for discretizing each state dimension
            actions: List of possible actions
        """
        self.state_bins = state_bins
        self.actions = actions
        self.action_to_idx = {a: i for i, a in enumerate(actions)}
        self.idx_to_action = {i: a for i, a in enumerate(actions)}

        # Q-table: state -> action -> Q-value
        # For tabular, we use a dictionary
        self.q_table: dict[tuple, np.ndarray] = {}

    def discretize_state(self, state: State) -> tuple:
        """Discretize continuous state to discrete bins."""
        # State dimensions:
        # 0: edge_bps (0-200 bps)
        # 1: position_pct (-1 to 1)
        # 2: portfolio_health (0-1)
        # 3: volatility (0-1)
        # 4: gas_percentile (0-1)
        # 5: liquidity (0-1)

        bins = [
            np.clip(int(state[0] / 20), 0, self.state_bins[0] - 1),  # edge: 20 bps per bin
            np.clip(
                int((state[1] + 1) * self.state_bins[1] / 2), 0, self.state_bins[1] - 1
            ),  # position
            np.clip(int(state[2] * self.state_bins[2]), 0, self.state_bins[2] - 1),  # health
            np.clip(int(state[3] * self.state_bins[3]), 0, self.state_bins[3] - 1),  # volatility
            np.clip(int(state[4] * self.state_bins[4]), 0, self.state_bins[4] - 1),  # gas
            np.clip(int(state[5] * self.state_bins[5]), 0, self.state_bins[5] - 1),  # liquidity
        ]

        return tuple(bins)

    def get_q_values(self, state: State) -> np.ndarray:
        """Get Q-values for all actions in given state."""
        discrete_state = self.discretize_state(state)

        if discrete_state not in self.q_table:
            # Initialize with small random values
            self.q_table[discrete_state] = np.random.randn(len(self.actions)) * 0.01

        return self.q_table[discrete_state]

    def get_best_action(self, state: State) -> Action:
        """Get action with highest Q-value for given state."""
        q_values = self.get_q_values(state)
        best_idx = int(np.argmax(q_values))
        return self.idx_to_action[best_idx]

    def update(self, state: State, action: Action, target: float, learning_rate: float) -> None:
        """Update Q-value for state-action pair."""
        discrete_state = self.discretize_state(state)
        action_idx = self.action_to_idx[action]

        if discrete_state not in self.q_table:
            self.q_table[discrete_state] = np.zeros(len(self.actions))

        # Q-learning update: Q(s,a) += α * (target - Q(s,a))
        current_q = self.q_table[discrete_state][action_idx]
        self.q_table[discrete_state][action_idx] = current_q + learning_rate * (target - current_q)


class RLArbitragePolicy:
    """Reinforcement learning-based arbitrage policy.

    Uses Q-learning to learn optimal trading strategy from experience.
    The policy observes market conditions and portfolio state, then selects
    actions (buy/sell/hold/flash_arb) to maximize cumulative profit.

    Key features:
    - State: edge quality, position, portfolio health, market regime
    - Actions: buy, sell, hold, flash_arb
    - Rewards: profit - costs + execution bonuses
    - Learning: Q-learning with experience replay
    """

    def __init__(self, config: RLPolicyConfig | None = None):
        """Initialize RL policy."""
        self.config = config or RLPolicyConfig()

        # Q-network
        self.actions: list[Action] = ["buy", "sell", "hold", "flash_arb"]
        state_bins = (10, 10, 10, 5, 5, 5)  # Bins for each state dimension
        self.q_network = QNetwork(state_bins, self.actions)

        # Experience replay buffer
        self.replay_buffer: deque[Experience] = deque(maxlen=self.config.replay_buffer_size)

        # Exploration parameters
        self.epsilon = self.config.epsilon_start
        self.steps = 0
        self.episodes = 0

        # Performance tracking
        self.total_reward = 0.0
        self.episode_rewards: list[float] = []

        # Load pre-trained model if exists
        if self.config.model_path.exists():
            self._load_model()

        log.info(
            "rl_policy.initialized",
            actions=self.actions,
            target_symbols=self.config.target_symbols,
        )

    def decide(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
        context: ContextMap | None = None,
    ) -> OrderSeq:
        """Generate orders using RL policy.

        Args:
            portfolio: Current portfolio state
            snapshot: Current market data
            context: Optional context (can contain edge predictions, etc.)

        Returns:
            Sequence of orders to execute
        """
        orders: list[Order] = []

        for symbol in self.config.target_symbols:
            # Extract state features
            state = self._extract_state(portfolio, snapshot, symbol, context)

            # Select action using epsilon-greedy
            action = self._select_action(state)

            # Generate order based on action
            order = self._action_to_order(action, symbol, snapshot, portfolio)

            if order:
                orders.append(order)

            # Increment step counter
            self.steps += 1
            self._decay_epsilon()

        return orders

    def on_fill(self, fill: msgspec.Struct) -> None:
        """Handle order fill - record experience for learning.

        Args:
            fill: Order fill information
        """
        # Extract reward from fill
        # This is simplified - real implementation would track P&L
        # For now, we use fill price vs expected price as reward signal

        # TODO: Implement proper experience recording when fill format is known
        log.debug("rl_policy.fill_received")

    def _extract_state(
        self,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot,
        symbol: Symbol,
        context: ContextMap | None,
    ) -> State:
        """Extract state vector from portfolio and market data.

        State dimensions (6):
        1. edge_bps: Current arbitrage edge (0-200)
        2. position_pct: Position as % of max (-1 to 1)
        3. portfolio_health: Portfolio health metric (0-1)
        4. volatility: Market volatility indicator (0-1)
        5. gas_percentile: Current gas price percentile (0-1)
        6. liquidity: Route liquidity score (0-1)
        """
        # 1. Edge from context (if available)
        edge_bps = 0.0
        if context and "edges" in context:
            edge_bps = context["edges"].get(symbol, 0.0)  # type: ignore

        # 2. Current position
        position = portfolio.position(symbol)
        position_pct = position / self.config.max_position_size

        # 3. Portfolio health
        portfolio_health = min(1.0, portfolio.equity / max(1.0, portfolio.cash))

        # 4. Volatility (from snapshot features if available)
        volatility = 0.5  # default
        if snapshot.features is not None and "volatility" in snapshot.features.columns:
            try:
                vol_series = snapshot.features.filter(pl.col("symbol") == symbol)["volatility"]
                if len(vol_series) > 0:
                    volatility = float(vol_series[0])
            except Exception:
                pass

        # 5. Gas percentile (from context)
        gas_percentile = 0.5  # default
        if context and "gas_percentile" in context:
            gas_percentile = float(context["gas_percentile"])  # type: ignore

        # 6. Liquidity (from context)
        liquidity = 0.7  # default good liquidity
        if context and "liquidity" in context:
            liquidity = context["liquidity"].get(symbol, 0.7)  # type: ignore

        state: State = (
            float(edge_bps),
            float(np.clip(position_pct, -1.0, 1.0)),
            float(np.clip(portfolio_health, 0.0, 1.0)),
            float(np.clip(volatility, 0.0, 1.0)),
            float(np.clip(gas_percentile, 0.0, 1.0)),
            float(np.clip(liquidity, 0.0, 1.0)),
        )

        return state

    def _select_action(self, state: State) -> Action:
        """Select action using epsilon-greedy policy."""
        if np.random.rand() < self.epsilon:
            # Explore: random action
            return np.random.choice(self.actions)  # type: ignore
        else:
            # Exploit: best action from Q-network
            return self.q_network.get_best_action(state)

    def _action_to_order(
        self,
        action: Action,
        symbol: Symbol,
        snapshot: MarketSnapshot,
        portfolio: PortfolioState,
    ) -> Order | None:
        """Convert action to order.

        Args:
            action: Selected action
            symbol: Trading symbol
            snapshot: Market snapshot
            portfolio: Portfolio state

        Returns:
            Order object or None if no order
        """
        price = snapshot.price(symbol)
        if not price or price <= 0:
            return None

        current_position = portfolio.position(symbol)

        if action == "buy":
            # Buy if we don't have max position
            if current_position < self.config.max_position_size:
                # Calculate order size (10% of remaining capacity)
                size = (self.config.max_position_size - current_position) * 0.1
                return Order(
                    symbol=symbol,
                    quantity=size,
                    side=Side.BUY,
                    order_type=OrderType.MARKET,
                )

        elif action == "sell":
            # Sell if we have a position
            if current_position > 0:
                # Sell 10% of position
                size = current_position * 0.1
                return Order(
                    symbol=symbol,
                    quantity=size,
                    side=Side.SELL,
                    order_type=OrderType.MARKET,
                )

        elif action == "flash_arb":
            # Flash arbitrage opportunity
            # This would trigger flash loan execution
            # For now, return None (would integrate with flash executor)
            log.info("rl_policy.flash_arb_signal", symbol=symbol)
            return None

        # action == "hold" or no valid order
        return None

    def _decay_epsilon(self) -> None:
        """Decay exploration rate."""
        self.epsilon = max(
            self.config.epsilon_end, self.epsilon * self.config.epsilon_decay
        )

    def record_experience(
        self,
        state: State,
        action: Action,
        reward: float,
        next_state: State,
        done: bool,
        symbol: Symbol,
    ) -> None:
        """Record experience for replay learning."""
        exp = Experience(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=done,
            symbol=symbol,
        )
        self.replay_buffer.append(exp)

        # Update total reward
        self.total_reward += reward

        # Learn from experience replay
        if len(self.replay_buffer) >= self.config.min_replay_size:
            self._learn_from_replay()

    def _learn_from_replay(self) -> None:
        """Sample from replay buffer and update Q-network."""
        if len(self.replay_buffer) < self.config.batch_size:
            return

        # Sample random batch
        indices = np.random.choice(
            len(self.replay_buffer), size=self.config.batch_size, replace=False
        )
        batch = [self.replay_buffer[i] for i in indices]

        # Update Q-values for each experience
        for exp in batch:
            # Calculate target
            if exp.done:
                target = exp.reward
            else:
                # Q-learning: target = reward + γ * max_a' Q(s', a')
                next_q_values = self.q_network.get_q_values(exp.next_state)
                target = exp.reward + self.config.discount_factor * np.max(next_q_values)

            # Update Q-network
            self.q_network.update(
                exp.state, exp.action, target, self.config.learning_rate
            )

    def end_episode(self, episode_reward: float) -> None:
        """Mark end of episode and save model periodically."""
        self.episodes += 1
        self.episode_rewards.append(episode_reward)

        # Save model periodically
        if self.episodes % self.config.save_frequency == 0:
            self._save_model()

        log.info(
            "rl_policy.episode_complete",
            episode=self.episodes,
            reward=episode_reward,
            epsilon=self.epsilon,
            avg_reward=np.mean(self.episode_rewards[-100:]) if self.episode_rewards else 0.0,
        )

    def _save_model(self) -> None:
        """Save Q-network to disk."""
        self.config.model_path.parent.mkdir(parents=True, exist_ok=True)

        checkpoint = {
            "q_table": self.q_network.q_table,
            "epsilon": self.epsilon,
            "steps": self.steps,
            "episodes": self.episodes,
            "episode_rewards": self.episode_rewards,
        }

        with open(self.config.model_path, "wb") as f:
            pickle.dump(checkpoint, f)

        log.info("rl_policy.model_saved", path=str(self.config.model_path))

    def _load_model(self) -> None:
        """Load pre-trained Q-network from disk."""
        try:
            with open(self.config.model_path, "rb") as f:
                checkpoint = pickle.load(f)

            self.q_network.q_table = checkpoint["q_table"]
            self.epsilon = checkpoint["epsilon"]
            self.steps = checkpoint["steps"]
            self.episodes = checkpoint["episodes"]
            self.episode_rewards = checkpoint["episode_rewards"]

            log.info(
                "rl_policy.model_loaded",
                path=str(self.config.model_path),
                episodes=self.episodes,
            )
        except Exception:
            log.exception("rl_policy.load_failed")

    def get_stats(self) -> dict:
        """Get RL policy statistics."""
        return {
            "episodes": self.episodes,
            "steps": self.steps,
            "epsilon": self.epsilon,
            "total_reward": self.total_reward,
            "avg_episode_reward": (
                np.mean(self.episode_rewards[-100:]) if self.episode_rewards else 0.0
            ),
            "replay_buffer_size": len(self.replay_buffer),
            "q_table_size": len(self.q_network.q_table),
        }
