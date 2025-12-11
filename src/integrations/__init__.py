"""
Integration modules for connecting AI arbitrage system with brokers and exchanges.

Provides bridges between AI decision systems and execution platforms:
- AlpacaAIBridge: Traditional equities/crypto via Alpaca
- Future: KrakenAIBridge, BybitAIBridge, etc.

Usage:
    from src.integrations import AlpacaAIBridge, create_bridge

    bridge = create_bridge("alpaca", alpaca_adapter=adapter)
    analysis = await bridge.analyze_opportunity("SPY", 450.0, 449.5)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import structlog

from src.integrations.alpaca_ai_bridge import AlpacaAIBridge

log = structlog.get_logger()

__version__ = "1.0.0"
__all__ = [
    "AlpacaAIBridge",
    "BridgeProtocol",
    "IntegrationError",
    "BridgeNotFoundError",
    "ExecutionError",
    "create_bridge",
    "list_available_bridges",
]


# Exceptions
class IntegrationError(Exception):
    """Base exception for integration-related errors."""
    pass


class BridgeNotFoundError(IntegrationError):
    """Raised when requested bridge type is not available."""
    pass


class ExecutionError(IntegrationError):
    """Raised when trade execution fails."""
    pass


# Protocol for all bridge implementations
@runtime_checkable
class BridgeProtocol(Protocol):
    """Protocol that all broker-AI bridges must implement."""

    async def analyze_opportunity(
        self,
        symbol: str,
        cex_price: float,
        dex_price: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Analyze arbitrage opportunity using AI.

        Args:
            symbol: Trading symbol
            cex_price: Centralized exchange price
            dex_price: Decentralized exchange price
            **kwargs: Additional parameters

        Returns:
            Analysis dict with keys: should_trade, confidence, net_profit_quote
        """
        ...

    async def execute_arbitrage_trade(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        order_type: str = "market",
        limit_price: float | None = None,
        ai_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute arbitrage trade.

        Args:
            symbol: Trading symbol
            direction: 'buy' or 'sell'
            quantity: Trade quantity
            order_type: 'market' or 'limit'
            limit_price: Price for limit orders
            ai_metadata: AI decision metadata

        Returns:
            Execution result dict with success status
        """
        ...

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get trading performance metrics.

        Returns:
            Dict with total_trades, success_rate, etc.
        """
        ...


# Bridge registry
_BRIDGE_REGISTRY: dict[str, type[BridgeProtocol]] = {
    "alpaca": AlpacaAIBridge,
}


def create_bridge(
    bridge_type: str,
    **kwargs: Any,
) -> BridgeProtocol:
    """Factory function to create bridge instances.

    Args:
        bridge_type: Type of bridge ('alpaca', 'kraken', etc.)
        **kwargs: Bridge-specific initialization parameters

    Returns:
        Initialized bridge instance

    Raises:
        BridgeNotFoundError: If bridge type not registered

    Example:
        >>> from src.brokers.alpaca_adapter import AlpacaAdapter
        >>> adapter = AlpacaAdapter(api_key="...", secret="...", paper=True)
        >>> bridge = create_bridge("alpaca", alpaca_adapter=adapter)
        >>> await bridge.analyze_opportunity("SPY", 450.0, 449.5)
    """
    bridge_type = bridge_type.lower()

    if bridge_type not in _BRIDGE_REGISTRY:
        available = ", ".join(_BRIDGE_REGISTRY.keys())
        raise BridgeNotFoundError(
            f"Bridge type '{bridge_type}' not found. "
            f"Available: {available}"
        )

    bridge_class = _BRIDGE_REGISTRY[bridge_type]

    try:
        bridge = bridge_class(**kwargs)
        log.info(
            "integration.bridge_created",
            bridge_type=bridge_type,
            bridge_class=bridge_class.__name__,
        )
        return bridge
    except TypeError as e:
        raise IntegrationError(
            f"Failed to initialize {bridge_type} bridge: {e}"
        ) from e


def list_available_bridges() -> list[str]:
    """Get list of available bridge types.

    Returns:
        List of registered bridge type names

    Example:
        >>> list_available_bridges()
        ['alpaca']
    """
    return sorted(_BRIDGE_REGISTRY.keys())


def register_bridge(
    name: str,
    bridge_class: type[BridgeProtocol],
) -> None:
    """Register a new bridge type (for extensibility).

    Args:
        name: Bridge identifier (e.g., 'kraken')
        bridge_class: Bridge class implementing BridgeProtocol

    Example:
        >>> class KrakenAIBridge:
        ...     # Implementation
        >>> register_bridge("kraken", KrakenAIBridge)
    """
    name = name.lower()

    if not isinstance(bridge_class, type):
        raise ValueError(f"bridge_class must be a class, got {type(bridge_class)}")

    _BRIDGE_REGISTRY[name] = bridge_class
    log.info(
        "integration.bridge_registered",
        name=name,
        class_name=bridge_class.__name__,
    )


__all__.append("register_bridge")
