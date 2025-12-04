#!/usr/bin/env python3
"""Environment configuration checker for arbitrage system.

Checks that all required environment variables are set and provides
instructions for missing ones.
"""

import os
import sys


def check_env() -> dict[str, bool]:
    """Check environment variables and return status."""
    checks = {
        # Required
        "ETH_RPC_URL": bool(os.getenv("ETH_RPC_URL")),
        "POLYGON_RPC_URL": bool(os.getenv("POLYGON_RPC_URL") or os.getenv("POLYGON_RPC")),

        # Recommended
        "ONEINCH_API_KEY": bool(os.getenv("ONEINCH_API_KEY") or os.getenv("ONEINCH_TOKEN")),
        "ETHERSCAN_API_KEY": bool(os.getenv("ETHERSCAN_API_KEY")),
        "POLYGONSCAN_API_KEY": bool(os.getenv("POLYGONSCAN_API_KEY")),

        # Optional
        "BLOCKNATIVE_API_KEY": bool(os.getenv("BLOCKNATIVE_API_KEY")),
        "ALPACA_API_KEY": bool(os.getenv("ALPACA_API_KEY")),
        "ALPACA_API_SECRET": bool(os.getenv("ALPACA_API_SECRET")),
    }
    return checks


def print_report() -> None:
    """Print configuration report."""
    checks = check_env()

    print("\n" + "=" * 70)
    print("ENVIRONMENT CONFIGURATION CHECK".center(70))
    print("=" * 70 + "\n")

    # Required
    print("🔴 REQUIRED (system won't work without these)")
    print("-" * 70)
    required = ["ETH_RPC_URL", "POLYGON_RPC_URL"]
    for key in required:
        status = "✅" if checks[key] else "❌"
        print(f"{status} {key}")
        if not checks[key]:
            print(f"   ⚠️  Set this in your .env file or export it")
    print()

    # Recommended
    print("🟡 RECOMMENDED (features will be degraded without these)")
    print("-" * 70)
    recommended = ["ONEINCH_API_KEY", "ETHERSCAN_API_KEY", "POLYGONSCAN_API_KEY"]
    for key in recommended:
        status = "✅" if checks[key] else "⚠️"
        print(f"{status} {key}")
        if not checks[key]:
            if key == "ONEINCH_API_KEY":
                print("   💡 Needed for Polygon arbitrage quotes")
                print("   📝 Get one at: https://portal.1inch.dev/")
            elif key == "ETHERSCAN_API_KEY":
                print("   💡 Improves Ethereum gas price accuracy")
                print("   📝 Get one at: https://etherscan.io/apis")
            elif key == "POLYGONSCAN_API_KEY":
                print("   💡 Improves Polygon gas price accuracy")
                print("   📝 Get one at: https://polygonscan.com/apis")
    print()

    # Optional
    print("🟢 OPTIONAL (nice to have, not critical)")
    print("-" * 70)
    optional = ["BLOCKNATIVE_API_KEY", "ALPACA_API_KEY", "ALPACA_API_SECRET"]
    for key in optional:
        status = "✅" if checks[key] else "⚪"
        print(f"{status} {key}")
    print()

    # Summary
    required_count = sum(1 for k in required if checks[k])
    recommended_count = sum(1 for k in recommended if checks[k])

    print("📊 SUMMARY")
    print("-" * 70)
    print(f"Required:    {required_count}/{len(required)}")
    print(f"Recommended: {recommended_count}/{len(recommended)}")

    if required_count < len(required):
        print("\n❌ System cannot start - missing required variables")
        print("   Please set the variables above and try again.")
        return False
    elif recommended_count < len(recommended):
        print("\n⚠️  System can start but some features will be limited")
        print("   Consider setting the recommended variables for full functionality.")
        return True
    else:
        print("\n✅ All recommended variables are set!")
        print("   System is ready to run.")
        return True

    print("\n" + "=" * 70 + "\n")


def generate_template() -> None:
    """Generate a .env template file."""
    template = """# Arbitrage System Environment Configuration
# Copy this file to .env and fill in your values

# ============================================================================
# REQUIRED - System won't work without these
# ============================================================================

# Ethereum RPC (Alchemy, Infura, or your own node)
ETH_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY_HERE

# Polygon RPC
POLYGON_RPC_URL=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY_HERE

# ============================================================================
# RECOMMENDED - For full functionality
# ============================================================================

# 1inch API Key (for Polygon quotes)
# Get one at: https://portal.1inch.dev/
ONEINCH_API_KEY=your_1inch_key_here

# Etherscan API Key (for accurate Ethereum gas prices)
# Get one at: https://etherscan.io/apis
ETHERSCAN_API_KEY=your_etherscan_key_here

# Polygonscan API Key (for accurate Polygon gas prices)
# Get one at: https://polygonscan.com/apis
POLYGONSCAN_API_KEY=your_polygonscan_key_here

# ============================================================================
# OPTIONAL - For additional features
# ============================================================================

# Blocknative API Key (premium gas price oracle)
# Get one at: https://www.blocknative.com/
# BLOCKNATIVE_API_KEY=your_blocknative_key_here

# Alpaca API (for CEX trading)
# Get one at: https://alpaca.markets/
# ALPACA_API_KEY=your_alpaca_key_here
# ALPACA_API_SECRET=your_alpaca_secret_here

# ============================================================================
# WALLET CONFIGURATION
# ============================================================================

# Your wallet private key (NEVER commit this to git!)
# PRIVATE_KEY=your_private_key_here

# Account address (checksummed)
# ACCOUNT_ADDRESS=0xYourAddressHere
"""

    output_file = ".env.template"
    with open(output_file, "w") as f:
        f.write(template)

    print(f"\n✅ Template generated: {output_file}")
    print("   Copy it to .env and fill in your values:")
    print(f"   cp {output_file} .env")
    print(f"   nano .env  # or your favorite editor\n")


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Check environment configuration")
    parser.add_argument(
        "--generate-template",
        action="store_true",
        help="Generate a .env template file",
    )

    args = parser.parse_args()

    if args.generate_template:
        generate_template()
        return

    success = print_report()

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
