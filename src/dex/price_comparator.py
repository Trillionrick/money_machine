"""Price comparison utilities for finding arbitrage opportunities.

This module provides tools to compare prices across CEX and DEX platforms,
identify spreads, and calculate potential profitability.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import structlog
from web3 import Web3

log = structlog.get_logger()


@dataclass
class PriceQuote:
    """Price quote from a specific source."""

    source: str  # e.g., "Uniswap V3", "OANDA", "SushiSwap"
    symbol: str  # e.g., "ETH/USDC"
    price: Decimal
    liquidity: Decimal | None = None  # Available liquidity
    timestamp: int | None = None
    gas_cost_wei: int | None = None  # Estimated gas for this route


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity between two sources."""

    symbol: str
    buy_from: PriceQuote  # Where to buy (cheaper)
    sell_to: PriceQuote  # Where to sell (expensive)
    spread_bps: Decimal  # Price difference in basis points
    estimated_profit: Decimal  # Gross profit estimate
    recommended_size: Decimal  # Optimal trade size
    confidence: str  # "high", "medium", "low"
    risk_factors: list[str]  # Potential risks


class PriceComparator:
    """Compare prices across multiple sources and identify opportunities."""

    # Basis points denominator
    BPS_DENOMINATOR = Decimal("10000")

    # Minimum thresholds
    MIN_SPREAD_BPS = Decimal("25")  # 0.25%
    MIN_LIQUIDITY = Decimal("10000")  # $10k minimum

    def __init__(
        self,
        min_spread_bps: Decimal | None = None,
        min_liquidity: Decimal | None = None,
    ):
        """Initialize price comparator.

        Args:
            min_spread_bps: Minimum spread to consider (default 25 bps)
            min_liquidity: Minimum liquidity required (default $10k)
        """
        self.min_spread_bps = min_spread_bps or self.MIN_SPREAD_BPS
        self.min_liquidity = min_liquidity or self.MIN_LIQUIDITY

    def calculate_spread_bps(self, price_1: Decimal, price_2: Decimal) -> Decimal:
        """Calculate spread between two prices in basis points.

        Args:
            price_1: First price
            price_2: Second price

        Returns:
            Absolute spread in basis points
        """
        if price_1 <= 0 or price_2 <= 0:
            return Decimal("0")

        lower_price = min(price_1, price_2)
        spread = abs(price_1 - price_2)
        spread_bps = (spread / lower_price) * self.BPS_DENOMINATOR

        return spread_bps

    def find_best_spread(
        self, quotes: list[PriceQuote]
    ) -> tuple[PriceQuote, PriceQuote, Decimal] | None:
        """Find the best spread across all quotes.

        Args:
            quotes: List of price quotes from different sources

        Returns:
            Tuple of (buy_from, sell_to, spread_bps) or None if no opportunity
        """
        if len(quotes) < 2:
            return None

        best_spread = Decimal("0")
        best_buy: PriceQuote | None = None
        best_sell: PriceQuote | None = None

        # Compare all pairs
        for i, quote_1 in enumerate(quotes):
            for quote_2 in quotes[i + 1 :]:
                spread = self.calculate_spread_bps(quote_1.price, quote_2.price)

                if spread > best_spread:
                    best_spread = spread
                    # Buy from cheaper, sell to more expensive
                    if quote_1.price < quote_2.price:
                        best_buy = quote_1
                        best_sell = quote_2
                    else:
                        best_buy = quote_2
                        best_sell = quote_1

        if best_spread < self.min_spread_bps:
            return None

        if best_buy is None or best_sell is None:
            return None

        return (best_buy, best_sell, best_spread)

    def calculate_optimal_size(
        self,
        buy_quote: PriceQuote,
        sell_quote: PriceQuote,
        max_size: Decimal,
        price_impact_threshold_bps: Decimal = Decimal("50"),
    ) -> Decimal:
        """Calculate optimal trade size considering liquidity and price impact.

        Args:
            buy_quote: Quote to buy from
            sell_quote: Quote to sell to
            max_size: Maximum position size
            price_impact_threshold_bps: Max acceptable price impact

        Returns:
            Recommended trade size
        """
        # Start with max size
        recommended = max_size

        # Limit by liquidity if available
        if buy_quote.liquidity is not None:
            # Use at most 10% of available liquidity to minimize impact
            max_from_liquidity = buy_quote.liquidity * Decimal("0.1")
            recommended = min(recommended, max_from_liquidity)

        if sell_quote.liquidity is not None:
            max_from_liquidity = sell_quote.liquidity * Decimal("0.1")
            recommended = min(recommended, max_from_liquidity)

        # Ensure minimum
        if recommended < Decimal("1"):
            recommended = Decimal("1")

        return recommended

    def estimate_profit(
        self,
        buy_quote: PriceQuote,
        sell_quote: PriceQuote,
        size: Decimal,
        flash_loan_fee_bps: Decimal = Decimal("5"),  # Aave V3 fee
    ) -> tuple[Decimal, Decimal]:
        """Estimate gross and net profit for a trade.

        Args:
            buy_quote: Quote to buy from
            sell_quote: Quote to sell to
            size: Trade size in base currency
            flash_loan_fee_bps: Flash loan fee in bps (default 0.05%)

        Returns:
            Tuple of (gross_profit, net_profit)
        """
        # Buy cost
        buy_cost = size * buy_quote.price

        # Sell revenue
        sell_revenue = size * sell_quote.price

        # Gross profit
        gross_profit = sell_revenue - buy_cost

        # Costs
        flash_loan_cost = buy_cost * flash_loan_fee_bps / self.BPS_DENOMINATOR
        gas_cost_eth = Decimal("0")

        if buy_quote.gas_cost_wei:
            gas_cost_eth = Decimal(str(Web3.from_wei(buy_quote.gas_cost_wei, "ether")))

        # Net profit
        net_profit = gross_profit - flash_loan_cost - gas_cost_eth

        return (gross_profit, net_profit)

    def assess_risk_factors(
        self, buy_quote: PriceQuote, sell_quote: PriceQuote, spread_bps: Decimal
    ) -> list[str]:
        """Assess risk factors for an arbitrage opportunity.

        Args:
            buy_quote: Quote to buy from
            sell_quote: Quote to sell to
            spread_bps: Price spread in bps

        Returns:
            List of risk factors (empty if low risk)
        """
        risks = []

        # Low liquidity
        if buy_quote.liquidity and buy_quote.liquidity < self.min_liquidity:
            risks.append(f"Low liquidity on {buy_quote.source}")

        if sell_quote.liquidity and sell_quote.liquidity < self.min_liquidity:
            risks.append(f"Low liquidity on {sell_quote.source}")

        # Very high spread (might be stale data or error)
        if spread_bps > Decimal("500"):  # 5%
            risks.append("Unusually high spread - verify prices")

        # High gas cost
        if buy_quote.gas_cost_wei and buy_quote.gas_cost_wei > 0.1 * 10**18:
            risks.append("High gas cost")

        # Stale prices (if timestamp available)
        # This would require current time comparison

        return risks

    def analyze_opportunity(
        self, quotes: list[PriceQuote], max_size: Decimal = Decimal("100")
    ) -> ArbitrageOpportunity | None:
        """Analyze quotes and identify the best arbitrage opportunity.

        Args:
            quotes: List of price quotes from different sources
            max_size: Maximum trade size

        Returns:
            ArbitrageOpportunity if found, None otherwise
        """
        # Find best spread
        result = self.find_best_spread(quotes)
        if result is None:
            return None

        buy_from, sell_to, spread_bps = result

        # Calculate optimal size
        recommended_size = self.calculate_optimal_size(buy_from, sell_to, max_size)

        # Estimate profit
        gross_profit, net_profit = self.estimate_profit(buy_from, sell_to, recommended_size)

        # Assess risks
        risk_factors = self.assess_risk_factors(buy_from, sell_to, spread_bps)

        # Determine confidence
        if len(risk_factors) == 0 and spread_bps > Decimal("100"):
            confidence = "high"
        elif len(risk_factors) <= 1 and spread_bps > Decimal("50"):
            confidence = "medium"
        else:
            confidence = "low"

        opportunity = ArbitrageOpportunity(
            symbol=buy_from.symbol,
            buy_from=buy_from,
            sell_to=sell_to,
            spread_bps=spread_bps,
            estimated_profit=net_profit,
            recommended_size=recommended_size,
            confidence=confidence,
            risk_factors=risk_factors,
        )

        log.info(
            "price_comparator.opportunity_found",
            symbol=opportunity.symbol,
            spread_bps=float(spread_bps),
            net_profit=float(net_profit),
            confidence=confidence,
            risks=risk_factors,
        )

        return opportunity

    def compare_multi_source(
        self, quotes_by_symbol: dict[str, list[PriceQuote]], max_size: Decimal = Decimal("100")
    ) -> list[ArbitrageOpportunity]:
        """Compare prices across multiple symbols and sources.

        Args:
            quotes_by_symbol: Dict mapping symbols to lists of quotes
            max_size: Maximum trade size per opportunity

        Returns:
            List of arbitrage opportunities sorted by estimated profit
        """
        opportunities = []

        for symbol, quotes in quotes_by_symbol.items():
            opp = self.analyze_opportunity(quotes, max_size)
            if opp is not None:
                opportunities.append(opp)

        # Sort by estimated profit (descending)
        opportunities.sort(key=lambda x: x.estimated_profit, reverse=True)

        return opportunities

    def format_opportunity(self, opp: ArbitrageOpportunity) -> str:
        """Format opportunity for display.

        Args:
            opp: ArbitrageOpportunity to format

        Returns:
            Formatted string
        """
        lines = [
            "=" * 60,
            f"🎯 ARBITRAGE OPPORTUNITY: {opp.symbol}",
            "=" * 60,
            f"",
            f"Buy from:  {opp.buy_from.source} @ {opp.buy_from.price}",
            f"Sell to:   {opp.sell_to.source} @ {opp.sell_to.price}",
            f"",
            f"Spread:    {opp.spread_bps:.2f} bps ({float(opp.spread_bps)/100:.2f}%)",
            f"Size:      {opp.recommended_size} {opp.symbol.split('/')[0]}",
            f"Profit:    ${opp.estimated_profit:.2f}",
            f"",
            f"Confidence: {opp.confidence.upper()}",
        ]

        if opp.risk_factors:
            lines.append(f"")
            lines.append(f"⚠️  Risk Factors:")
            for risk in opp.risk_factors:
                lines.append(f"   - {risk}")

        lines.append("=" * 60)

        return "\n".join(lines)


# Example usage
if __name__ == "__main__":
    # Example quotes
    quotes = [
        PriceQuote(
            source="Uniswap V3",
            symbol="ETH/USDC",
            price=Decimal("3000.50"),
            liquidity=Decimal("5000000"),
            gas_cost_wei=int(0.015 * 10**18),
        ),
        PriceQuote(
            source="SushiSwap",
            symbol="ETH/USDC",
            price=Decimal("3030.75"),
            liquidity=Decimal("2000000"),
            gas_cost_wei=int(0.012 * 10**18),
        ),
        PriceQuote(
            source="OANDA",
            symbol="ETH/USDC",
            price=Decimal("3025.00"),
            liquidity=None,  # CEX liquidity
        ),
    ]

    comparator = PriceComparator()
    opportunity = comparator.analyze_opportunity(quotes, max_size=Decimal("50"))

    if opportunity:
        print(comparator.format_opportunity(opportunity))
    else:
        print("No opportunity found")
