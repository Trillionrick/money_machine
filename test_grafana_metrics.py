#!/usr/bin/env python3
"""Test script to verify Grafana metrics are working correctly.

This script:
1. Checks if the FastAPI application is running
2. Tests the Prometheus metrics endpoint
3. Verifies Prometheus is scraping correctly
4. Tests the Discord webhook (if configured)
5. Checks TimescaleDB connectivity
"""

import asyncio
import os
import sys
from datetime import datetime

import httpx
import structlog

log = structlog.get_logger()


async def check_application_health() -> bool:
    """Check if the FastAPI application is running."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8080/api/ai/health", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                log.info("application_health", status=data.get("status"), **data)
                return True
            else:
                log.error("application_health_check_failed", status_code=response.status_code)
                return False
    except Exception as e:
        log.error("application_not_reachable", error=str(e))
        return False


async def check_prometheus_metrics() -> bool:
    """Check if Prometheus metrics endpoint is working."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://localhost:8080/api/ai/metrics/prometheus", timeout=5.0
            )
            if response.status_code == 200:
                metrics_text = response.text
                lines = metrics_text.split("\n")
                metric_count = len([line for line in lines if line and not line.startswith("#")])

                log.info(
                    "prometheus_metrics_working",
                    total_lines=len(lines),
                    metric_lines=metric_count,
                )

                # Show sample metrics
                print("\n📊 Sample Metrics:")
                for line in lines[:20]:
                    if line and not line.startswith("#"):
                        print(f"  {line}")

                return True
            else:
                log.error("metrics_endpoint_failed", status_code=response.status_code)
                return False
    except Exception as e:
        log.error("metrics_endpoint_not_reachable", error=str(e))
        return False


async def check_prometheus_scraping() -> bool:
    """Check if Prometheus is scraping the metrics."""
    try:
        async with httpx.AsyncClient() as client:
            # Check Prometheus targets
            response = await client.get("http://localhost:9091/api/v1/targets", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                active_targets = data.get("data", {}).get("activeTargets", [])

                trading_app_targets = [
                    t for t in active_targets if "trading_app" in t.get("labels", {}).get("job", "")
                ]

                if trading_app_targets:
                    log.info(
                        "prometheus_scraping_active",
                        targets=len(trading_app_targets),
                    )

                    for target in trading_app_targets:
                        health = target.get("health", "unknown")
                        last_scrape = target.get("lastScrape", "never")
                        print(f"\n📡 Target: {target['labels']['job']}")
                        print(f"  Health: {health}")
                        print(f"  Last Scrape: {last_scrape}")
                        print(f"  Scrape URL: {target['scrapeUrl']}")

                    return True
                else:
                    log.warning("no_trading_app_targets_found")
                    return False
            else:
                log.error("prometheus_api_failed", status_code=response.status_code)
                return False
    except Exception as e:
        log.error("prometheus_not_reachable", error=str(e))
        return False


async def test_discord_webhook() -> bool:
    """Test Discord webhook if configured."""
    discord_url = os.getenv("DISCORD_WEBHOOK_URL")

    if not discord_url:
        log.warning("discord_webhook_not_configured")
        return False

    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "content": f"🧪 **Test Alert from Grafana Metrics Setup**\n\n"
                f"Timestamp: {datetime.utcnow().isoformat()}\n"
                f"System: Money Machine Arbitrage\n"
                f"Status: All systems operational\n\n"
                f"This is a test message to verify webhook integration is working correctly."
            }

            response = await client.post(discord_url, json=payload, timeout=10.0)

            if response.status_code in [200, 204]:
                log.info("discord_webhook_test_successful")
                print("\n✅ Discord webhook test message sent successfully!")
                return True
            else:
                log.error("discord_webhook_test_failed", status_code=response.status_code)
                return False
    except Exception as e:
        log.error("discord_webhook_test_error", error=str(e))
        return False


async def check_timescaledb() -> bool:
    """Check TimescaleDB connectivity and data."""
    try:
        import asyncpg

        conn = await asyncpg.connect(
            host="localhost",
            port=5433,
            user="trading_user",
            password="trading_pass_change_in_production",
            database="trading_db",
        )

        # Check if arbitrage_opportunities table exists
        result = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = 'arbitrage_opportunities'
            """
        )

        if result > 0:
            # Count records
            count = await conn.fetchval("SELECT COUNT(*) FROM arbitrage_opportunities")
            recent = await conn.fetchval(
                "SELECT COUNT(*) FROM arbitrage_opportunities WHERE timestamp > NOW() - INTERVAL '1 hour'"
            )

            log.info(
                "timescaledb_connected",
                total_records=count,
                recent_records=recent,
            )

            print(f"\n💾 TimescaleDB Status:")
            print(f"  Total Records: {count}")
            print(f"  Recent Records (1h): {recent}")

            await conn.close()
            return True
        else:
            log.warning("arbitrage_opportunities_table_not_found")
            await conn.close()
            return False

    except ImportError:
        log.warning("asyncpg_not_installed", hint="Install with: pip install asyncpg")
        return False
    except Exception as e:
        log.error("timescaledb_connection_failed", error=str(e))
        return False


async def check_grafana() -> bool:
    """Check if Grafana is accessible."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:3000/api/health", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                log.info("grafana_accessible", **data)
                print(f"\n📊 Grafana Status: {data.get('database', 'unknown')}")
                return True
            else:
                log.error("grafana_health_check_failed", status_code=response.status_code)
                return False
    except Exception as e:
        log.error("grafana_not_reachable", error=str(e))
        return False


async def main():
    """Run all checks."""
    print("=" * 60)
    print("🔍 Grafana Metrics Setup Verification")
    print("=" * 60)

    checks = {
        "FastAPI Application": check_application_health(),
        "Prometheus Metrics Endpoint": check_prometheus_metrics(),
        "Prometheus Scraping": check_prometheus_scraping(),
        "Grafana": check_grafana(),
        "TimescaleDB": check_timescaledb(),
        "Discord Webhook": test_discord_webhook(),
    }

    results = {}
    for name, coro in checks.items():
        print(f"\n🔄 Checking {name}...")
        results[name] = await coro

    # Summary
    print("\n" + "=" * 60)
    print("📋 Summary")
    print("=" * 60)

    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {name}")

    all_passed = all(results.values())

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All checks passed! Your monitoring stack is ready.")
        print("\n📌 Next Steps:")
        print("  1. Open Grafana: http://localhost:3000")
        print("  2. View Dashboard: Arbitrage Monitoring")
        print("  3. Create Alert Rules: Alerting → Alert rules")
        print("  4. Configure Contact Points: Alerting → Contact points")
    else:
        print("⚠️  Some checks failed. Please review the errors above.")
        print("\n📌 Troubleshooting:")
        print("  1. Ensure Docker containers are running: docker compose ps")
        print("  2. Check application logs: docker compose logs trading_app")
        print("  3. Verify environment variables in .env file")
        print("  4. Review setup guide: GRAFANA_ALERTING_SETUP.md")

    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
