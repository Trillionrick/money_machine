"""Log arbitrage opportunities to TimescaleDB for ML training."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import asyncpg
import structlog

if TYPE_CHECKING:
    from decimal import Decimal

log = structlog.get_logger()


@dataclass
class OpportunityLog:
    """Arbitrage opportunity data for ML training."""

    symbol: str
    chain: str
    cex_price: float
    dex_price: float
    edge_bps: float
    pool_liquidity_quote: float | None
    gas_price_gwei: float
    hour_of_day: int
    estimated_slippage_bps: float
    trade_size_quote: float | None = None
    hop_count: int = 2
    route_path: str | None = None
    execution_path: str = "regular"
    # Set after execution
    executed: bool = False
    actual_slippage_bps: float | None = None
    profitable: bool | None = None
    profit_eth: float | None = None
    profit_quote: float | None = None
    gas_cost_eth: float | None = None
    ml_model_version: str | None = None


class OpportunityLogger:
    """Logs arbitrage opportunities to TimescaleDB for ML training."""

    def __init__(self):
        self.pool: asyncpg.Pool | None = None
        self.db_url = self._build_db_url()

    def _build_db_url(self) -> str:
        """Build PostgreSQL connection URL from environment."""
        host = os.getenv("TIMESCALE_HOST", "localhost")
        port = os.getenv("TIMESCALE_PORT", "5433")
        user = os.getenv("TIMESCALE_USER", "trading_user")
        password = os.getenv("TIMESCALE_PASSWORD", "trading_pass_change_in_production")
        database = os.getenv("TIMESCALE_DB", "trading_db")

        return f"postgresql://{user}:{password}@{host}:{port}/{database}"

    async def connect(self) -> None:
        """Create connection pool to TimescaleDB."""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(
                    self.db_url,
                    min_size=2,
                    max_size=10,
                    command_timeout=60
                )
                log.info("opportunity_logger.connected")
            except Exception as e:
                log.warning("opportunity_logger.connect_failed", error=str(e))

    async def close(self) -> None:
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            log.info("opportunity_logger.closed")

    async def log_opportunity(self, opp: OpportunityLog) -> int | None:
        """Log opportunity to database, return row ID."""
        if not self.pool:
            await self.connect()

        if not self.pool:
            log.warning("opportunity_logger.no_connection")
            return None

        try:
            row_id = await self.pool.fetchval(
                """
                INSERT INTO arbitrage_opportunities (
                    timestamp, symbol, chain, cex_price, dex_price, edge_bps,
                    pool_liquidity_quote, gas_price_gwei, hour_of_day,
                    estimated_slippage_bps, trade_size_quote, hop_count,
                    route_path, execution_path, executed, actual_slippage_bps,
                    profitable, profit_eth, profit_quote, gas_cost_eth,
                    ml_model_version
                ) VALUES (
                    NOW(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                    $12, $13, $14, $15, $16, $17, $18, $19, $20
                ) RETURNING id
                """,
                opp.symbol,
                opp.chain,
                opp.cex_price,
                opp.dex_price,
                opp.edge_bps,
                opp.pool_liquidity_quote,
                opp.gas_price_gwei,
                opp.hour_of_day,
                opp.estimated_slippage_bps,
                opp.trade_size_quote,
                opp.hop_count,
                opp.route_path,
                opp.execution_path,
                opp.executed,
                opp.actual_slippage_bps,
                opp.profitable,
                opp.profit_eth,
                opp.profit_quote,
                opp.gas_cost_eth,
                opp.ml_model_version,
            )

            log.debug("opportunity_logger.logged", id=row_id, symbol=opp.symbol, edge_bps=opp.edge_bps)
            return row_id

        except Exception as e:
            log.warning("opportunity_logger.insert_failed", error=str(e), symbol=opp.symbol)
            return None

    async def update_execution_result(
        self,
        row_id: int,
        actual_slippage_bps: float,
        profitable: bool,
        profit_eth: float | None = None,
        profit_quote: float | None = None,
        gas_cost_eth: float | None = None,
    ) -> None:
        """Update opportunity record with execution results."""
        if not self.pool:
            return

        try:
            await self.pool.execute(
                """
                UPDATE arbitrage_opportunities
                SET executed = TRUE,
                    actual_slippage_bps = $2,
                    profitable = $3,
                    profit_eth = $4,
                    profit_quote = $5,
                    gas_cost_eth = $6
                WHERE id = $1
                """,
                row_id,
                actual_slippage_bps,
                profitable,
                profit_eth,
                profit_quote,
                gas_cost_eth,
            )

            log.debug("opportunity_logger.updated", id=row_id, profitable=profitable)

        except Exception as e:
            log.warning("opportunity_logger.update_failed", error=str(e), id=row_id)

    async def get_training_data(self, days: int = 30, min_samples: int = 50) -> list[dict]:
        """Fetch recent training data for ML models."""
        if not self.pool:
            await self.connect()

        if not self.pool:
            return []

        try:
            rows = await self.pool.fetch(
                """
                SELECT * FROM ml_training_data
                WHERE timestamp > NOW() - $1::INTERVAL
                ORDER BY timestamp DESC
                LIMIT 10000
                """,
                f"{days} days",
            )

            if len(rows) < min_samples:
                log.warning(
                    "opportunity_logger.insufficient_training_data",
                    samples=len(rows),
                    required=min_samples,
                )
                return []

            return [dict(row) for row in rows]

        except Exception as e:
            log.warning("opportunity_logger.fetch_failed", error=str(e))
            return []


# Global singleton instance
_logger: OpportunityLogger | None = None


def get_opportunity_logger() -> OpportunityLogger:
    """Get global OpportunityLogger instance."""
    global _logger
    if _logger is None:
        _logger = OpportunityLogger()
    return _logger
