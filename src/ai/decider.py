"""Lightweight AI decision scaffold for flash-loan execution.

This module keeps the "brain" off-chain:
1. Receive candidate opportunities (from scanner or an external scorer)
2. Score them with a simple heuristic (drop-in point for ML models)
3. Return a structured decision and (optionally) hand it to the executor

The default scorer is intentionally simple so it is safe to run now, and can
be swapped for an ML/RL model later without touching the rest of the app.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class AIConfig:
    """Runtime knobs for the AI decider."""

    min_profit_eth: float = 0.05
    confidence_threshold: float = 0.6
    max_gas_gwei: float = 120.0
    hop_penalty_quote: float = 5.0  # Optional extra penalty per hop (in quote units)


@dataclass
class AICandidate:
    """A single opportunity proposed for AI review."""

    symbol: str
    edge_bps: float
    notional_quote: float
    gas_cost_quote: float
    flash_fee_quote: float = 0.0
    slippage_quote: float = 0.0
    hop_count: int = 1
    cex_price: float | None = None
    dex_price: float | None = None
    chain: str = "ethereum"
    confidence: float = 0.5  # caller-supplied prior confidence

    def expected_net_quote(self) -> float:
        """Compute a simple expected net PnL in quote terms."""
        gross = self.notional_quote * (self.edge_bps / 10_000)
        costs = self.gas_cost_quote + self.flash_fee_quote + self.slippage_quote
        return gross - costs


@dataclass
class AIDecision:
    """Result of scoring a candidate."""

    symbol: str
    edge_bps: float
    notional_quote: float
    net_quote: float
    confidence: float
    chain: str
    cex_price: float | None = None
    dex_price: float | None = None
    gas_cost_quote: float = 0.0
    flash_fee_quote: float = 0.0
    slippage_quote: float = 0.0
    hop_count: int = 1
    reason: str = "ok"

    def is_profitable(self, min_profit_eth: float, quote_per_eth: float) -> bool:
        """Check if decision clears the profit floor in ETH terms."""
        if quote_per_eth <= 0:
            return False
        net_eth = self.net_quote / quote_per_eth
        return net_eth >= min_profit_eth

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "edge_bps": self.edge_bps,
            "notional_quote": self.notional_quote,
            "net_quote": self.net_quote,
            "confidence": self.confidence,
            "chain": self.chain,
            "cex_price": self.cex_price,
            "dex_price": self.dex_price,
            "gas_cost_quote": self.gas_cost_quote,
            "flash_fee_quote": self.flash_fee_quote,
            "slippage_quote": self.slippage_quote,
            "hop_count": self.hop_count,
            "reason": self.reason,
        }


class AIDecider:
    """Simple scoring wrapper; drop-in replacement for ML/RL later."""

    def __init__(self, config: AIConfig | None = None):
        self.config = config or AIConfig()
        self.last_trace: list[dict] = []
        self.last_decision: AIDecision | None = None

    def pick_best(self, candidates: Iterable[AICandidate]) -> AIDecision | None:
        """Score all candidates and return the best viable decision."""
        best: AIDecision | None = None
        self.last_trace = []
        self.last_decision = None

        for cand in candidates:
            gross_quote = cand.notional_quote * (cand.edge_bps / 10_000)
            costs = cand.gas_cost_quote + cand.flash_fee_quote + cand.slippage_quote
            net_quote = gross_quote - costs
            reason = "ok"

            # Penalize hop count if configured
            if self.config.hop_penalty_quote > 0 and cand.hop_count > 1:
                net_quote -= self.config.hop_penalty_quote * (cand.hop_count - 1)

            if gross_quote <= costs:
                reason = "costs_exceed_gross"
            elif net_quote <= 0:
                reason = "net_negative_after_penalty"

            # Combine caller confidence with edge signal (lightweight heuristic)
            normalized_edge = max(0.0, min(1.0, cand.edge_bps / 100.0))  # 100 bps -> 1.0
            confidence = 0.5 * cand.confidence + 0.5 * normalized_edge

            if reason == "ok":
                if cand.edge_bps <= 0:
                    reason = "non_positive_edge"
                elif confidence < self.config.confidence_threshold:
                    reason = "low_confidence"

            trace_entry = {
                "symbol": cand.symbol,
                "edge_bps": cand.edge_bps,
                "hop_count": cand.hop_count,
                "gas_quote": cand.gas_cost_quote,
                "flash_fee_quote": cand.flash_fee_quote,
                "slippage_quote": cand.slippage_quote,
                "gross_quote": gross_quote,
                "net_quote": net_quote,
                "confidence": confidence,
                "chain": cand.chain,
                "reason": reason,
            }
            self.last_trace.append(trace_entry)

            if reason != "ok":
                continue

            decision = AIDecision(
                symbol=cand.symbol,
                edge_bps=cand.edge_bps,
                notional_quote=cand.notional_quote,
                net_quote=net_quote,
                confidence=confidence,
                chain=cand.chain,
                cex_price=cand.cex_price,
                dex_price=cand.dex_price,
                gas_cost_quote=cand.gas_cost_quote,
                flash_fee_quote=cand.flash_fee_quote,
                slippage_quote=cand.slippage_quote,
                hop_count=cand.hop_count,
                reason="ok",
            )

            if best is None or decision.net_quote > best.net_quote:
                best = decision

        self.last_decision = best
        return best
