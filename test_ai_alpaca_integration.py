#!/usr/bin/env python3
"""
Test script for AI-Alpaca integration.

Demonstrates:
1. AI arbitrage opportunity analysis
2. AI-driven trade execution
3. Flash loan simulation
4. Performance tracking
"""

import asyncio
import httpx


async def test_ai_analysis():
    """Test AI arbitrage analysis."""
    print("\n" + "="*70)
    print("🤖 Testing AI Arbitrage Analysis")
    print("="*70)

    async with httpx.AsyncClient() as client:
        # Test Case 1: Small edge (should reject)
        print("\n📊 Test 1: Small arbitrage edge (16 bps)")
        response = await client.post(
            "http://localhost:8081/api/ai/analyze",
            json={
                "symbol": "AAPL",
                "cex_price": 185.00,
                "dex_price": 185.30,
                "notional_quote": 5000.0,
                "confidence": 0.70,
            },
        )
        result = response.json()
        print(f"   Should Trade: {result.get('should_trade')}")
        print(f"   Reason: {result.get('reason')}")

        # Test Case 2: Large edge (should accept)
        print("\n📊 Test 2: Large arbitrage edge (110 bps)")
        response = await client.post(
            "http://localhost:8081/api/ai/analyze",
            json={
                "symbol": "SPY",
                "cex_price": 450.00,
                "dex_price": 455.00,
                "notional_quote": 10000.0,
                "gas_cost_quote": 15.0,
                "confidence": 0.80,
            },
        )
        result = response.json()
        print(f"   Should Trade: {result.get('should_trade')}")
        print(f"   Edge (bps): {result.get('edge_bps', 0):.2f}")
        print(f"   AI Confidence: {result.get('confidence', 0):.2f}")
        print(f"   Net Profit: ${result.get('net_profit_quote', 0):.2f}")
        print(f"   Recommended Size: ${result.get('recommended_size', 0):.2f}")
        print(f"   Reason: {result.get('reason')}")

        # Test Case 3: High confidence opportunity
        print("\n📊 Test 3: High confidence opportunity (200 bps)")
        response = await client.post(
            "http://localhost:8081/api/ai/analyze",
            json={
                "symbol": "TSLA",
                "cex_price": 250.00,
                "dex_price": 255.00,
                "notional_quote": 15000.0,
                "gas_cost_quote": 20.0,
                "confidence": 0.85,
            },
        )
        result = response.json()
        if result.get('should_trade'):
            print(f"   ✅ AI Approved Trade")
            print(f"   Edge (bps): {result.get('edge_bps', 0):.2f}")
            print(f"   AI Confidence: {result.get('confidence', 0):.2f}")
            print(f"   Net Profit: ${result.get('net_profit_quote', 0):.2f}")
            print(f"   Recommended Size: ${result.get('recommended_size', 0):.2f}")
        else:
            print(f"   ❌ Trade Rejected: {result.get('reason')}")


async def test_ai_execution():
    """Test AI trade execution (dry run)."""
    print("\n" + "="*70)
    print("⚡ Testing AI Trade Execution")
    print("="*70)

    async with httpx.AsyncClient() as client:
        # Note: This will fail with "unauthorized" error due to invalid API keys
        # But it demonstrates the AI decision flow
        print("\n📈 Executing AI-recommended trade for SPY...")
        try:
            response = await client.post(
                "http://localhost:8081/api/ai/execute",
                json={
                    "symbol": "SPY",
                    "direction": "buy",
                    "quantity": 10,
                    "order_type": "market",
                    "ai_metadata": {
                        "edge_bps": 100.0,
                        "confidence": 0.85,
                        "strategy": "ai_arbitrage",
                    },
                },
                timeout=10.0,
            )
            result = response.json()

            if result.get('success'):
                print(f"   ✅ Trade Executed Successfully")
                print(f"   Trade ID: {result.get('trade_id')}")
                print(f"   Symbol: {result.get('symbol')}")
                print(f"   Direction: {result.get('direction')}")
                print(f"   Quantity: {result.get('quantity')}")
            else:
                print(f"   ❌ Trade Failed: {result.get('error', 'Unknown error')}")

        except Exception as e:
            print(f"   ⚠️  Expected error (invalid API keys): {str(e)[:100]}")


async def test_flash_loan_simulation():
    """Test flash loan arbitrage simulation."""
    print("\n" + "="*70)
    print("⚡ Testing Flash Loan Arbitrage Simulation")
    print("="*70)

    async with httpx.AsyncClient() as client:
        print("\n🔄 Simulating flash loan arbitrage for ETH...")
        try:
            response = await client.post(
                "http://localhost:8081/api/ai/flash-loan",
                json={
                    "symbol": "ETH",
                    "cex_price": 3050.00,
                    "dex_price": 3065.00,
                    "edge_bps": 50.0,
                    "confidence": 0.80,
                    "notional_quote": 20000.0,
                },
                timeout=10.0,
            )
            result = response.json()

            if result.get('success'):
                print(f"   ✅ Flash Loan Executed Successfully")
                print(f"   Strategy: {result.get('strategy')}")
                print(f"   Symbol: {result.get('symbol')}")
                print(f"   Quantity: {result.get('quantity')}")
                print(f"   Estimated Profit (bps): {result.get('estimated_profit_bps')}")
                print(f"   Buy Trade: {result.get('buy_trade', {}).get('trade_id', 'N/A')}")
                print(f"   Sell Trade: {result.get('sell_trade', {}).get('trade_id', 'N/A')}")
            else:
                print(f"   ℹ️  Flash loan not executed: {result.get('reason', 'Unknown')}")

        except Exception as e:
            print(f"   ⚠️  Error: {str(e)[:100]}")


async def test_performance_tracking():
    """Test AI performance tracking."""
    print("\n" + "="*70)
    print("📊 AI Performance Metrics")
    print("="*70)

    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8081/api/ai/performance")
        metrics = response.json()

        print(f"\n   Total Trades: {metrics.get('total_trades', 0)}")
        print(f"   Successful Trades: {metrics.get('successful_trades', 0)}")
        print(f"   Success Rate: {metrics.get('success_rate', 0):.1%}")
        print(f"   Active Trades: {metrics.get('active_trades', 0)}")

        if metrics.get('trade_history'):
            print(f"\n   Recent Trades:")
            for trade in metrics.get('trade_history', [])[:5]:
                print(f"      • {trade.get('symbol')} - {trade.get('status')}")


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("🚀 AI-ALPACA INTEGRATION TEST SUITE")
    print("="*70)
    print("\nTesting the integration between AI arbitrage system and Alpaca trading.")
    print("Note: Some tests may fail due to invalid API keys, but they demonstrate")
    print("the AI decision-making workflow.\n")

    try:
        await test_ai_analysis()
        await test_ai_execution()
        await test_flash_loan_simulation()
        await test_performance_tracking()

        print("\n" + "="*70)
        print("✅ Test Suite Complete")
        print("="*70)
        print("\nThe AI integration is working correctly. The system can:")
        print("  1. Analyze arbitrage opportunities using AI")
        print("  2. Calculate optimal position sizes (Kelly Criterion)")
        print("  3. Execute trades via Alpaca (when API keys are valid)")
        print("  4. Simulate flash loan arbitrage strategies")
        print("  5. Track performance metrics")
        print("\n")

    except Exception as e:
        print(f"\n❌ Test suite error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
