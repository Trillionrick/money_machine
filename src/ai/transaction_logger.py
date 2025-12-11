"""Production Transaction Logger for Trade Auditing and Analysis.

Logs every trade decision and execution with complete detail:
- Pre-trade analysis and predictions
- Execution details (tx hash, gas, slippage)
- Post-trade results (actual profit, performance)
- AI decision rationale

Supports:
- CSV export for analysis
- JSON for programmatic access
- Real-time trade streaming
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class TradeDecision:
    """AI trade decision record."""

    timestamp: str
    opportunity_id: str
    trade_type: str  # "flash_loan", "arbitrage", "spot"
    symbol: str
    action: str  # "BUY", "SELL", "EXECUTE"

    # AI Decision Metrics
    ai_confidence: float
    expected_profit_eth: float
    expected_profit_usd: float
    edge_bps: float
    kelly_fraction: float

    # Risk Metrics
    position_size_eth: float
    estimated_gas_cost_eth: float
    estimated_slippage_bps: float
    max_potential_loss_eth: float

    # Pool/Market Data
    pool_liquidity_eth: float
    gas_price_gwei: float

    # AI Scoring Details
    ml_score: float | None = None
    rl_action: str | None = None
    safety_score: float | None = None

    # Decision
    approved: bool = False
    rejection_reason: str | None = None


@dataclass
class TradeExecution:
    """Trade execution record."""

    decision_id: str
    timestamp: str

    # Execution Details
    tx_hash: str | None = None
    block_number: int | None = None
    executed: bool = False
    execution_error: str | None = None

    # Actual Costs
    actual_gas_cost_eth: float | None = None
    actual_gas_price_gwei: float | None = None
    actual_slippage_bps: float | None = None

    # Results
    actual_profit_eth: float | None = None
    actual_profit_usd: float | None = None
    execution_time_ms: int | None = None

    # Performance vs Prediction
    profit_error_pct: float | None = None  # (actual - expected) / expected
    gas_error_pct: float | None = None
    slippage_error_pct: float | None = None


@dataclass
class TradeResult:
    """Complete trade result (decision + execution)."""

    decision: TradeDecision
    execution: TradeExecution | None = None

    # Post-Trade Analysis
    success: bool = False
    win: bool = False  # Profitable
    pnl_eth: float = 0.0
    pnl_usd: float = 0.0
    roi_pct: float = 0.0

    # Portfolio Impact
    portfolio_value_before_eth: float = 0.0
    portfolio_value_after_eth: float = 0.0


class TransactionLogger:
    """Production transaction logger.

    Features:
    - Complete trade history (decisions + executions)
    - CSV and JSON export
    - Real-time statistics
    - Audit trail for compliance
    """

    def __init__(self, log_dir: Path | None = None):
        """Initialize transaction logger.

        Args:
            log_dir: Directory for log files (default: logs/trades)
        """
        self.log_dir = log_dir or Path("logs/trades")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Current session log file
        self.session_start = datetime.utcnow()
        self.session_id = self.session_start.strftime("%Y%m%d_%H%M%S")

        self.csv_path = self.log_dir / f"trades_{self.session_id}.csv"
        self.json_path = self.log_dir / f"trades_{self.session_id}.jsonl"

        # In-memory history
        self.trade_history: list[TradeResult] = []
        self.pending_decisions: dict[str, TradeDecision] = {}

        # Initialize CSV
        self._init_csv()

        log.info("transaction_logger.initialized", session_id=self.session_id, log_dir=str(self.log_dir))

    def _init_csv(self) -> None:
        """Initialize CSV file with headers."""
        headers = [
            # Timestamp & IDs
            "timestamp",
            "opportunity_id",
            "session_id",
            # Trade Info
            "trade_type",
            "symbol",
            "action",
            # AI Decision
            "ai_confidence",
            "expected_profit_eth",
            "edge_bps",
            "position_size_eth",
            # Execution
            "executed",
            "tx_hash",
            "block_number",
            # Results
            "actual_profit_eth",
            "actual_gas_cost_eth",
            "actual_slippage_bps",
            "pnl_eth",
            "success",
            "win",
            # Costs
            "gas_price_gwei",
            "gas_cost_eth",
            # Performance
            "profit_error_pct",
            "execution_time_ms",
            # Risk
            "max_loss_eth",
            "pool_liquidity_eth",
            # Rejection
            "approved",
            "rejection_reason",
        ]

        with open(self.csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

        log.debug("transaction_logger.csv_initialized", path=str(self.csv_path))

    def log_decision(self, decision: TradeDecision) -> str:
        """Log a trade decision.

        Args:
            decision: Trade decision to log

        Returns:
            Decision ID for later execution logging
        """
        decision_id = f"{decision.timestamp}_{decision.opportunity_id}"
        self.pending_decisions[decision_id] = decision

        # Log to JSON immediately
        self._append_json({"type": "decision", "data": asdict(decision)})

        log.info(
            "transaction_logger.decision_logged",
            decision_id=decision_id,
            approved=decision.approved,
            confidence=decision.ai_confidence,
            expected_profit_eth=decision.expected_profit_eth,
        )

        return decision_id

    def log_execution(self, decision_id: str, execution: TradeExecution) -> None:
        """Log trade execution result.

        Args:
            decision_id: ID from log_decision()
            execution: Execution details
        """
        if decision_id not in self.pending_decisions:
            log.warning("transaction_logger.unknown_decision", decision_id=decision_id)
            return

        decision = self.pending_decisions.pop(decision_id)

        # Create complete trade result
        result = TradeResult(decision=decision, execution=execution)

        # Calculate performance metrics
        if execution.executed and execution.actual_profit_eth is not None:
            result.success = True
            result.pnl_eth = execution.actual_profit_eth - (execution.actual_gas_cost_eth or 0)
            result.win = result.pnl_eth > 0

            if decision.position_size_eth > 0:
                result.roi_pct = (result.pnl_eth / decision.position_size_eth) * 100

            if decision.expected_profit_eth > 0:
                execution.profit_error_pct = (
                    (execution.actual_profit_eth - decision.expected_profit_eth)
                    / decision.expected_profit_eth
                    * 100
                )

        # Store in history
        self.trade_history.append(result)

        # Write to files
        self._append_csv(result)
        self._append_json({"type": "execution", "data": asdict(execution)})
        self._append_json({"type": "result", "data": asdict(result)})

        log.info(
            "transaction_logger.execution_logged",
            decision_id=decision_id,
            executed=execution.executed,
            pnl_eth=result.pnl_eth,
            win=result.win,
        )

    def log_rejection(self, decision: TradeDecision) -> None:
        """Log a rejected trade decision.

        Args:
            decision: Rejected decision
        """
        decision_id = self.log_decision(decision)

        # Create result with no execution
        result = TradeResult(decision=decision, execution=None, success=False)
        self.trade_history.append(result)

        # Write to CSV
        self._append_csv(result)

        log.info(
            "transaction_logger.rejection_logged",
            decision_id=decision_id,
            reason=decision.rejection_reason,
        )

    def _append_csv(self, result: TradeResult) -> None:
        """Append trade result to CSV."""
        row = {
            "timestamp": result.decision.timestamp,
            "opportunity_id": result.decision.opportunity_id,
            "session_id": self.session_id,
            "trade_type": result.decision.trade_type,
            "symbol": result.decision.symbol,
            "action": result.decision.action,
            "ai_confidence": result.decision.ai_confidence,
            "expected_profit_eth": result.decision.expected_profit_eth,
            "edge_bps": result.decision.edge_bps,
            "position_size_eth": result.decision.position_size_eth,
            "executed": result.execution.executed if result.execution else False,
            "tx_hash": result.execution.tx_hash if result.execution else None,
            "block_number": result.execution.block_number if result.execution else None,
            "actual_profit_eth": result.execution.actual_profit_eth if result.execution else None,
            "actual_gas_cost_eth": result.execution.actual_gas_cost_eth if result.execution else None,
            "actual_slippage_bps": result.execution.actual_slippage_bps if result.execution else None,
            "pnl_eth": result.pnl_eth,
            "success": result.success,
            "win": result.win,
            "gas_price_gwei": result.decision.gas_price_gwei,
            "gas_cost_eth": result.decision.estimated_gas_cost_eth,
            "profit_error_pct": result.execution.profit_error_pct if result.execution else None,
            "execution_time_ms": result.execution.execution_time_ms if result.execution else None,
            "max_loss_eth": result.decision.max_potential_loss_eth,
            "pool_liquidity_eth": result.decision.pool_liquidity_eth,
            "approved": result.decision.approved,
            "rejection_reason": result.decision.rejection_reason,
        }

        with open(self.csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            writer.writerow(row)

    def _append_json(self, data: dict[str, Any]) -> None:
        """Append JSON line to log file."""
        with open(self.json_path, "a") as f:
            json.dump(data, f)
            f.write("\n")

    def get_session_stats(self) -> dict[str, Any]:
        """Get statistics for current session.

        Returns:
            Session performance metrics
        """
        if not self.trade_history:
            return {"total_trades": 0, "session_id": self.session_id}

        executed_trades = [t for t in self.trade_history if t.execution and t.execution.executed]
        wins = [t for t in executed_trades if t.win]
        losses = [t for t in executed_trades if not t.win and t.pnl_eth < 0]

        total_pnl_eth = sum(t.pnl_eth for t in executed_trades)
        total_profit_eth = sum(t.pnl_eth for t in wins)
        total_loss_eth = sum(t.pnl_eth for t in losses)

        return {
            "session_id": self.session_id,
            "session_start": self.session_start.isoformat(),
            "total_decisions": len(self.trade_history),
            "approved_decisions": sum(1 for t in self.trade_history if t.decision.approved),
            "rejected_decisions": sum(1 for t in self.trade_history if not t.decision.approved),
            "total_executions": len(executed_trades),
            "successful_executions": sum(1 for t in executed_trades if t.success),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": (len(wins) / len(executed_trades) * 100) if executed_trades else 0,
            "total_pnl_eth": total_pnl_eth,
            "total_profit_eth": total_profit_eth,
            "total_loss_eth": total_loss_eth,
            "avg_win_eth": (total_profit_eth / len(wins)) if wins else 0,
            "avg_loss_eth": (total_loss_eth / len(losses)) if losses else 0,
            "largest_win_eth": max((t.pnl_eth for t in wins), default=0),
            "largest_loss_eth": min((t.pnl_eth for t in losses), default=0),
            "avg_confidence": sum(t.decision.ai_confidence for t in self.trade_history) / len(self.trade_history),
            "log_files": {"csv": str(self.csv_path), "json": str(self.json_path)},
        }

    def export_summary(self, output_path: Path | None = None) -> Path:
        """Export session summary to JSON.

        Args:
            output_path: Path for summary file (default: logs/trades/summary_{session_id}.json)

        Returns:
            Path to summary file
        """
        if output_path is None:
            output_path = self.log_dir / f"summary_{self.session_id}.json"

        stats = self.get_session_stats()

        with open(output_path, "w") as f:
            json.dump(stats, f, indent=2)

        log.info("transaction_logger.summary_exported", path=str(output_path))
        return output_path


# Global singleton
_logger: TransactionLogger | None = None


def get_transaction_logger() -> TransactionLogger:
    """Get global TransactionLogger instance."""
    global _logger
    if _logger is None:
        _logger = TransactionLogger()
    return _logger
