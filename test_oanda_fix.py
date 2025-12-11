#!/usr/bin/env python3
"""Test script to validate OANDA configuration fix."""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from pydantic import ValidationError
from src.brokers.oanda_config import OandaConfig
from src.brokers.oanda_adapter import OandaAdapter

print("=" * 70)
print("OANDA Configuration Fix - Test Suite")
print("=" * 70)

# Test 1: Load config without errors
print("\n[Test 1] Loading OandaConfig from environment...")
try:
    config = OandaConfig.from_env()
    print("✓ Config loaded successfully")
except ValidationError as e:
    print(f"✗ Validation error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    sys.exit(1)

# Test 2: Check if credentials are configured
print("\n[Test 2] Checking if credentials are configured...")
print(f"  OANDA_API_TOKEN in env: {bool(os.getenv('OANDA_API_TOKEN'))}")
print(f"  OANDA_ACCOUNT_ID in env: {bool(os.getenv('OANDA_ACCOUNT_ID'))}")
print(f"  OANDA_ENVIRONMENT: {os.getenv('OANDA_ENVIRONMENT', 'not set')}")
print(f"  config.is_configured(): {config.is_configured()}")

if config.is_configured():
    print("✓ Credentials are properly configured")
    print(f"  Account ID: {config.oanda_account_id}")
    print(f"  Environment: {config.oanda_environment.value}")
    print(f"  Base URL: {config.get_base_url()}")
else:
    print("✗ Credentials are NOT configured")
    print("  This is expected if OANDA_API_TOKEN or OANDA_ACCOUNT_ID are not set")

# Test 3: Try to create adapter (should succeed only if configured)
print("\n[Test 3] Creating OandaAdapter...")
try:
    adapter = OandaAdapter(config)
    print("✓ Adapter created successfully")
    print(f"  Account ID: {adapter.account_id}")
    print(f"  Base URL: {adapter.base_url}")
except ValueError as e:
    print(f"✗ Expected error (credentials not configured): {e}")
except Exception as e:
    print(f"✗ Unexpected error: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Test with missing credentials
print("\n[Test 4] Testing with missing credentials...")
# Create config with explicit None values (bypassing environment)
# Note: In Pydantic BaseSettings, use lowercase field names in constructor
# Uppercase aliases (OANDA_API_TOKEN) are only for environment variables
try:
    from pydantic import SecretStr

    # Create config without credentials
    config_empty = OandaConfig()
    print(f"  config.is_configured(): {config_empty.is_configured()}")
    if not config_empty.is_configured():
        print("✓ Correctly detected missing credentials")
    else:
        print("✗ Failed to detect missing credentials")

    # Try to create adapter (should fail)
    try:
        adapter_empty = OandaAdapter(config_empty)
        print("✗ Adapter should not have been created without credentials")
    except ValueError as e:
        print(f"✓ Adapter correctly rejected missing credentials")
except Exception as e:
    print(f"✗ Unexpected error in test: {e}")

print("\n" + "=" * 70)
print("All tests completed!")
print("=" * 70)
