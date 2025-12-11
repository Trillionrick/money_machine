"""
Alpaca-AI Integration Bridge

Connects the AI arbitrage system with Alpaca for automated trade execution.
Enables AI-driven flash loan and arbitrage strategies to execute on Alpaca.
"""

import asyncio
from decimal import Decimal
from typing import Any

import structlog

from src.ai.decider import AIDecider, AICandidate
from src.ai.unified_orchestrator import UnifiedAIOrchestrator
from src.brokers.alpaca_adapter import AlpacaAdapter
from src.core.execution import Order, OrderType, Side

log = structlog.get_logger()


class AlpacaAIBridge:
    """Bridge between AI arbitrage system and Alpaca trading."""

    def __init__(
        self,
        alpaca_adapter: AlpacaAdapter,
        ai_orchestrator: UnifiedAIOrchestrator | None = None,
    ):
        """Initialize the bridge.

        Args:
            alpaca_adapter: Alpaca trading adapter
            ai_orchestrator: AI orchestrator (optional, will create if not provided)
        """
        self.alpaca = alpaca_adapter
        self.orchestrator = ai_orchestrator  # Don't create default - requires dependencies
        self.active_trades: dict[str, dict[str, Any]] = {}
        self.trade_history: list[dict[str, Any]] = []

        log.info(
            "alpaca_ai_bridge.initialized",
            paper_mode=alpaca_adapter.paper,
        )

    async def analyze_opportunity(
        self,
        symbol: str,
        cex_price: float,
        dex_price: float,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Analyze an arbitrage opportunity using AI.

        Args:
            symbol: Trading symbol (e.g., 'SPY', 'AAPL')
            cex_price: Centralized exchange price
            dex_price: Decentralized exchange price
            **kwargs: Additional parameters

        Returns:
            AI analysis with decision and confidence
        """
        # Calculate edge
        edge_bps = abs((cex_price - dex_price) / cex_price) * 10000

        # Create AI candidate
        candidate = AICandidate(
            symbol=symbol,
            edge_bps=edge_bps,
            notional_quote=kwargs.get("notional_quote", 1000.0),
            gas_cost_quote=kwargs.get("gas_cost_quote", 0.0),
            flash_fee_quote=kwargs.get("flash_fee_quote", 0.0),
            slippage_quote=kwargs.get("slippage_quote", 0.0),
            hop_count=kwargs.get("hop_count", 1),
            cex_price=cex_price,
            dex_price=dex_price,
            chain=kwargs.get("chain", "ethereum"),
            confidence=kwargs.get("confidence", 0.7),
        )

        # Get AI decision
        from src.ai.decider import AIDecider, AIConfig

        ai_config = AIConfig(
            min_profit_eth=0.01,
            confidence_threshold=0.6,
            max_gas_gwei=100.0,
            hop_penalty_quote=5.0,
        )
        decider = AIDecider(config=ai_config)
        decision = decider.pick_best([candidate])

        if decision:
            return {
                "should_trade": True,
                "symbol": decision.symbol,
                "edge_bps": decision.edge_bps,
                "confidence": decision.confidence,
                "net_profit_quote": decision.net_quote,
                "reason": decision.reason,
                "recommended_size": self._calculate_position_size(
                    decision, kwargs.get("account_equity", 10000.0)
                ),
            }

        return {
            "should_trade": False,
            "reason": "No profitable opportunity found",
        }

    def _calculate_position_size(
        self,
        decision: Any,
        account_equity: float,
    ) -> float:
        """Calculate optimal position size based on Kelly Criterion.

        Args:
            decision: AI decision
            account_equity: Total account equity

        Returns:
            Recommended position size in dollars
        """
        # Conservative Kelly fraction (0.25 = 1/4 Kelly)
        kelly_fraction = 0.25

        # Estimate win probability from confidence
        win_prob = decision.confidence

        # Estimate win/loss ratio from edge
        win_loss_ratio = decision.edge_bps / 100.0  # Simplified

        # Kelly formula: f = (p * b - q) / b
        # where p = win prob, q = loss prob, b = win/loss ratio
        kelly = (win_prob * win_loss_ratio - (1 - win_prob)) / win_loss_ratio

        # Apply fraction and ensure positive
        kelly = max(0, kelly * kelly_fraction)

        # Calculate position size (cap at 20% of equity)
        position_size = min(account_equity * kelly, account_equity * 0.20)

        return position_size

    async def execute_arbitrage_trade(
        self,
        symbol: str,
        direction: str,  # 'buy' or 'sell'
        quantity: float,
        order_type: str = "market",
        limit_price: float | None = None,
        ai_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an arbitrage trade via Alpaca.

        Args:
            symbol: Trading symbol
            direction: 'buy' or 'sell'
            quantity: Number of shares
            order_type: 'market' or 'limit'
            limit_price: Limit price for limit orders
            ai_metadata: AI decision metadata

        Returns:
            Trade execution result
        """
        try:
            # Create order
            side = Side.BUY if direction.lower() == "buy" else Side.SELL
            order_type_enum = (
                OrderType.MARKET if order_type == "market" else OrderType.LIMIT
            )

            order = Order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type_enum,
                price=limit_price if order_type == "limit" else None,
            )

            # Submit to Alpaca
            await self.alpaca.submit_orders([order])

            # Track trade
            trade_id = f"{symbol}_{asyncio.get_event_loop().time()}"
            trade_record = {
                "trade_id": trade_id,
                "symbol": symbol,
                "direction": direction,
                "quantity": quantity,
                "order_type": order_type,
                "limit_price": limit_price,
                "ai_metadata": ai_metadata or {},
                "status": "submitted",
                "timestamp": asyncio.get_event_loop().time(),
            }

            self.active_trades[trade_id] = trade_record
            self.trade_history.append(trade_record)

            log.info(
                "alpaca_ai_bridge.trade_executed",
                trade_id=trade_id,
                symbol=symbol,
                direction=direction,
                quantity=quantity,
            )

            return {
                "success": True,
                "trade_id": trade_id,
                "symbol": symbol,
                "direction": direction,
                "quantity": quantity,
                "order_type": order_type,
            }

        except Exception as e:
            log.exception(
                "alpaca_ai_bridge.trade_failed",
                symbol=symbol,
                error=str(e),
            )
            return {
                "success": False,
                "error": str(e),
                "symbol": symbol,
            }

    async def execute_flash_loan_arbitrage(
        self,
        opportunity: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a flash loan arbitrage strategy.

        Note: Flash loans are blockchain-native. For Alpaca (traditional markets),
        we simulate this by using margin trading with immediate close.

        Args:
            opportunity: Arbitrage opportunity details

        Returns:
            Execution result
        """
        symbol = opportunity.get("symbol")
        edge_bps = opportunity.get("edge_bps", 0)
        confidence = opportunity.get("confidence", 0)

        if not symbol or edge_bps < 50:  # Minimum 50 bps edge
            return {
                "success": False,
                "reason": "Insufficient edge for flash loan strategy",
            }

        # Get account info
        account = await self.alpaca.get_account()
        buying_power = account.get("buying_power", 0)

        # Calculate position size (use margin)
        position_size = min(buying_power * 0.5, 10000.0)  # Max $10k per trade
        quantity = int(position_size / opportunity.get("cex_price", 100))

        if quantity < 1:
            return {
                "success": False,
                "reason": "Position size too small",
            }

        log.info(
            "alpaca_ai_bridge.flash_loan_attempt",
            symbol=symbol,
            quantity=quantity,
            edge_bps=edge_bps,
            confidence=confidence,
        )

        # Execute buy side
        buy_result = await self.execute_arbitrage_trade(
            symbol=symbol,
            direction="buy",
            quantity=quantity,
            order_type="market",
            ai_metadata={
                "strategy": "flash_loan_arbitrage",
                "edge_bps": edge_bps,
                "confidence": confidence,
            },
        )

        if not buy_result.get("success"):
            return buy_result

        # Wait for fill (simplified - in production, monitor fill status)
        await asyncio.sleep(1)

        # Execute sell side to close
        sell_result = await self.execute_arbitrage_trade(
            symbol=symbol,
            direction="sell",
            quantity=quantity,
            order_type="market",
            ai_metadata={
                "strategy": "flash_loan_arbitrage_close",
                "related_trade": buy_result.get("trade_id"),
            },
        )

        return {
            "success": True,
            "strategy": "flash_loan_arbitrage",
            "symbol": symbol,
            "quantity": quantity,
            "buy_trade": buy_result,
            "sell_trade": sell_result,
            "estimated_profit_bps": edge_bps,
        }

    async def monitor_positions(self) -> dict[str, Any]:
        """Monitor open positions and check for exit signals.

        Returns:
            Position monitoring report
        """
        positions = await self.alpaca.get_positions()

        position_analysis = []
        for symbol, quantity in positions.items():
            # Get current account to check P&L
            # In a real implementation, calculate actual P&L
            position_analysis.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "status": "monitoring",
                }
            )

        return {
            "total_positions": len(positions),
            "positions": position_analysis,
        }

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get AI trading performance metrics.

        Returns:
            Performance statistics
        """
        total_trades = len(self.trade_history)
        successful_trades = sum(
            1 for t in self.trade_history if t.get("status") != "failed"
        )

        return {
            "total_trades": total_trades,
            "successful_trades": successful_trades,
            "success_rate": (
                successful_trades / total_trades if total_trades > 0 else 0
            ),
            "active_trades": len(self.active_trades),
            "trade_history": self.trade_history[-10:],  # Last 10 trades
        }
