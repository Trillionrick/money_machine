"""Core trading system types, protocols, and math."""

from src.core.execution import (
    ExecutionEngine,
    Fill,
    Order,
    OrderType,
    Side,
)
from src.core.policy import (
    MarketSnapshot,
    Policy,
    PortfolioState,
)
from src.core.regime import (
    AdaptiveSizer,
    MarketRegime,
    RegimeDetector,
)
from src.core.risk import (
    RiskLimits,
    RiskManager,
    RiskMetrics,
    RiskViolation,
)
from src.core.sizing import (
    LogUtility,
    TargetUtility,
    Utility,
    fractional_kelly,
    kelly_with_ruin,
)

__all__ = [
    # Execution
    "ExecutionEngine",
    "Fill",
    "Order",
    "OrderType",
    "Side",
    # Policy
    "MarketSnapshot",
    "Policy",
    "PortfolioState",
    # Regime
    "AdaptiveSizer",
    "MarketRegime",
    "RegimeDetector",
    # Risk
    "RiskLimits",
    "RiskManager",
    "RiskMetrics",
    "RiskViolation",
    # Sizing
    "LogUtility",
    "TargetUtility",
    "Utility",
    "fractional_kelly",
    "kelly_with_ruin",
]
