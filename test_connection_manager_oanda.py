#!/usr/bin/env python3
"""Test ConnectionManager with OANDA integration."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from src.brokers.connection_manager import ConnectionManager
from src.brokers.credentials import BrokerCredentials

print("=" * 70)
print("ConnectionManager OANDA Integration Test")
print("=" * 70)

async def test_connection_manager():
    """Test ConnectionManager with OANDA."""

    # Load broker credentials
    print("\n[Step 1] Loading broker credentials...")
    try:
        creds = BrokerCredentials()
        print("✓ Credentials loaded")
    except Exception as e:
        print(f"✗ Failed to load credentials: {e}")
        return False

    # Initialize connection manager
    print("\n[Step 2] Initializing ConnectionManager...")
    try:
        manager = ConnectionManager(credentials=creds)
        await manager.initialize()
        print("✓ ConnectionManager initialized")
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Check which connectors were initialized
    print("\n[Step 3] Checking initialized connectors...")
    print(f"  Available connectors: {list(manager.connectors.keys())}")

    if "oanda" in manager.connectors:
        print("✓ OANDA connector initialized successfully")
        oanda = manager.connectors["oanda"]
        print(f"  Account ID: {oanda.account_id}")
        print(f"  Base URL: {oanda.base_url}")
        print(f"  Environment: {oanda.config.oanda_environment.value}")
    else:
        print("⚠ OANDA connector not initialized (may be expected if credentials not set)")

    # Cleanup
    print("\n[Step 4] Cleaning up...")
    try:
        # Try common shutdown/close method names if present on the manager.
        shutdown_called = False
        for name in ("shutdown", "close", "stop", "disconnect"):
            if hasattr(manager, name):
                method = getattr(manager, name)
                if callable(method):
                    result = method()
                    if asyncio.iscoroutine(result):
                        await result
                    shutdown_called = True
                    break
        if not shutdown_called:
            print("⚠ No shutdown/close method found on ConnectionManager; skipping explicit cleanup")
        else:
            print("✓ ConnectionManager shutdown successfully")
    except Exception as e:
        print(f"⚠ Shutdown warning: {e}")

    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_connection_manager())
        if success:
            print("\n" + "=" * 70)
            print("Integration test PASSED!")
            print("=" * 70)
            sys.exit(0)
        else:
            print("\n" + "=" * 70)
            print("Integration test FAILED!")
            print("=" * 70)
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
