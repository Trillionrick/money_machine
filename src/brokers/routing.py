"""Order routing utilities for multi-venue execution.

Provides a small, testable policy layer that decides which connector
should receive an order and how to split size across venues.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

import structlog

from src.core.execution import Order, OrderSeq
from src.core.types import Symbol

log = structlog.get_logger()

# ISO-ish fiat currency codes we treat as forex when paired together.
FIAT_CODES = {
    "USD",
    "EUR",
    "JPY",
    "GBP",
    "AUD",
    "CAD",
    "CHF",
    "NZD",
    "HKD",
    "SGD",
    "CNY",
}

# Metal codes that should route like forex (OANDA supports them).
METAL_CODES = {"XAU", "XAG"}

# Common crypto bases to identify digital assets when mixed with fiat quotes.
CRYPTO_BASES = {
    "BTC",
    "ETH",
    "SOL",
    "ADA",
    "XRP",
    "LTC",
    "BNB",
    "DOT",
    "LINK",
    "DOGE",
    "AVAX",
    "ATOM",
    "MATIC",
    "UNI",
    "ETC",
    "OP",
    "ARB",
}


class AssetClass(StrEnum):
    """Asset class classification for routing decisions."""

    FOREX = "forex"
    CRYPTO = "crypto"
    UNKNOWN = "unknown"


@dataclass
class RouteTarget:
    """Target venue allocation for a single order."""

    venue: str
    weight: float  # Fraction of original order size to send to this venue
    note: str | None = None


class RoutingPolicy:
    """Interface for routing policies."""

    def targets(self, order: Order, available_venues: set[str]) -> list[RouteTarget]:
        """Return venue allocations for an order."""
        raise NotImplementedError


def _detect_asset_class(symbol: Symbol) -> AssetClass:
    """Classify a symbol into an asset class for routing."""
    normalized = symbol.replace("_", "/").upper()
    forex_bases = FIAT_CODES | METAL_CODES

    if "/" in normalized:
        base, quote = normalized.split("/", 1)
        if base in forex_bases and quote in FIAT_CODES:
            return AssetClass.FOREX
        if base in FIAT_CODES and quote in FIAT_CODES:
            return AssetClass.FOREX
        if base in CRYPTO_BASES or quote in {"USDT", "USDC", "DAI"}:
            return AssetClass.CRYPTO

    if normalized in CRYPTO_BASES:
        return AssetClass.CRYPTO

    return AssetClass.UNKNOWN


class DefaultRoutingPolicy(RoutingPolicy):
    """Simple default routing policy covering forex and crypto venues."""

    def __init__(self, *, max_venue_share: float = 0.40) -> None:
        self.max_venue_share = max_venue_share
        self.crypto_priority = ["kraken", "okx", "bybit", "coinbase", "binance"]

    def targets(self, order: Order, available_venues: set[str]) -> list[RouteTarget]:
        asset_class = _detect_asset_class(order.symbol)

        if asset_class == AssetClass.FOREX:
            return [RouteTarget("oanda", 1.0)] if "oanda" in available_venues else []

        if asset_class == AssetClass.CRYPTO:
            venues = [v for v in self.crypto_priority if v in available_venues]
            if not venues:
                return []

            allocations: list[RouteTarget] = []
            max_share = Decimal(str(self.max_venue_share))
            remaining = Decimal("1")

            for venue in venues:
                share = max_share if remaining > max_share else remaining
                allocations.append(RouteTarget(venue, float(share)))
                remaining -= share
                if remaining <= Decimal("0"):
                    break

            if remaining > Decimal("0") and allocations:
                # Not enough venues to satisfy the diversification cap; allow concentration with a note.
                allocations[0].weight = float(
                    Decimal(str(allocations[0].weight)) + remaining
                )
                allocations[0].note = (
                    allocations[0].note or "concentration_override"
                )
                log.warning(
                    "routing.concentration_override",
                    venue=allocations[0].venue,
                    remaining_allocation=remaining,
                )

            return allocations

        return []


class OrderRouter:
    """Route orders to available connectors according to a policy."""

    def __init__(
        self,
        connectors: Mapping[str, Any],
        *,
        policy: RoutingPolicy | None = None,
    ) -> None:
        self.connectors = connectors
        self.policy = policy or DefaultRoutingPolicy()

    def route_orders(self, orders: OrderSeq) -> dict[str, list[Order]]:
        """Build venue -> orders mapping without sending anything."""
        available = set(self.connectors.keys())
        planned: dict[str, list[Order]] = {}

        for order in orders:
            targets = self.policy.targets(order, available)
            if not targets:
                log.warning("routing.no_target", symbol=order.symbol)
                continue

            for target in targets:
                connector = self.connectors.get(target.venue)
                if connector is None:
                    log.warning(
                        "routing.connector_missing",
                        venue=target.venue,
                        symbol=order.symbol,
                    )
                    continue

                qty_decimal = (
                    Decimal(str(order.quantity)) * Decimal(str(target.weight))
                )
                qty = float(qty_decimal)
                if qty <= 0:
                    continue

                planned.setdefault(target.venue, []).append(
                    Order(
                        symbol=order.symbol,
                        side=order.side,
                        quantity=qty,
                        order_type=order.order_type,
                        price=order.price,
                        id=order.id,
                        timestamp=order.timestamp,
                    )
                )

        return planned

    async def submit_orders(self, orders: OrderSeq) -> None:
        """Route and submit orders to connectors."""
        planned = self.route_orders(orders)
        if not planned:
            log.warning("routing.no_orders_submitted")
            return

        tasks = []
        for venue, venue_orders in planned.items():
            connector = self.connectors.get(venue)
            if connector is None:
                log.warning("routing.connector_missing", venue=venue)
                continue

            submit = getattr(connector, "submit_orders", None)
            if submit is None:
                log.warning("routing.connector_no_submit", venue=venue)
                continue

            tasks.append(submit(venue_orders))

        if tasks:
            await asyncio.gather(*tasks)
