"""Production Alert System for Critical Events.

Sends notifications for:
- Profitable trades
- Large losses
- Circuit breaker triggers
- Emergency shutdowns
- Daily/hourly summaries

Supports:
- Discord webhooks
- Telegram bot
- Email (SMTP)
- Console logging
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import requests
import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

log = structlog.get_logger()


class AlertConfig(BaseSettings):
    """Alert system configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    discord_webhook_url: str | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None


class AlertLevel(Enum):
    """Alert severity levels."""

    INFO = "info"  # General information
    SUCCESS = "success"  # Profitable trades
    WARNING = "warning"  # Potential issues
    CRITICAL = "critical"  # Emergency situations


@dataclass
class Alert:
    """Alert message."""

    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    data: dict[str, Any] | None = None


class AlertSystem:
    """Production alert system.

    Sends notifications through multiple channels for critical trading events.
    """

    def __init__(
        self,
        config: AlertConfig | None = None,
        discord_webhook: str | None = None,
        telegram_bot_token: str | None = None,
        telegram_chat_id: str | None = None,
        enable_console: bool = True,
    ):
        """Initialize alert system.

        Args:
            config: Pydantic settings (auto-loads from env if not provided)
            discord_webhook: Override Discord webhook URL
            telegram_bot_token: Override Telegram bot token
            telegram_chat_id: Override Telegram chat ID
            enable_console: Enable console logging
        """
        # Load config from environment if not provided
        if config is None:
            config = AlertConfig()

        # Use explicit params or fall back to config
        self.discord_webhook = discord_webhook or config.discord_webhook_url
        self.telegram_bot_token = telegram_bot_token or config.telegram_bot_token
        self.telegram_chat_id = telegram_chat_id or config.telegram_chat_id
        self.enable_console = enable_console

        # Alert history
        self.alert_history: list[Alert] = []

        # Rate limiting
        self.last_alert_times: dict[str, datetime] = {}
        self.min_alert_interval_seconds = 60  # Don't spam same alert within 60s

        log.info(
            "alert_system.initialized",
            discord=bool(self.discord_webhook),
            telegram=bool(self.telegram_bot_token and self.telegram_chat_id),
        )

    def send_trade_executed(
        self,
        symbol: str,
        profit_eth: float,
        profit_usd: float,
        confidence: float,
        tx_hash: str | None = None,
    ) -> None:
        """Alert: Trade executed successfully.

        Args:
            symbol: Trading symbol
            profit_eth: Profit in ETH
            profit_usd: Profit in USD
            confidence: AI confidence
            tx_hash: Transaction hash
        """
        emoji = "🟢" if profit_eth > 0 else "🔴"
        title = f"{emoji} Trade Executed: {symbol}"

        message = (
            f"Profit: {profit_eth:+.6f} ETH (${profit_usd:+.2f})\n"
            f"AI Confidence: {confidence:.1%}\n"
        )

        if tx_hash:
            message += f"TX: {tx_hash[:10]}...{tx_hash[-8:]}\n"
            message += f"Etherscan: https://etherscan.io/tx/{tx_hash}"

        alert = Alert(
            level=AlertLevel.SUCCESS if profit_eth > 0 else AlertLevel.WARNING,
            title=title,
            message=message,
            timestamp=datetime.now(timezone.utc),
            data={
                "symbol": symbol,
                "profit_eth": profit_eth,
                "profit_usd": profit_usd,
                "confidence": confidence,
                "tx_hash": tx_hash,
            },
        )

        self._send_alert(alert)

    def send_trade_failed(
        self,
        symbol: str,
        loss_eth: float,
        loss_usd: float,
        reason: str,
    ) -> None:
        """Alert: Trade execution failed."""
        title = f"🔴 Trade Failed: {symbol}"
        message = (
            f"Loss (gas/fees): {loss_eth:.6f} ETH (${loss_usd:.2f})\n"
            f"Reason: {reason}"
        )

        alert = Alert(
            level=AlertLevel.WARNING,
            title=title,
            message=message,
            timestamp=datetime.now(timezone.utc),
            data={
                "symbol": symbol,
                "loss_eth": loss_eth,
                "loss_usd": loss_usd,
                "reason": reason,
            },
        )

        self._send_alert(alert)

    def send_emergency_shutdown(self, reason: str, total_loss_eth: float) -> None:
        """Alert: Emergency shutdown triggered.

        Args:
            reason: Shutdown reason
            total_loss_eth: Total loss that triggered shutdown
        """
        title = "🚨 EMERGENCY SHUTDOWN"
        message = (
            f"System automatically shut down!\n\n"
            f"Reason: {reason}\n"
            f"Total Loss: {total_loss_eth:.4f} ETH\n\n"
            f"⚠️ Trading halted. Manual intervention required."
        )

        alert = Alert(
            level=AlertLevel.CRITICAL,
            title=title,
            message=message,
            timestamp=datetime.now(timezone.utc),
            data={"reason": reason, "total_loss_eth": total_loss_eth},
        )

        self._send_alert(alert, force=True)

    def send_circuit_breaker_triggered(
        self, breaker_type: str, reason: str, value: float, threshold: float
    ) -> None:
        """Alert: Circuit breaker triggered.

        Args:
            breaker_type: Type of breaker
            reason: Trigger reason
            value: Current value
            threshold: Threshold exceeded
        """
        title = f"⚠️ Circuit Breaker: {breaker_type.upper()}"
        message = (
            f"{reason}\n\n"
            f"Current: {value:.4f}\n"
            f"Threshold: {threshold:.4f}\n\n"
            f"Trading paused for safety."
        )

        alert = Alert(
            level=AlertLevel.WARNING,
            title=title,
            message=message,
            timestamp=datetime.now(timezone.utc),
            data={
                "breaker_type": breaker_type,
                "reason": reason,
                "value": value,
                "threshold": threshold,
            },
        )

        self._send_alert(alert)

    def send_daily_summary(
        self,
        trades_executed: int,
        wins: int,
        losses: int,
        total_profit_eth: float,
        total_profit_usd: float,
        win_rate: float,
    ) -> None:
        """Alert: Daily performance summary.

        Args:
            trades_executed: Number of trades
            wins: Winning trades
            losses: Losing trades
            total_profit_eth: Total profit in ETH
            total_profit_usd: Total profit in USD
            win_rate: Win rate percentage
        """
        emoji = "📊"
        if total_profit_eth > 0.5:
            emoji = "🎉"
        elif total_profit_eth < -0.5:
            emoji = "😞"

        title = f"{emoji} Daily Summary - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        message = (
            f"Trades: {trades_executed} ({wins}W / {losses}L)\n"
            f"Win Rate: {win_rate:.1f}%\n\n"
            f"P&L: {total_profit_eth:+.4f} ETH\n"
            f"P&L USD: ${total_profit_usd:+.2f}\n\n"
        )

        if total_profit_eth > 0:
            message += "✅ Profitable day!"
        elif total_profit_eth < 0:
            message += "⚠️ Negative day - review strategy"
        else:
            message += "Break even"

        alert = Alert(
            level=AlertLevel.INFO,
            title=title,
            message=message,
            timestamp=datetime.now(timezone.utc),
            data={
                "trades": trades_executed,
                "wins": wins,
                "losses": losses,
                "profit_eth": total_profit_eth,
                "profit_usd": total_profit_usd,
                "win_rate": win_rate,
            },
        )

        self._send_alert(alert)

    def send_large_opportunity(
        self, symbol: str, expected_profit_eth: float, edge_bps: float, confidence: float
    ) -> None:
        """Alert: Large opportunity detected.

        Args:
            symbol: Trading symbol
            expected_profit_eth: Expected profit
            edge_bps: Edge in basis points
            confidence: AI confidence
        """
        title = f"💰 Large Opportunity: {symbol}"
        message = (
            f"Expected Profit: {expected_profit_eth:.4f} ETH\n"
            f"Edge: {edge_bps:.1f} bps\n"
            f"Confidence: {confidence:.1%}"
        )

        alert = Alert(
            level=AlertLevel.INFO,
            title=title,
            message=message,
            timestamp=datetime.now(timezone.utc),
            data={
                "symbol": symbol,
                "expected_profit_eth": expected_profit_eth,
                "edge_bps": edge_bps,
                "confidence": confidence,
            },
        )

        self._send_alert(alert)

    def _send_alert(self, alert: Alert, force: bool = False) -> None:
        """Send alert through all configured channels.

        Args:
            alert: Alert to send
            force: Force send even if rate limited
        """
        # Rate limiting (unless forced)
        if not force:
            alert_key = f"{alert.level.value}_{alert.title}"
            last_time = self.last_alert_times.get(alert_key)

            if last_time:
                seconds_since = (alert.timestamp - last_time).total_seconds()
                if seconds_since < self.min_alert_interval_seconds:
                    log.debug("alert_system.rate_limited", alert_key=alert_key)
                    return

            self.last_alert_times[alert_key] = alert.timestamp

        # Store in history
        self.alert_history.append(alert)

        # Send through all channels
        if self.enable_console:
            self._send_console(alert)

        if self.discord_webhook:
            self._send_discord(alert)

        if self.telegram_bot_token and self.telegram_chat_id:
            self._send_telegram(alert)

        log.info("alert_system.sent", level=alert.level.value, title=alert.title)

    def _send_console(self, alert: Alert) -> None:
        """Send alert to console."""
        level_emojis = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.SUCCESS: "✅",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
        }

        emoji = level_emojis.get(alert.level, "📢")
        print(f"\n{emoji} {alert.title}")
        print(alert.message)
        print()

    def _send_discord(self, alert: Alert) -> None:
        """Send alert to Discord webhook."""
        if not self.discord_webhook:
            return

        # Color based on level
        colors = {
            AlertLevel.INFO: 3447003,  # Blue
            AlertLevel.SUCCESS: 3066993,  # Green
            AlertLevel.WARNING: 16776960,  # Yellow
            AlertLevel.CRITICAL: 15158332,  # Red
        }

        embed = {
            "title": alert.title,
            "description": alert.message,
            "color": colors.get(alert.level, 0),
            "timestamp": alert.timestamp.isoformat(),
        }

        if alert.data:
            embed["fields"] = [
                {"name": key, "value": str(value), "inline": True} for key, value in alert.data.items()
            ]

        payload = {"embeds": [embed]}

        try:
            response = requests.post(
                self.discord_webhook, json=payload, timeout=10
            )
            response.raise_for_status()
        except Exception:
            log.exception("alert_system.discord_failed")

    def _send_telegram(self, alert: Alert) -> None:
        """Send alert to Telegram."""
        if not (self.telegram_bot_token and self.telegram_chat_id):
            return

        # Format message
        message = f"*{alert.title}*\n\n{alert.message}"

        # Add data if present
        if alert.data:
            message += "\n\n*Details:*\n"
            for key, value in alert.data.items():
                message += f"• {key}: `{value}`\n"

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except Exception:
            log.exception("alert_system.telegram_failed")

    def get_alert_history(self, limit: int = 100) -> list[Alert]:
        """Get recent alerts.

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of recent alerts
        """
        return self.alert_history[-limit:]


# Global singleton
_alert_system: AlertSystem | None = None


def get_alert_system() -> AlertSystem:
    """Get global AlertSystem instance."""
    global _alert_system
    if _alert_system is None:
        _alert_system = AlertSystem()
    return _alert_system
