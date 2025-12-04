#!/usr/bin/env python3
"""Route health monitoring tool.

Analyzes route performance from the arbitrage runner's SQLite database
and provides insights into:
- Route success rates
- Blacklisted routes
- Symbol performance
- Recommendations for optimization
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class RouteHealth:
    """Route health metrics."""

    route_id: str
    failures: int
    is_blacklisted: bool
    status: str  # "healthy", "degraded", "blacklisted"


@dataclass
class PairPerformance:
    """Trading pair performance metrics."""

    symbol: str
    wins: int
    trades: int
    win_rate: float


class RouteMonitor:
    """Monitor and analyze route health."""

    def __init__(self, db_path: Path = Path("logs/route_health.db")) -> None:
        """Initialize route monitor.

        Args:
            db_path: Path to route health SQLite database
        """
        self.db_path = db_path
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Route health database not found at {db_path}. "
                "Run the arbitrage system first to generate data."
            )

        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def get_route_health(self) -> list[RouteHealth]:
        """Get health status of all routes."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT route_id, failures, blacklisted
            FROM route_failures
            ORDER BY failures DESC
            """
        )

        routes = []
        for row in cursor.fetchall():
            failures = row["failures"]
            is_blacklisted = bool(row["blacklisted"])

            if is_blacklisted:
                status = "blacklisted"
            elif failures >= 2:
                status = "degraded"
            else:
                status = "healthy"

            routes.append(
                RouteHealth(
                    route_id=row["route_id"],
                    failures=failures,
                    is_blacklisted=is_blacklisted,
                    status=status,
                )
            )

        return routes

    def get_pair_performance(self) -> list[PairPerformance]:
        """Get trading pair performance."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT symbol, wins, trades
            FROM pair_results
            ORDER BY trades DESC
            """
        )

        pairs = []
        for row in cursor.fetchall():
            wins = row["wins"]
            trades = row["trades"]
            win_rate = (wins / trades * 100) if trades > 0 else 0.0

            pairs.append(
                PairPerformance(
                    symbol=row["symbol"],
                    wins=wins,
                    trades=trades,
                    win_rate=win_rate,
                )
            )

        return pairs

    def get_summary(self) -> dict[str, Any]:
        """Get overall health summary."""
        routes = self.get_route_health()
        pairs = self.get_pair_performance()

        total_routes = len(routes)
        blacklisted = sum(1 for r in routes if r.is_blacklisted)
        degraded = sum(1 for r in routes if r.status == "degraded")
        healthy = sum(1 for r in routes if r.status == "healthy")

        total_trades = sum(p.trades for p in pairs)
        total_wins = sum(p.wins for p in pairs)
        overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0

        return {
            "routes": {
                "total": total_routes,
                "healthy": healthy,
                "degraded": degraded,
                "blacklisted": blacklisted,
            },
            "pairs": {
                "total": len(pairs),
                "total_trades": total_trades,
                "total_wins": total_wins,
                "overall_win_rate": overall_win_rate,
            },
        }

    def print_report(self) -> None:
        """Print detailed health report."""
        print("\n" + "=" * 70)
        print("ROUTE HEALTH MONITOR".center(70))
        print("=" * 70 + "\n")

        # Summary
        summary = self.get_summary()
        print("📊 SUMMARY")
        print("-" * 70)
        print(f"Routes: {summary['routes']['total']} total")
        print(f"  ✅ Healthy:     {summary['routes']['healthy']}")
        print(f"  ⚠️  Degraded:    {summary['routes']['degraded']}")
        print(f"  ❌ Blacklisted: {summary['routes']['blacklisted']}")
        print()
        print(f"Trading Pairs: {summary['pairs']['total']} total")
        print(f"  Total Trades: {summary['pairs']['total_trades']}")
        print(f"  Total Wins:   {summary['pairs']['total_wins']}")
        print(f"  Win Rate:     {summary['pairs']['overall_win_rate']:.1f}%")
        print()

        # Routes
        routes = self.get_route_health()
        print("🛣️  ROUTE HEALTH")
        print("-" * 70)

        if not routes:
            print("No route data available yet.")
        else:
            # Show problematic routes first
            problematic = [r for r in routes if r.status != "healthy"]
            if problematic:
                print("\n⚠️  Problematic Routes:")
                for route in problematic[:10]:  # Top 10
                    status_icon = "❌" if route.is_blacklisted else "⚠️"
                    print(
                        f"  {status_icon} {route.route_id[:50]}... "
                        f"({route.failures} failures)"
                    )
            else:
                print("All routes are healthy! ✅")

        print()

        # Pair Performance
        pairs = self.get_pair_performance()
        print("💰 PAIR PERFORMANCE")
        print("-" * 70)

        if not pairs:
            print("No trading data available yet.")
        else:
            print(
                f"{'Symbol':<15} {'Trades':>8} {'Wins':>8} {'Win Rate':>10}"
            )
            print("-" * 70)
            for pair in sorted(pairs, key=lambda p: p.win_rate, reverse=True)[:15]:
                status_icon = "✅" if pair.win_rate >= 80 else "⚠️" if pair.win_rate >= 50 else "❌"
                print(
                    f"{pair.symbol:<15} {pair.trades:>8} {pair.wins:>8} "
                    f"{pair.win_rate:>9.1f}% {status_icon}"
                )

        print()

        # Recommendations
        print("💡 RECOMMENDATIONS")
        print("-" * 70)
        recommendations = self._generate_recommendations(routes, pairs)
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                print(f"{i}. {rec}")
        else:
            print("System is performing well! No immediate actions needed.")

        print("\n" + "=" * 70 + "\n")

    def _generate_recommendations(
        self, routes: list[RouteHealth], pairs: list[PairPerformance]
    ) -> list[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Check for blacklisted routes
        blacklisted_count = sum(1 for r in routes if r.is_blacklisted)
        if blacklisted_count > 0:
            recommendations.append(
                f"Review {blacklisted_count} blacklisted route(s). "
                "Consider investigating root causes (liquidity, slippage, contract issues)."
            )

        # Check for low win rate pairs
        low_performers = [p for p in pairs if p.trades >= 5 and p.win_rate < 50]
        if low_performers:
            symbols = ", ".join(p.symbol for p in low_performers[:3])
            recommendations.append(
                f"Low win rate detected for: {symbols}. "
                "Consider adjusting thresholds or removing these pairs."
            )

        # Check for untested pairs (no trades)
        if pairs:
            avg_trades = sum(p.trades for p in pairs) / len(pairs)
            inactive = [p for p in pairs if p.trades < avg_trades * 0.1]
            if len(inactive) > len(pairs) * 0.3:  # 30%+ inactive
                recommendations.append(
                    f"{len(inactive)} pairs have minimal activity. "
                    "Consider reviewing min_edge_bps or liquidity requirements."
                )

        # Check for high degraded route count
        degraded_count = sum(1 for r in routes if r.status == "degraded")
        if degraded_count > len(routes) * 0.2:  # 20%+ degraded
            recommendations.append(
                f"{degraded_count} routes are degraded. "
                "Check RPC connectivity, gas settings, or DEX pool liquidity."
            )

        return recommendations

    def reset_route(self, route_id: str) -> bool:
        """Reset failures for a specific route.

        Args:
            route_id: Route to reset

        Returns:
            True if successful
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                UPDATE route_failures
                SET failures = 0, blacklisted = 0
                WHERE route_id = ?
                """,
                (route_id,),
            )
            self.conn.commit()

            if cursor.rowcount > 0:
                log.info("route_monitor.reset_successful", route_id=route_id)
                return True

            log.warning("route_monitor.route_not_found", route_id=route_id)
            return False

        except Exception as e:
            log.error("route_monitor.reset_failed", route_id=route_id, error=str(e))
            return False

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Route Health Monitor")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("logs/route_health.db"),
        help="Path to route health database",
    )
    parser.add_argument(
        "--reset-route",
        type=str,
        help="Reset failures for a specific route ID",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of formatted report",
    )

    args = parser.parse_args()

    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger("INFO"),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    try:
        monitor = RouteMonitor(args.db)

        if args.reset_route:
            # Reset specific route
            success = monitor.reset_route(args.reset_route)
            if success:
                print(f"✅ Reset route: {args.reset_route}")
            else:
                print(f"❌ Failed to reset route: {args.reset_route}")
                return

        elif args.json:
            # JSON output
            import json

            summary = monitor.get_summary()
            routes = [
                {
                    "route_id": r.route_id,
                    "failures": r.failures,
                    "blacklisted": r.is_blacklisted,
                    "status": r.status,
                }
                for r in monitor.get_route_health()
            ]
            pairs = [
                {
                    "symbol": p.symbol,
                    "wins": p.wins,
                    "trades": p.trades,
                    "win_rate": p.win_rate,
                }
                for p in monitor.get_pair_performance()
            ]

            output = {
                "summary": summary,
                "routes": routes,
                "pairs": pairs,
            }

            print(json.dumps(output, indent=2))

        else:
            # Human-readable report
            monitor.print_report()

        monitor.close()

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("\nMake sure to run the arbitrage system first to generate route data.")
    except Exception as e:
        log.exception("route_monitor.error", error=str(e))


if __name__ == "__main__":
    main()
