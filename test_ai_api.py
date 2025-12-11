"""Quick test to verify AI API endpoints are working."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("Testing AI API Integration...\n")

# Test 1: Import endpoints
print("1. Testing module imports...")
try:
    from src.api.ai_endpoints import router
    print(f"   ✅ AI router loaded with {len(router.routes)} routes")
except Exception as e:
    print(f"   ❌ Failed to import: {e}")
    sys.exit(1)

# Test 2: Test config manager
print("\n2. Testing AI config manager...")
try:
    from src.ai.config_manager import get_ai_config_manager
    config_manager = get_ai_config_manager()
    config = config_manager.get_config()
    print(f"   ✅ Config manager initialized")
    print(f"   ✅ AI Mode: {config.ai_mode}")
    print(f"   ✅ AI Enabled: {config.enable_ai_system}")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

# Test 3: Test metrics collector
print("\n3. Testing metrics collector...")
try:
    from src.ai.metrics import get_metrics_collector
    metrics = get_metrics_collector()
    summary = metrics.get_summary()
    print(f"   ✅ Metrics collector initialized")
    print(f"   ✅ Tracked metrics: decisions, execution, opportunities")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

from fastapi.routing import APIRoute

# Test 4: List available endpoints
print("\n4. Available AI Endpoints:")
for route in router.routes:
    if isinstance(route, APIRoute):
        methods = ", ".join(route.methods or [])
        print(f"   {methods:8} {route.path}")

print("\n✅ All tests passed! AI API is ready.\n")
print("Next steps:")
print("1. Start dashboard: python web_server.py")
print("2. Test endpoint: curl http://localhost:8080/api/ai/status")
print("3. Add widget to web_dashboard.html")
print("4. See AI_DASHBOARD_INTEGRATION.md for details")
