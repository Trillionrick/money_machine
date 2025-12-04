"""AI-powered Aqua event analyzer for profitable trading opportunities.

This module monitors Aqua Protocol events across chains and identifies
profitable trading opportunities based on liquidity movements and strategy signals.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import structlog
from web3 import AsyncWeb3, Web3

from src.ai.decider import AICandidate, AIDecider, AIConfig
from src.dex.aqua_client import AquaClient, AquaEvent
from src.dex.flash_loan_executor import FlashLoanExecutor
from src.dex.uniswap_connector import UniswapConnector
from src.brokers.price_fetcher import CEXPriceFetcher

log = structlog.get_logger()


@dataclass
class AquaOpportunityConfig:
    """Configuration for Aqua opportunity detection."""

    # Minimum thresholds
    min_pushed_amount_usd: float = 10_000.0  # Only track large deposits (10k+)
    min_profit_usd: float = 100.0  # Minimum profit to pursue
    min_confidence: float = 0.7  # AI confidence threshold

    # Strategy tracking
    track_successful_strategies: bool = True  # Learn from profitable strategies
    strategy_cooldown_seconds: int = 300  # Wait 5min before copying same strategy

    # Execution settings
    enable_copy_trading: bool = False  # Copy successful strategies (RISKY - test first!)
    enable_counter_trading: bool = True  # Trade against whale exits
    max_position_size_usd: float = 5_000.0  # Max position per opportunity

    # Risk management
    max_slippage_bps: float = 50.0  # 0.5% max slippage
    gas_price_limit_gwei: float = 100.0  # Don't trade if gas too high


@dataclass
class AquaOpportunity:
    """Detected opportunity from Aqua events."""

    event: AquaEvent
    opportunity_type: str  # "whale_entry", "whale_exit", "strategy_copy", "arbitrage"
    token_address: str
    estimated_profit_usd: float
    confidence: float
    action: str  # "buy", "sell", "flash_loan_arb"
    reasoning: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AquaOpportunityDetector:
    """Monitors Aqua events and detects profitable trading opportunities."""

    def __init__(
        self,
        w3_ethereum: AsyncWeb3,
        w3_polygon: AsyncWeb3,
        config: AquaOpportunityConfig,
        ai_decider: AIDecider,
        uniswap_connector: UniswapConnector,
        price_fetcher: CEXPriceFetcher,
        flash_executor: Optional[FlashLoanExecutor] = None,
    ):
        self.w3_eth = w3_ethereum
        self.w3_polygon = w3_polygon
        self.config = config
        self.ai_decider = ai_decider
        self.uniswap = uniswap_connector
        self.price_fetcher = price_fetcher
        self.flash_executor = flash_executor

        # Initialize Aqua clients
        self.aqua_eth = AquaClient(w3_ethereum, chain_id=1)
        self.aqua_polygon = AquaClient(w3_polygon, chain_id=137)

        # Tracking
        self.strategy_tracker: dict[str, list[AquaEvent]] = {}  # strategy_hash -> events
        self.last_strategy_copy: dict[str, datetime] = {}  # cooldown tracker
        self.opportunities_found: list[AquaOpportunity] = []
        self.trades_executed: int = 0

        # Token price cache (for USD conversion)
        self.token_prices: dict[str, float] = {}

    async def get_token_price_usd(self, token_address: str, chain_id: int) -> float:
        """Get token price in USD (from cache or fetch)."""
        cache_key = f"{chain_id}:{token_address.lower()}"

        if cache_key in self.token_prices:
            return self.token_prices[cache_key]

        # Try to get price from common tokens
        common_prices = {
            "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 1.0,  # USDC
            "0xdac17f958d2ee523a2206206994597c13d831ec7": 1.0,  # USDT
            "0x6b175474e89094c44da98b954eedeac495271d0f": 1.0,  # DAI
            "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": 3000.0,  # WETH (~$3k)
        }

        price = common_prices.get(token_address.lower(), 1.0)
        self.token_prices[cache_key] = price
        return price

    async def analyze_pushed_event(self, event: AquaEvent) -> Optional[AquaOpportunity]:
        """Analyze a Pushed event (token deposit) for opportunities.

        Strategy: Large deposits often precede profitable strategies.
        If a whale deposits 100k USDC, they likely expect to profit.
        We can copy their entry or prepare for exit arbitrage.
        """
        if not event.token or not event.amount:
            return None

        # Convert amount to USD
        token_decimals = 6  # Assume USDC/USDT for now
        amount = event.amount / (10 ** token_decimals)
        token_price = await self.get_token_price_usd(event.token, event.chain_id or 1)
        amount_usd = amount * token_price

        # Only track large deposits
        if amount_usd < self.config.min_pushed_amount_usd:
            return None

        log.info(
            "aqua.large_deposit",
            maker=event.maker,
            token=event.token,
            amount_usd=amount_usd,
            chain_id=event.chain_id,
        )

        # Track this strategy
        if event.strategy_hash:
            if event.strategy_hash not in self.strategy_tracker:
                self.strategy_tracker[event.strategy_hash] = []
            self.strategy_tracker[event.strategy_hash].append(event)

        # Opportunity: Copy large whale entries (if enabled)
        if self.config.enable_copy_trading:
            confidence = 0.6 if amount_usd > 100_000 else 0.5

            return AquaOpportunity(
                event=event,
                opportunity_type="whale_entry",
                token_address=event.token,
                estimated_profit_usd=amount_usd * 0.02,  # Assume 2% profit potential
                confidence=confidence,
                action="buy",
                reasoning=f"Whale deposited ${amount_usd:,.0f} - likely profitable strategy incoming",
            )

        return None

    async def analyze_pulled_event(self, event: AquaEvent) -> Optional[AquaOpportunity]:
        """Analyze a Pulled event (token withdrawal) for opportunities.

        Strategy: Large withdrawals indicate strategy completion.
        We can analyze if it was profitable and counter-trade or copy.
        """
        if not event.token or not event.amount or not event.strategy_hash:
            return None

        # Get corresponding Pushed event to calculate profit
        strategy_events = self.strategy_tracker.get(event.strategy_hash, [])
        pushed_events = [e for e in strategy_events if e.name == "Pushed"]

        if not pushed_events:
            return None

        # Calculate profit/loss
        token_decimals = 6
        pulled_amount = event.amount / (10 ** token_decimals)
        pushed_amount = sum(e.amount or 0 for e in pushed_events) / (10 ** token_decimals)

        token_price = await self.get_token_price_usd(event.token, event.chain_id or 1)
        profit_usd = (pulled_amount - pushed_amount) * token_price

        log.info(
            "aqua.strategy_completed",
            strategy_hash=event.strategy_hash,
            profit_usd=profit_usd,
            roi_pct=(profit_usd / (pushed_amount * token_price)) * 100 if pushed_amount > 0 else 0,
        )

        # If profitable, consider counter-trading or copying
        if profit_usd > self.config.min_profit_usd:
            # Counter-trade: Whale just exited, might cause price dip
            if self.config.enable_counter_trading:
                confidence = 0.7 if profit_usd > 1000 else 0.6

                return AquaOpportunity(
                    event=event,
                    opportunity_type="whale_exit",
                    token_address=event.token,
                    estimated_profit_usd=profit_usd * 0.1,  # 10% of their profit
                    confidence=confidence,
                    action="buy",  # Buy the dip from their exit
                    reasoning=f"Whale exited with ${profit_usd:,.0f} profit - expect price recovery",
                )

        return None

    async def analyze_shipped_event(self, event: AquaEvent) -> Optional[AquaOpportunity]:
        """Analyze a Shipped event (strategy deployed) for opportunities.

        Strategy: Track new strategies from successful traders.
        """
        if not event.strategy_hash:
            return None

        # Check if this maker has been profitable before
        maker_strategies = [
            s for s, events in self.strategy_tracker.items()
            if any(e.maker == event.maker for e in events)
        ]

        profitable_count = 0
        for strategy_hash in maker_strategies:
            events = self.strategy_tracker[strategy_hash]
            pushed = sum(e.amount or 0 for e in events if e.name == "Pushed")
            pulled = sum(e.amount or 0 for e in events if e.name == "Pulled")
            if pulled > pushed:
                profitable_count += 1

        # If maker has >70% win rate, track their new strategy
        if len(maker_strategies) >= 3 and profitable_count / len(maker_strategies) > 0.7:
            log.info(
                "aqua.profitable_trader_detected",
                maker=event.maker,
                win_rate=profitable_count / len(maker_strategies),
                new_strategy=event.strategy_hash,
            )

            if self.config.enable_copy_trading:
                # Check cooldown
                last_copy = self.last_strategy_copy.get(event.maker)
                if last_copy:
                    elapsed = (datetime.now(timezone.utc) - last_copy).total_seconds()
                    if elapsed < self.config.strategy_cooldown_seconds:
                        return None

                self.last_strategy_copy[event.maker] = datetime.now(timezone.utc)

                return AquaOpportunity(
                    event=event,
                    opportunity_type="strategy_copy",
                    token_address="",  # Will be determined from strategy
                    estimated_profit_usd=500.0,  # Conservative estimate
                    confidence=0.75,
                    action="copy_strategy",
                    reasoning=f"Profitable trader ({profitable_count}/{len(maker_strategies)} wins) deployed new strategy",
                )

        return None

    async def execute_opportunity(self, opportunity: AquaOpportunity) -> bool:
        """Execute a detected opportunity (if confidence high enough)."""
        if opportunity.confidence < self.config.min_confidence:
            log.info("aqua.opportunity_skipped", reason="low_confidence", opp=opportunity)
            return False

        log.info(
            "aqua.opportunity_executing",
            type=opportunity.opportunity_type,
            action=opportunity.action,
            estimated_profit=opportunity.estimated_profit_usd,
            confidence=opportunity.confidence,
        )

        try:
            # Route to appropriate execution method
            if opportunity.action == "flash_loan_arb" and self.flash_executor:
                return await self._execute_flash_arb(opportunity)
            elif opportunity.action in ("buy", "sell"):
                return await self._execute_spot_trade(opportunity)
            elif opportunity.action == "copy_strategy":
                return await self._copy_strategy(opportunity)

            return False

        except Exception as e:
            log.exception("aqua.execution_failed", error=str(e))
            return False

    async def _execute_flash_arb(self, opportunity: AquaOpportunity) -> bool:
        """Execute flash loan arbitrage based on opportunity."""
        if not self.flash_executor:
            log.warning("aqua.flash_executor_unavailable")
            return False

        log.info("aqua.flash_arb_execution", opportunity=opportunity)

        try:
            # Calculate borrow amount based on opportunity size
            max_borrow_usd = min(
                opportunity.estimated_profit_usd * 10,  # 10x leverage
                self.config.max_position_size_usd,
            )

            # Convert USD to ETH (assuming WETH flash loan)
            eth_price = await self.get_token_price_usd(
                "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
                opportunity.event.chain_id,
            )
            if eth_price <= 0:
                log.warning("aqua.eth_price_unavailable")
                return False

            borrow_amount_eth = max_borrow_usd / eth_price

            # Build arbitrage plan
            arb_plan = self.flash_executor.build_weth_usdc_arb_plan(
                borrow_amount_eth=borrow_amount_eth,
                expected_profit_eth=opportunity.estimated_profit_usd / eth_price,
                min_profit_eth=self.config.min_profit_usd / eth_price,
            )

            # Calculate profitability
            borrow_wei = Web3.to_wei(borrow_amount_eth, "ether")
            profit_wei = Web3.to_wei(opportunity.estimated_profit_usd / eth_price, "ether")

            profitability = self.flash_executor.calculate_profitability(
                borrow_amount=borrow_wei,
                expected_profit=profit_wei,
            )

            if not profitability.is_profitable:
                log.info("aqua.flash_arb_not_profitable", net_profit=profitability.net_profit)
                return False

            # Execute flash loan
            log.info(
                "aqua.flash_arb_executing",
                borrow_eth=borrow_amount_eth,
                expected_profit_eth=opportunity.estimated_profit_usd / eth_price,
            )

            # This would execute the actual flash loan transaction
            # For now, return True to indicate success in dry-run mode
            # In production, would call: tx_hash = await self.flash_executor.execute(arb_plan)

            log.info("aqua.flash_arb_success", opportunity_type=opportunity.opportunity_type)
            return True

        except Exception:
            log.exception("aqua.flash_arb_failed")
            return False

    async def _execute_spot_trade(self, opportunity: AquaOpportunity) -> bool:
        """Execute a spot trade (buy/sell) based on opportunity."""
        log.info("aqua.spot_trade_execution", opportunity=opportunity)

        try:
            # Calculate trade size in USD
            trade_size_usd = min(
                self.config.max_position_size_usd,
                opportunity.estimated_profit_usd * 5,  # Size based on expected profit
            )

            # Get token price
            token_price_usd = await self.get_token_price_usd(
                opportunity.token_address, opportunity.event.chain_id
            )
            if token_price_usd <= 0:
                log.warning("aqua.token_price_unavailable", token=opportunity.token_address)
                return False

            # Calculate token amount
            token_amount = trade_size_usd / token_price_usd

            # Determine token pair (assume trading against USDC)
            usdc_address = (
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"  # Ethereum USDC
                if opportunity.event.chain_id == 1
                else "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # Polygon USDC
            )

            if opportunity.action == "buy":
                # Buy token with USDC
                amount_in = Decimal(str(trade_size_usd))  # USDC amount
                token_in = usdc_address
                token_out = opportunity.token_address

                log.info(
                    "aqua.spot_buy",
                    token_out=token_out,
                    usdc_amount=float(amount_in),
                    expected_tokens=token_amount,
                )

                # Get quote from Uniswap
                quote = await self.uniswap.get_quote(
                    token_in=token_in,
                    token_out=token_out,
                    amount_in=amount_in,
                    fee_tier=3000,  # 0.3% fee tier
                )

                if not quote or quote.amount_out <= 0:
                    log.warning("aqua.quote_failed")
                    return False

                # Check slippage
                expected_out = Decimal(str(token_amount))
                slippage_bps = (
                    abs(float(quote.amount_out - expected_out)) / float(expected_out) * 10_000
                )

                if slippage_bps > self.config.max_slippage_bps:
                    log.warning(
                        "aqua.slippage_too_high",
                        slippage_bps=slippage_bps,
                        max=self.config.max_slippage_bps,
                    )
                    return False

                # Execute swap (dry-run mode for now)
                log.info("aqua.spot_buy_ready", quote=float(quote.amount_out))
                # In production: tx_hash = await self.uniswap.execute_swap(...)
                return True

            elif opportunity.action == "sell":
                # Sell token for USDC
                amount_in = Decimal(str(token_amount))
                token_in = opportunity.token_address
                token_out = usdc_address

                log.info(
                    "aqua.spot_sell",
                    token_in=token_in,
                    token_amount=float(amount_in),
                    expected_usdc=trade_size_usd,
                )

                # Get quote from Uniswap
                quote = await self.uniswap.get_quote(
                    token_in=token_in,
                    token_out=token_out,
                    amount_in=amount_in,
                    fee_tier=3000,
                )

                if not quote or quote.amount_out <= 0:
                    log.warning("aqua.quote_failed")
                    return False

                # Check slippage
                expected_out = Decimal(str(trade_size_usd))
                slippage_bps = (
                    abs(float(quote.amount_out - expected_out)) / float(expected_out) * 10_000
                )

                if slippage_bps > self.config.max_slippage_bps:
                    log.warning(
                        "aqua.slippage_too_high",
                        slippage_bps=slippage_bps,
                        max=self.config.max_slippage_bps,
                    )
                    return False

                # Execute swap (dry-run mode for now)
                log.info("aqua.spot_sell_ready", usdc_quote=float(quote.amount_out))
                # In production: tx_hash = await self.uniswap.execute_swap(...)
                return True

            else:
                log.warning("aqua.unknown_action", action=opportunity.action)
                return False

        except Exception:
            log.exception("aqua.spot_trade_failed")
            return False

    async def _copy_strategy(self, opportunity: AquaOpportunity) -> bool:
        """Copy a profitable trader's strategy."""
        log.info("aqua.strategy_copy", opportunity=opportunity)

        try:
            # Get strategy details from the event
            strategy_hash = opportunity.event.strategy_hash
            maker = opportunity.event.maker

            # Track strategy for monitoring
            if strategy_hash not in self.strategy_tracker:
                self.strategy_tracker[strategy_hash] = []
            self.strategy_tracker[strategy_hash].append(opportunity.event)

            # Monitor subsequent Pushed events to see what the whale does
            # This is a simplified implementation - production would:
            # 1. Decode strategy bytes to understand the trading logic
            # 2. Monitor all subsequent events for this strategy
            # 3. Replicate the whale's actions with a delay

            log.info(
                "aqua.strategy_copy_monitoring",
                strategy=strategy_hash,
                maker=maker,
                event_count=len(self.strategy_tracker[strategy_hash]),
            )

            # For now, we'll wait for the whale to make their first move (Pushed event)
            # Then copy their position after validation

            # Check if we've seen a Pushed event for this strategy
            pushed_events = [
                e for e in self.strategy_tracker[strategy_hash] if e.name == "Pushed"
            ]

            if not pushed_events:
                log.info("aqua.strategy_copy_waiting", strategy=strategy_hash)
                return False

            # Use the most recent Pushed event to determine position
            latest_push = pushed_events[-1]

            # Calculate copy size (smaller than whale's position)
            whale_size_usd = latest_push.amount  # Assuming amount is in USD
            copy_size_usd = min(
                whale_size_usd * 0.1,  # Copy 10% of whale's position
                self.config.max_position_size_usd,
            )

            # Execute spot trade to enter same position
            copy_opportunity = AquaOpportunity(
                event=latest_push,
                opportunity_type="strategy_copy",
                token_address=latest_push.token,
                estimated_profit_usd=copy_size_usd * 0.05,  # Assume 5% profit target
                confidence=opportunity.confidence,
                action="buy",  # Assume entering long position
                reasoning=f"Copying profitable trader {maker[:10]}... strategy {strategy_hash[:10]}...",
            )

            # Execute the copy trade
            success = await self._execute_spot_trade(copy_opportunity)

            if success:
                log.info(
                    "aqua.strategy_copied",
                    strategy=strategy_hash,
                    size_usd=copy_size_usd,
                    whale_size_usd=whale_size_usd,
                )

            return success

        except Exception:
            log.exception("aqua.strategy_copy_failed")
            return False

    async def process_event(self, event: AquaEvent) -> None:
        """Process a single Aqua event and detect opportunities."""
        opportunity: Optional[AquaOpportunity] = None

        if event.name == "Pushed":
            opportunity = await self.analyze_pushed_event(event)
        elif event.name == "Pulled":
            opportunity = await self.analyze_pulled_event(event)
        elif event.name == "Shipped":
            opportunity = await self.analyze_shipped_event(event)
        elif event.name == "Docked":
            # Strategy terminated - just track it
            log.info("aqua.strategy_docked", strategy=event.strategy_hash)

        if opportunity:
            self.opportunities_found.append(opportunity)

            # Execute if configured
            if self.config.enable_copy_trading or self.config.enable_counter_trading:
                success = await self.execute_opportunity(opportunity)
                if success:
                    self.trades_executed += 1
            else:
                log.info(
                    "aqua.opportunity_detected_dry_run",
                    type=opportunity.opportunity_type,
                    profit_est=opportunity.estimated_profit_usd,
                    action=opportunity.action,
                    reasoning=opportunity.reasoning,
                )

    def get_stats(self) -> dict:
        """Get detector statistics."""
        return {
            "opportunities_found": len(self.opportunities_found),
            "trades_executed": self.trades_executed,
            "strategies_tracked": len(self.strategy_tracker),
            "total_estimated_profit_usd": sum(o.estimated_profit_usd for o in self.opportunities_found),
        }
