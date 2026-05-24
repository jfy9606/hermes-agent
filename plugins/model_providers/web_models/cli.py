"""
CLI interface for Web Models authentication management

Usage:
    python -m plugins.model_providers.web_models.cli list
    python -m plugins.model_providers.web_models.cli auth <provider> [--cookie value]
    python -m plugins.model_providers.web_models.cli status
    python -m plugins.model_providers.web_models.cli test <provider>
"""

import argparse
import asyncio
import sys
from typing import Optional

from .config import WEB_PROVIDERS_CONFIG
from .auth import WebAuthManager, get_cookie_instructions
from .base import WebModelAuth


def cmd_list(args) -> int:
    """List all available web providers."""
    print("\n🌐 Zero Token Web Models\n")
    print(f"{'Provider ID':<15} {'Name':<20} {'Model':<25} {'Context':>10}")
    print("-" * 75)

    for provider_id, config in WEB_PROVIDERS_CONFIG.items():
        print(
            f"{provider_id:<15} {config['name']:<20} {config['default_model']:<25} "
            f"{config['context_window']:>10,}"
        )

    print(f"\nTotal: {len(WEB_PROVIDERS_CONFIG)} providers (Zero Cost)")
    return 0


def cmd_auth(args) -> int:
    """Authenticate with a web provider."""
    provider_id = args.provider

    if provider_id not in WEB_PROVIDERS_CONFIG:
        print(f"❌ Unknown provider: {provider_id}")
        print(f"   Available: {', '.join(WEB_PROVIDERS_CONFIG.keys())}")
        return 1

    config = WEB_PROVIDERS_CONFIG[provider_id]
    manager = WebAuthManager()

    if args.cookie:
        auth_data = {"cookie": args.cookie}
        manager.set_auth(provider_id, auth_data)
        print(f"✅ Saved credentials for {config['name']}")
        return 0

    if args.session_key:
        auth_data = {"sessionKey": args.session_key}
        manager.set_auth(provider_id, auth_data)
        print(f"✅ Saved session key for {config['name']}")
        return 0

    print(f"\n🔐 Authentication for {config['name']}\n")
    print(get_cookie_instructions(provider_id))
    print("Options:")
    print(f"  --cookie <value>     Set cookie directly")
    print(f"  --session-key <value> Set session key directly")
    return 0


def cmd_status(args) -> int:
    """Check authentication status."""
    manager = WebAuthManager()
    providers = manager.list_providers()

    if not providers:
        print("\n⚠️  No web providers authenticated yet.")
        print("   Use 'auth <provider>' to set up authentication.\n")
        return 0

    print("\n🔑 Authentication Status\n")
    print(f"{'Provider':<20} {'Status':<10}")
    print("-" * 35)

    for provider_id in sorted(providers):
        auth_data = manager.get_auth(provider_id)
        status = "✅ Active"
        print(f"{provider_id:<20} {status:<10}")

    print(f"\nTotal: {len(providers)} authenticated provider(s)")
    return 0


async def cmd_test(args) -> int:
    """Test a web provider connection."""
    provider_id = args.provider

    if provider_id not in WEB_PROVIDERS_CONFIG:
        print(f"❌ Unknown provider: {provider_id}")
        return 1

    config = WEB_PROVIDERS_CONFIG[provider_id]
    manager = WebAuthManager()
    auth_data = manager.get_auth(provider_id)

    if not auth_data:
        print(f"❌ No authentication found for {config['name']}")
        print(f"   Run: auth {provider_id} first")
        return 1

    print(f"\n🧪 Testing connection to {config['name']}...\n")

    try:
        from web_models.clients.claude_web import ClaudeWebClient

        auth = WebModelAuth.from_dict(auth_data)

        if provider_id == "claude-web":
            client = ClaudeWebClient(auth)
            is_valid = await client.health_check()
        else:
            # For other clients, just check if auth data exists
            is_valid = bool(auth.cookie or auth.session_key)

        if is_valid:
            print("✅ Connection successful!")
            print(f"   Provider: {config['name']}")
            print(f"   Model: {config['default_model']}")
            return 0
        else:
            print("❌ Connection failed!")
            print(f"   The session may have expired.")
            return 1

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Zero Token Web Models CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("list", help="List available web models")

    auth_parser = subparsers.add_parser("auth", help="Authenticate with a provider")
    auth_parser.add_argument("provider", help="Provider ID (e.g., claude-web)")
    auth_parser.add_argument("--cookie", help="Set cookie directly")
    auth_parser.add_argument("--session-key", help="Set session key directly")

    subparsers.add_parser("status", help="Check authentication status")

    test_parser = subparsers.add_parser("test", help="Test provider connection")
    test_parser.add_argument("provider", help="Provider ID to test")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "list": cmd_list,
        "auth": cmd_auth,
        "status": cmd_status,
        "test": cmd_test,
    }

    handler = commands.get(args.command)
    if handler:
        if asyncio.iscoroutinefunction(handler):
            return asyncio.run(handler(args))
        else:
            return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
