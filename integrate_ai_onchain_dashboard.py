#!/usr/bin/env python3
"""Automatic integration script for AI/ML On-Chain dashboard widget.

This script automatically adds the AI/ML on-chain control widget to your
dashboard and mounts the necessary API endpoints.

Usage:
    python integrate_ai_onchain_dashboard.py
"""

import shutil
from pathlib import Path
import sys


def backup_file(file_path: Path) -> Path:
    """Create a backup of a file."""
    backup_path = file_path.with_suffix(file_path.suffix + '.backup')
    shutil.copy2(file_path, backup_path)
    print(f"✅ Backed up {file_path} to {backup_path}")
    return backup_path


def integrate_dashboard_widget():
    """Integrate the AI/ML on-chain widget into the dashboard HTML."""
    dashboard_path = Path("web_dashboard.html")
    widget_path = Path("web_dashboard_ai_onchain.html")

    if not dashboard_path.exists():
        print(f"❌ Error: {dashboard_path} not found")
        return False

    if not widget_path.exists():
        print(f"❌ Error: {widget_path} not found")
        return False

    # Backup original
    backup_file(dashboard_path)

    # Read files
    with open(dashboard_path, 'r', encoding='utf-8') as f:
        dashboard_content = f.read()

    with open(widget_path, 'r', encoding='utf-8') as f:
        widget_content = f.read()

    # Find the insertion point (after the AI Settings off-chain card)
    # Look for the closing </div> of the AI Settings card
    insertion_marker = '''                </div>

                <div class="settings-card">
                    <h3 style="margin:0 0 12px 0;font-size:14px;color:#10b981;">
                        <span class="emoji">🤖</span> AI Settings (off-chain)'''

    if insertion_marker not in dashboard_content:
        print("❌ Error: Could not find insertion point in dashboard")
        print("   Looking for AI Settings (off-chain) card")
        return False

    # Find where to insert (after the off-chain AI card closes)
    # We want to insert in the same settings-flex div
    off_chain_card_start = dashboard_content.find(insertion_marker)

    # Find the closing </div> of the off-chain AI card
    # We'll search for the closing tag after the off-chain card
    search_start = off_chain_card_start + len(insertion_marker)

    # Look for the pattern that marks the end of the off-chain card
    # This should be after the "Apply Config" button
    apply_config_marker = '''                <div style="margin-top:12px;">
                    <button class="btn-start" style="padding:10px 18px;" onclick="updateConfig()">
                        <span class="emoji">💾</span> Apply Config
                    </button>
            </div>
        </div>'''

    insertion_point = dashboard_content.find(apply_config_marker, search_start)

    if insertion_point == -1:
        print("❌ Error: Could not find exact insertion point")
        print("   Trying alternative method...")

        # Alternative: Insert before the closing of settings-flex
        # Find the end of the settings-flex div
        settings_flex_end = '</div>\n\n                <div style="margin-top:12px;">'
        insertion_point = dashboard_content.find(settings_flex_end, search_start)

        if insertion_point == -1:
            print("❌ Error: Could not find insertion point with alternative method")
            return False

    # Insert the widget content
    # Remove the HTML comment and script/style tags from widget (we'll insert the actual content)
    # Get just the settings-card div from the widget
    widget_start = widget_content.find('<div class="settings-card"')
    widget_end = widget_content.rfind('</div>') + 6

    if widget_start == -1:
        print("❌ Error: Could not extract widget content")
        return False

    # Extract the settings-card div and everything after it
    widget_to_insert = widget_content[widget_start:widget_end]

    # Insert after the "Apply Config" closing div
    insertion_point = insertion_point + len(apply_config_marker)

    new_content = (
        dashboard_content[:insertion_point] +
        '\n\n' +
        widget_to_insert +
        dashboard_content[insertion_point:]
    )

    # Write the modified dashboard
    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"✅ Integrated AI/ML on-chain widget into {dashboard_path}")
    return True


def integrate_api_endpoints():
    """Add API endpoint imports to web_server.py."""
    server_path = Path("web_server.py")

    if not server_path.exists():
        print(f"❌ Error: {server_path} not found")
        return False

    # Backup original
    backup_file(server_path)

    # Read server file
    with open(server_path, 'r', encoding='utf-8') as f:
        server_content = f.read()

    # Check if already integrated
    if 'ai_onchain_endpoints' in server_content:
        print("⚠️  AI on-chain endpoints already integrated in web_server.py")
        return True

    # Find where to insert (after ai_endpoints import)
    ai_endpoints_marker = '''try:
    from src.api.ai_endpoints import router as ai_router
    app.include_router(ai_router)
    log.info("ai_endpoints.mounted")
except Exception as e:
    log.warning("ai_endpoints.mount_failed", error=str(e))'''

    insertion_point = server_content.find(ai_endpoints_marker)

    if insertion_point == -1:
        print("❌ Error: Could not find AI endpoints import in web_server.py")
        return False

    # Prepare the import code to insert
    import_code = '''

# Import and mount AI on-chain endpoints
try:
    from src.api.ai_onchain_endpoints import router as ai_onchain_router, set_ai_runner
    app.include_router(ai_onchain_router)
    log.info("ai_onchain_endpoints.mounted")
except Exception as e:
    log.warning("ai_onchain_endpoints.mount_failed", error=str(e))'''

    # Insert after the ai_endpoints block
    insertion_point = insertion_point + len(ai_endpoints_marker)

    new_content = (
        server_content[:insertion_point] +
        import_code +
        server_content[insertion_point:]
    )

    # Write the modified server file
    with open(server_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"✅ Integrated AI on-chain endpoints into {server_path}")
    return True


def main():
    """Main integration function."""
    print("=" * 70)
    print("AI/ML ON-CHAIN DASHBOARD WIDGET INTEGRATION")
    print("=" * 70)
    print()

    success = True

    # Step 1: Integrate dashboard widget
    print("Step 1: Integrating dashboard widget...")
    if not integrate_dashboard_widget():
        success = False
        print("❌ Failed to integrate dashboard widget")
    else:
        print("✅ Dashboard widget integrated successfully")

    print()

    # Step 2: Integrate API endpoints
    print("Step 2: Integrating API endpoints...")
    if not integrate_api_endpoints():
        success = False
        print("❌ Failed to integrate API endpoints")
    else:
        print("✅ API endpoints integrated successfully")

    print()
    print("=" * 70)

    if success:
        print("✅ INTEGRATION COMPLETE!")
        print()
        print("Next steps:")
        print("1. Review the changes in web_dashboard.html and web_server.py")
        print("2. Start the dashboard: python web_server.py")
        print("3. Open http://localhost:8080 in your browser")
        print("4. Look for the new 'AI/ML On-Chain (Flash Loans)' widget")
        print()
        print("To configure for maximum flash loan profit:")
        print("- Click the '🚀 Aggressive' preset button")
        print("- Adjust Current Capital to match your ETH")
        print("- Set Target Capital to your profit goal")
        print("- Click '💾 Apply AI On-Chain Config'")
        print()
        print("See DASHBOARD_AI_ONCHAIN_INTEGRATION.md for detailed instructions")
    else:
        print("❌ INTEGRATION FAILED")
        print()
        print("Some steps failed. Check the error messages above.")
        print("Your original files have been backed up with .backup extension")
        print()
        print("You can restore them with:")
        print("  mv web_dashboard.html.backup web_dashboard.html")
        print("  mv web_server.py.backup web_server.py")

    print("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
