"""Enhanced arbitrage runner with flash loan execution.

Combines the existing CEX/DEX arbitrage scanner with flash loan capabilities
for executing larger, capital-free arbitrage trades.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Awaitable, Callable, cast

import structlog
from web3 import Web3

from src.ai.decider import AIDecision
from src.dex.flash_loan_executor import FlashLoanExecutor, FlashLoanSettings, ProfitabilityCheck
from src.live.arbitrage_runner import ArbitrageConfig, ArbitrageRunner, PriceFetcher
from src.brokers.routing import OrderRouter
from src.core.types import Price, Symbol
from src.dex.uniswap_connector import UniswapConnector

log = structlog.get_logger()


@dataclass
class FlashArbConfig(ArbitrageConfig):
    """Extended config for flash loan arbitrage with dynamic parameters.

    Modern 2025 configuration with adaptive thresholds and risk management.
    """

    # Flash loan execution settings
    min_flash_profit_eth: float = 0.15  # Minimum profit (reduced from 0.5 for more opportunities)
    max_flash_borrow_eth: float = 100.0  # Maximum to borrow per trade
    min_flash_borrow_eth: float = 5.0  # Minimum to borrow (avoid tiny trades)
    enable_flash_loans: bool = False  # Enable flash loan execution
    flash_loan_threshold_bps: float = 50.0  # Min spread to consider flash loans (0.5%, reduced from 1%)
    flash_loan_execution_timeout: float = 90.0  # Seconds to wait before aborting a stuck txn

    # Dynamic sizing based on edge
    enable_dynamic_sizing: bool = True  # Adjust borrow amount based on opportunity quality
    min_size_multiplier: float = 0.3  # Scale down to 30% for marginal opportunities
    max_size_multiplier: float = 1.0  # Full size for optimal opportunities

    # Fee stack configuration (adjusted for 2025 gas prices)
    gas_price_multiplier: float = 2.5  # Reduced from implicit 3x to 2.5x for tighter margins
    slippage_buffer_bps: float = 15.0  # Reduced from implicit higher values

    # Profitability thresholds
    min_roi_bps: float = 25.0  # Minimum ROI in basis points (0.25%)
    target_roi_bps: float = 100.0  # Target ROI for full-size trades (1%)

    # Risk management
    enable_profit_floor: bool = True  # Enforce minimum profit floor
    enable_gas_margin_check: bool = True  # Require 2x gas coverage
    enable_fee_stack_check: bool = True  # Require profit > total fee stack

    # Use smaller amounts for regular CEX/DEX arb
    max_notional: float = 100.0  # Smaller for non-flash trades


@dataclass
class FlashArbitrageRunner(ArbitrageRunner):
    """Arbitrage runner with flash loan execution capabilities."""

    flash_executor: FlashLoanExecutor | None = None
    on_opportunity: Callable[[dict], Awaitable[None] | None] | None = None
    on_trade: Callable[[dict], Awaitable[None] | None] | None = None

    flash_executions: int = 0
    flash_failures: int = 0

    @property
    def flash_config(self) -> FlashArbConfig:
        """Get config as FlashArbConfig with proper typing."""
        return cast(FlashArbConfig, self.config)

    def __post_init__(self) -> None:
        """Initialize flash loan executor if enabled."""
        super().__post_init__()
        # Type guard: ensure config is FlashArbConfig
        if not isinstance(self.config, FlashArbConfig):
            raise TypeError(f"FlashArbitrageRunner requires FlashArbConfig, got {type(self.config)}")

        # Cast for type checker - we've verified it's FlashArbConfig above
        flash_config = cast(FlashArbConfig, self.config)

        if flash_config.enable_flash_loans and self.flash_executor is None:
            try:
                self.flash_executor = FlashLoanExecutor()
                log.info("flash_arb.executor_initialized")
            except Exception:
                log.exception("flash_arb.executor_init_failed")
                flash_config.enable_flash_loans = False

    async def _scan_symbol(self, symbol: Symbol) -> None:
        """Scan symbol and choose between regular or flash loan arbitrage."""
        if "/" not in symbol:
            self.trades_skipped += 1
            return

        base, quote = symbol.split("/", 1)
        token_in = self.token_addresses.get(quote)
        token_out = self.token_addresses.get(base)
        polygon_token_in = (
            self.polygon_token_addresses.get(quote) if self.polygon_token_addresses else token_in
        )
        polygon_token_out = (
            self.polygon_token_addresses.get(base) if self.polygon_token_addresses else token_out
        )

        if not token_in or not token_out:
            self.trades_skipped += 1
            return

        # Get CEX price
        cex_price = await self.price_fetcher(symbol)
        if cex_price is None or cex_price <= 0:
            self.trades_skipped += 1
            return

        # Get DEX quote for small amount first
        test_amount = Decimal("1.0")  # 1 unit for price discovery
        candidates = await self._collect_quotes(
            symbol=symbol,
            base_symbol=base,
            quote_symbol=quote,
            token_in=token_in,
            token_out=token_out,
            polygon_token_in=polygon_token_in,
            polygon_token_out=polygon_token_out,
            amount_in=test_amount,
            cex_price=cex_price,
            cross_chain=True,
        )
        best = self._pick_best_candidate(candidates)
        if not best:
            self.trades_skipped += 1
            return

        dex_price = best.price
        edge_bps = best.net_edge_bps

        log.debug(
            "flash_arb.price_check",
            symbol=symbol,
            chain=best.chain,
            source=best.source,
            cex_price=cex_price,
            dex_price=dex_price,
            edge_bps=edge_bps,
            raw_edge_bps=best.raw_edge_bps,
        )

        # Decide execution method based on spread
        if (
            self.flash_config.enable_flash_loans
            and self.flash_executor
            and best.chain != "polygon"  # Flash loan infra assumed on mainnet for now
            and edge_bps >= self.flash_config.flash_loan_threshold_bps
        ):
            await self._emit_opportunity(
                {
                    "symbol": symbol,
                    "edge_bps": edge_bps,
                    "cex_price": cex_price,
                    "dex_price": dex_price,
                    "execution_path": "flash_loan",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            # Large spread - use flash loan for bigger size
            await self._execute_flash_arb(symbol, token_in, token_out, cex_price, dex_price, edge_bps)
        elif edge_bps >= self.config.min_edge_bps:
            await self._emit_opportunity(
                {
                    "symbol": symbol,
                    "edge_bps": edge_bps,
                    "cex_price": cex_price,
                    "dex_price": dex_price,
                    "execution_path": "regular",
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            # Small spread - use regular CEX/DEX arb
            await self._execute_regular_arb(symbol, token_in, token_out, cex_price)
        else:
            # No opportunity
            self.trades_skipped += 1

    async def _execute_flash_arb(
        self,
        symbol: Symbol,
        token_in: str,
        token_out: str,
        cex_price: float,
        dex_price: float,
        edge_bps: float,
    ) -> None:
        """Execute arbitrage using flash loan with dynamic sizing.

        Modern 2025 implementation with adaptive position sizing based on
        opportunity quality and risk metrics.
        """
        if not self.flash_executor:
            return

        # Calculate optimal borrow amount with dynamic sizing
        if self.flash_config.enable_dynamic_sizing:
            # Scale borrow amount based on edge quality
            edge_ratio = edge_bps / self.flash_config.target_roi_bps
            size_multiplier = max(
                self.flash_config.min_size_multiplier,
                min(self.flash_config.max_size_multiplier, edge_ratio),
            )
            base_borrow = self.flash_config.max_flash_borrow_eth * size_multiplier
        else:
            # Legacy conservative sizing
            base_borrow = min(
                self.flash_config.max_flash_borrow_eth,
                self.flash_config.max_flash_borrow_eth
                * (edge_bps / self.flash_config.flash_loan_threshold_bps),
            )

        borrow_amount_eth = max(
            self.flash_config.min_flash_borrow_eth,
            min(self.flash_config.max_flash_borrow_eth, base_borrow),
        )

        # Estimate profit (simple calculation - actual will vary with slippage)
        estimated_profit_eth = borrow_amount_eth * (edge_bps / 10_000)

        log.info(
            "flash_arb.opportunity_detected",
            symbol=symbol,
            edge_bps=edge_bps,
            borrow_amount_eth=borrow_amount_eth,
            estimated_profit_eth=estimated_profit_eth,
        )

        try:
            # Build arbitrage plan
            arb_plan = self.flash_executor.build_weth_usdc_arb_plan(
                borrow_amount_eth=borrow_amount_eth,
                expected_profit_eth=estimated_profit_eth,
                min_profit_eth=self.flash_config.min_flash_profit_eth,
            )

            # Calculate profitability
            borrow_wei = Web3.to_wei(borrow_amount_eth, "ether")
            profit_wei = Web3.to_wei(estimated_profit_eth, "ether")

            profitability: ProfitabilityCheck = self.flash_executor.calculate_profitability(
                borrow_amount=borrow_wei,
                expected_profit=profit_wei,
            )

            # Modern 2025 profitability checks with configurable thresholds
            if not profitability.is_profitable and self.flash_config.enable_profit_floor:
                log.info(
                    "flash_arb.not_profitable_after_fees",
                    symbol=symbol,
                    net_profit=profitability.net_profit,
                    borrow_amount_eth=borrow_amount_eth,
                )
                self.trades_skipped += 1
                return

            # Gas margin check - use configurable multiplier
            gas_margin_factor = self.flash_config.gas_price_multiplier
            if (
                self.flash_config.enable_gas_margin_check
                and profitability.gas_cost > 0
                and profitability.net_profit < gas_margin_factor * profitability.gas_cost
            ):
                log.info(
                    "flash_arb.gas_margin_block",
                    symbol=symbol,
                    net_profit_eth=Web3.from_wei(profitability.net_profit, "ether"),
                    gas_cost_eth=Web3.from_wei(profitability.gas_cost, "ether"),
                    required_margin=gas_margin_factor,
                )
                self.trades_skipped += 1
                return

            # Fee stack check with reduced multiplier (was 2x, now configurable)
            fee_stack = int(
                profitability.flash_loan_fee
                + profitability.slippage_cost
                + (gas_margin_factor * profitability.gas_cost)
            )
            if self.flash_config.enable_fee_stack_check and profitability.net_profit < fee_stack:
                log.info(
                    "flash_arb.net_below_fee_stack",
                    symbol=symbol,
                    net_profit_eth=Web3.from_wei(profitability.net_profit, "ether"),
                    fee_stack_eth=Web3.from_wei(fee_stack, "ether"),
                )
                self.trades_skipped += 1
                return

            # ROI threshold check
            roi_threshold = self.flash_config.min_roi_bps
            if profitability.roi_bps < roi_threshold:
                log.info(
                    "flash_arb.roi_below_threshold",
                    symbol=symbol,
                    roi_bps=profitability.roi_bps,
                    min_roi_bps=roi_threshold,
                )
                self.trades_skipped += 1
                return

            log.info(
                "flash_arb.profitability_check_passed",
                symbol=symbol,
                net_profit_eth=Web3.from_wei(profitability.net_profit, "ether"),
                roi_bps=profitability.roi_bps,
            )

            if not self.config.enable_execution:
                log.info("flash_arb.dry_run", symbol=symbol)
                await self._emit_trade(
                    {
                        "symbol": symbol,
                        "mode": "flash_loan",
                        "chain": "ethereum",
                        "borrow_amount_eth": borrow_amount_eth,
                        "estimated_profit_eth": estimated_profit_eth,
                        "executed": False,
                        "tx_hash": None,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
                return

            # Execute the flash loan
            weth_address = self.flash_executor.settings.weth_address
            try:
                receipt = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.flash_executor.execute_flash_loan,
                        loan_asset=weth_address,
                        loan_amount=borrow_wei,
                        arb_plan=arb_plan,
                        dry_run=False,
                    ),
                    timeout=self.flash_config.flash_loan_execution_timeout,
                )
            except asyncio.TimeoutError:
                self.flash_failures += 1
                log.error(
                    "flash_arb.execution_timeout",
                    symbol=symbol,
                    timeout_s=self.flash_config.flash_loan_execution_timeout,
                )
                return

            if receipt and receipt["status"] == 1:
                self.flash_executions += 1
                log.info(
                    "flash_arb.execution_success",
                    symbol=symbol,
                    tx_hash=receipt["transactionHash"].hex(),
                    gas_used=receipt["gasUsed"],
                )
                await self._emit_trade(
                    {
                        "symbol": symbol,
                        "mode": "flash_loan",
                        "chain": "ethereum",
                        "borrow_amount_eth": borrow_amount_eth,
                        "estimated_profit_eth": estimated_profit_eth,
                        "executed": True,
                        "tx_hash": receipt["transactionHash"].hex(),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
            else:
                self.flash_failures += 1
                log.error("flash_arb.execution_failed", symbol=symbol, receipt=receipt)

        except Exception:
            self.flash_failures += 1
            log.exception("flash_arb.execution_error", symbol=symbol)

    async def _execute_regular_arb(
        self,
        symbol: Symbol,
        token_in: str,
        token_out: str,
        cex_price: float,
    ) -> None:
        """Execute regular CEX/DEX arbitrage (small size, from parent class)."""
        # Use parent class logic for regular arbitrage
        notional_quote = min(self.config.max_notional, cex_price * self.config.max_position)
        amount_in = Decimal(str(notional_quote))

        base_symbol, quote_symbol = symbol.split("/", 1)
        polygon_token_in = (
            self.polygon_token_addresses.get(quote_symbol)
            if self.polygon_token_addresses
            else token_in
        )
        polygon_token_out = (
            self.polygon_token_addresses.get(base_symbol)
            if self.polygon_token_addresses
            else token_out
        )

        candidates = await self._collect_quotes(
            symbol=symbol,
            base_symbol=base_symbol,
            quote_symbol=quote_symbol,
            token_in=token_in,
            token_out=token_out,
            polygon_token_in=polygon_token_in,
            polygon_token_out=polygon_token_out,
            amount_in=amount_in,
            cex_price=cex_price,
            cross_chain=True,
        )
        best = self._pick_best_candidate(candidates)
        if not best:
            self.trades_skipped += 1
            return

        base_qty = float(best.expected_output)
        if base_qty > self.config.max_position and base_qty > 0:
            scale = self.config.max_position / base_qty
            base_qty = self.config.max_position
            amount_in *= Decimal(str(scale))

        edge_bps = best.net_edge_bps

        if self.config.min_margin_bps and edge_bps < self.config.min_margin_bps:
            self.trades_skipped += 1
            log.debug(
                "flash_arb.margin_floor_block",
                chain=best.chain,
                net_edge_bps=edge_bps,
                margin_floor=self.config.min_margin_bps,
            )
            return

        notional_quote = float(amount_in) * self.config.quote_token_price
        gas_limit = self.config.polygon_gas_limit if best.chain == "polygon" else self.config.gas_limit
        gas_bps = await self._network_fee_bps(best.chain, notional_quote, gas_limit)
        if gas_bps and gas_bps > 0:
            gas_quote = notional_quote * (gas_bps / 10_000)
            net_quote = notional_quote * (edge_bps / 10_000)
            if net_quote < 2 * gas_quote:
                self.trades_skipped += 1
                log.debug(
                    "flash_arb.gas_margin_block",
                    chain=best.chain,
                    net_quote=net_quote,
                    gas_quote=gas_quote,
                )
                return

        log.info(
            "flash_arb.regular_opportunity",
            symbol=symbol,
            chain=best.chain,
            source=best.source,
            edge_bps=edge_bps,
            base_qty=base_qty,
        )

        if not self.config.enable_execution:
            await self._emit_trade(
                {
                    "symbol": symbol,
                    "mode": "regular",
                    "chain": best.chain,
                    "base_qty": base_qty,
                    "notional_quote": float(amount_in),
                    "edge_bps": edge_bps,
                    "executed": False,
                    "tx_hash": None,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            return

        dex_executor = self._resolve_executor(best.chain)
        if dex_executor is None:
            log.warning("flash_arb.no_executor_for_chain", chain=best.chain)
            self.trades_skipped += 1
            return

        # Execute via parent class method
        exec_token_in = polygon_token_in if best.chain == "polygon" else token_in
        exec_token_out = polygon_token_out if best.chain == "polygon" else token_out

        # Type guard: ensure token addresses are not None
        if exec_token_in is None or exec_token_out is None:
            log.warning(
                "flash_arb.missing_token_addresses",
                symbol=symbol,
                chain=best.chain,
                token_in=exec_token_in,
                token_out=exec_token_out,
            )
            self.trades_skipped += 1
            return

        route_id = self._route_key(best)
        tx_hash = await self._execute(
            symbol,
            exec_token_in,
            exec_token_out,
            base_qty,
            amount_in,
            dex_executor,
            route_id,
        )
        await self._emit_trade(
            {
                "symbol": symbol,
                "mode": "regular",
                "chain": best.chain,
                "base_qty": base_qty,
                "notional_quote": float(amount_in),
                "edge_bps": edge_bps,
                "executed": True,
                "tx_hash": tx_hash,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def get_stats(self) -> dict:
        """Get execution statistics."""
        return {
            "regular_trades": self.trades_executed,
            "flash_trades": self.flash_executions,
            "total_trades": self.trades_executed + self.flash_executions,
            "skipped": self.trades_skipped,
            "regular_failures": self.failures,
            "flash_failures": self.flash_failures,
            "total_failures": self.failures + self.flash_failures,
        }

    async def _emit_opportunity(self, payload: dict) -> None:
        """Notify dashboard/listeners about an opportunity if hook is provided."""
        if not self.on_opportunity:
            return

        result = self.on_opportunity(payload)
        if asyncio.iscoroutine(result):
            await result

    async def _emit_trade(self, payload: dict) -> None:
        """Notify dashboard/listeners about executed or simulated trades."""
        if not self.on_trade:
            return

        result = self.on_trade(payload)
        if asyncio.iscoroutine(result):
            await result

    async def execute_ai_flash_decision(self, decision: AIDecision) -> dict:
        """Execute an AI-approved flash-loan opportunity.

        AI must supply symbol + edge + (optional) cex/dex prices. We reuse the
        existing flash-loan pipeline so profitability is re-checked on-chain.
        """
        if not self.flash_executor:
            return {"accepted": False, "reason": "flash_executor_unavailable"}

        if not self.config.enable_execution:
            return {"accepted": False, "reason": "execution_disabled"}

        base_symbol, quote_symbol = decision.symbol.split("/", 1)
        token_out = self.token_addresses.get(base_symbol)
        token_in = self.token_addresses.get(quote_symbol)
        if not token_in or not token_out:
            return {"accepted": False, "reason": "unknown_token"}

        await self._execute_flash_arb(
            symbol=decision.symbol,
            token_in=token_in,
            token_out=token_out,
            cex_price=decision.cex_price or 0.0,
            dex_price=decision.dex_price or 0.0,
            edge_bps=decision.edge_bps,
        )
        return {"accepted": True}


async def run_flash_arbitrage_scanner(
    symbols: list[Symbol],
    router: OrderRouter,
    dex: UniswapConnector,
    price_fetcher: PriceFetcher,
    token_addresses: dict[str, str],
    config: FlashArbConfig | None = None,
) -> None:
    """Main entry point for running flash arbitrage scanner.

    Args:
        symbols: List of symbols to scan (e.g., ["ETH/USDC", "BTC/USDT"])
        router: Order router for CEX execution
        dex: Uniswap connector for DEX execution
        price_fetcher: Function to fetch CEX prices
        token_addresses: Mapping of symbols to token addresses
        config: Configuration (uses defaults if None)
    """
    cfg = config or FlashArbConfig()

    runner = FlashArbitrageRunner(
        router=router,
        dex=dex,
        price_fetcher=price_fetcher,
        token_addresses=token_addresses,
        config=cfg,
    )

    log.info(
        "flash_arb.scanner_starting",
        symbols=symbols,
        enable_flash=cfg.enable_flash_loans,
        enable_execution=cfg.enable_execution,
    )

    try:
        await runner.run(symbols)
    except KeyboardInterrupt:
        stats = runner.get_stats()
        log.info("flash_arb.scanner_stopped", stats=stats)
    except Exception:
        stats = runner.get_stats()
        log.exception("flash_arb.scanner_failed", stats=stats)
        raise
