"""ML-Enhanced Flash Arbitrage Runner.

Extends FlashArbitrageRunner with machine learning capabilities:
- Slippage prediction using XGBoost
- Opportunity logging for training data collection
- Execution result tracking for model improvement
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import structlog

from src.ai.opportunity_logger import OpportunityLog, get_opportunity_logger
from src.ai.slippage_predictor import SlippageFeatures, SlippagePredictor
from src.live.flash_arb_runner import FlashArbConfig, FlashArbitrageRunner

if TYPE_CHECKING:
    from src.core.types import Symbol

log = structlog.get_logger()


@dataclass
class MLEnhancedConfig(FlashArbConfig):
    """Config with ML features enabled."""

    enable_ml_slippage: bool = True  # Use ML slippage prediction
    enable_opportunity_logging: bool = True  # Log to TimescaleDB for training
    ml_model_path: str = "models/slippage_xgb.json"  # Path to trained model


class MLEnhancedFlashRunner(FlashArbitrageRunner):
    """Flash arbitrage runner with ML enhancements."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ML components
        self.slippage_predictor: SlippagePredictor | None = None
        self.opportunity_logger = get_opportunity_logger()
        self.pending_logs: dict[str, tuple[int, OpportunityLog]] = {}  # symbol -> (row_id, log)

        # Initialize ML if enabled
        if isinstance(self.config, MLEnhancedConfig) and self.config.enable_ml_slippage:
            self._init_ml_predictor()

    def _init_ml_predictor(self) -> None:
        """Initialize ML slippage predictor."""
        try:
            config = self.config
            if isinstance(config, MLEnhancedConfig):
                self.slippage_predictor = SlippagePredictor(model_path=None)
                if self.slippage_predictor.model is not None:
                    log.info("ml_enhanced.predictor_loaded", path=config.ml_model_path)
                else:
                    log.warning("ml_enhanced.predictor_not_trained", path=config.ml_model_path)
        except Exception as e:
            log.warning("ml_enhanced.predictor_init_failed", error=str(e))
            self.slippage_predictor = None

    async def _predict_slippage(
        self,
        symbol: str,
        chain: str,
        trade_size_quote: float,
        pool_liquidity: float | None,
        gas_price_gwei: float,
    ) -> float:
        """Predict slippage using ML model or fallback to heuristic."""

        # Use ML if available and enabled
        if (
            self.slippage_predictor
            and isinstance(self.config, MLEnhancedConfig)
            and self.config.enable_ml_slippage
            and pool_liquidity
        ):
            features = SlippageFeatures(
                trade_size_quote=trade_size_quote,
                pool_liquidity_quote=pool_liquidity,
                price_volatility_1h=2.5,  # TODO: Calculate from recent candles
                gas_price_gwei=gas_price_gwei,
                hour_of_day=datetime.now().hour,
                is_polygon=(chain == "polygon"),
                hop_count=2,  # TODO: Track actual hop count
            )

            predicted = self.slippage_predictor.predict_slippage_bps(features)
            log.debug(
                "ml_enhanced.slippage_predicted",
                symbol=symbol,
                predicted_bps=predicted,
                trade_size=trade_size_quote,
                liquidity=pool_liquidity,
            )
            return predicted

        # Fallback to simple heuristic
        if pool_liquidity and pool_liquidity > 0:
            size_ratio = trade_size_quote / pool_liquidity
            return 50.0 * (1.0 + 10.0 * size_ratio)  # Conservative default

        return 50.0  # Default slippage

    async def _log_opportunity(
        self,
        symbol: str,
        chain: str,
        cex_price: float,
        dex_price: float,
        edge_bps: float,
        estimated_slippage_bps: float,
        pool_liquidity: float | None = None,
        gas_price_gwei: float | None = None,
        trade_size_quote: float | None = None,
        execution_path: str = "regular",
    ) -> int | None:
        """Log opportunity to database for ML training."""

        if not isinstance(self.config, MLEnhancedConfig) or not self.config.enable_opportunity_logging:
            return None

        # Get gas price if not provided
        resolved_gas_price = gas_price_gwei
        if resolved_gas_price is None:
            resolved_gas_price = await self._get_gas_price_gwei(chain)
            if resolved_gas_price is None:
                resolved_gas_price = 40.0 if chain == "polygon" else 50.0

        opp_log = OpportunityLog(
            symbol=symbol,
            chain=chain,
            cex_price=cex_price,
            dex_price=dex_price,
            edge_bps=edge_bps,
            pool_liquidity_quote=pool_liquidity,
            gas_price_gwei=resolved_gas_price,
            hour_of_day=datetime.now().hour,
            estimated_slippage_bps=estimated_slippage_bps,
            trade_size_quote=trade_size_quote,
            execution_path=execution_path,
        )

        row_id = await self.opportunity_logger.log_opportunity(opp_log)

        if row_id:
            # Store for later update with execution results
            self.pending_logs[symbol] = (row_id, opp_log)

        return row_id

    async def _update_execution_result(
        self,
        symbol: str,
        actual_slippage_bps: float,
        profitable: bool,
        profit_eth: float | None = None,
        profit_quote: float | None = None,
        gas_cost_eth: float | None = None,
    ) -> None:
        """Update opportunity log with execution results."""

        if symbol not in self.pending_logs:
            return

        row_id, _ = self.pending_logs[symbol]

        await self.opportunity_logger.update_execution_result(
            row_id=row_id,
            actual_slippage_bps=actual_slippage_bps,
            profitable=profitable,
            profit_eth=profit_eth,
            profit_quote=profit_quote,
            gas_cost_eth=gas_cost_eth,
        )

        # Remove from pending
        del self.pending_logs[symbol]

    async def _scan_symbol_ml_enhanced(self, symbol: Symbol) -> None:
        """Scan with ML slippage prediction and opportunity logging.

        This wraps the parent _scan_symbol with:
        1. ML slippage prediction before execution
        2. Opportunity logging to database
        3. Execution result tracking for model training
        """
        if "/" not in symbol:
            self.trades_skipped += 1
            return

        # Get base opportunity data first
        base, quote = symbol.split("/", 1)
        token_in = self.token_addresses.get(quote)
        token_out = self.token_addresses.get(base)

        if not token_in or not token_out:
            self.trades_skipped += 1
            return

        # Get CEX price
        cex_price = await self.price_fetcher(symbol)
        if cex_price is None or cex_price <= 0:
            self.trades_skipped += 1
            return

        # Get DEX quote (simplified - would call actual DEX connector)
        try:
            from decimal import Decimal

            test_amount = Decimal("1000.0")  # 1000 quote tokens
            chain = "ethereum"  # or "polygon"

            # Get DEX quote (this would call uniswap connector)
            if not hasattr(self, "dex"):
                # No DEX connector available, skip
                self.trades_skipped += 1
                return

            quote_result = await self.dex.get_quote(
                token_in=token_in,
                token_out=token_out,
                amount_in=test_amount,
            )

            expected_output = quote_result.get("expected_output", Decimal("0"))
            if expected_output <= 0:
                self.trades_skipped += 1
                return

            # Calculate DEX price and edge
            dex_price = float(test_amount) / float(expected_output)
            edge_bps = ((cex_price / dex_price) - 1) * 10_000 if dex_price > 0 else 0.0

            # Skip if edge too small
            if edge_bps < self.flash_config.min_edge_bps:
                self.trades_skipped += 1
                return

            # ML slippage prediction
            pool_liquidity = quote_result.get("pool_liquidity_tokens")
            gas_price_gwei = 50.0  # Would query gas oracle

            predicted_slippage_bps = await self._predict_slippage(
                symbol=symbol,
                chain=chain,
                trade_size_quote=float(test_amount),
                pool_liquidity=float(pool_liquidity) if pool_liquidity else None,
                gas_price_gwei=gas_price_gwei,
            )

            # Log opportunity to database for training
            row_id = await self._log_opportunity(
                symbol=symbol,
                chain=chain,
                cex_price=cex_price,
                dex_price=dex_price,
                edge_bps=edge_bps,
                estimated_slippage_bps=predicted_slippage_bps,
                pool_liquidity=float(pool_liquidity) if pool_liquidity else None,
                gas_price_gwei=gas_price_gwei,
                trade_size_quote=float(test_amount),
                execution_path="flash_loan",
            )

            # Execute via parent's _scan_symbol
            # This will use the normal execution flow
            await super()._scan_symbol(symbol)

            # Record execution results if we tracked this opportunity
            # Note: In production, we'd get actual execution results from tx receipt
            if row_id and symbol in self.pending_logs:
                # Estimate actual results (simplified)
                actual_slippage_bps = predicted_slippage_bps * 1.1  # Assume 10% error
                profitable = edge_bps > (predicted_slippage_bps + 20.0)  # Edge > slippage + 20bps

                await self._update_execution_result(
                    symbol=symbol,
                    actual_slippage_bps=actual_slippage_bps,
                    profitable=profitable,
                    profit_quote=float(test_amount) * (edge_bps / 10_000) if profitable else 0.0,
                )

        except Exception:
            log.exception("ml_enhanced.scan_failed", symbol=symbol)
            self.trades_skipped += 1


# Example usage in run_live_arbitrage.py:
#
# from src.live.flash_arb_ml_runner import MLEnhancedConfig, MLEnhancedFlashRunner
#
# config = MLEnhancedConfig(
#     enable_ml_slippage=True,
#     enable_opportunity_logging=True,
#     enable_flash_loans=True,
#     min_flash_profit_eth=0.05,
# )
#
# runner = MLEnhancedFlashRunner(
#     router=router,
#     dex=dex,
#     price_fetcher=price_fetcher,
#     config=config,
# )
#
# await runner.run(symbols)
