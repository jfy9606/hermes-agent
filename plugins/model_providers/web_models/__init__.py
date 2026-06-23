"""
Zero Token Web Models Provider Plugin

This plugin hosts browser-session-backed model providers.

Only providers with a concrete client implementation are registered into the
main provider registry so unfinished entries do not leak into the global model
picker/runtime path.
"""

import logging
from typing import Dict, List

try:
    from providers import register_provider
    from providers.base import ProviderProfile
    PROVIDERS_SYSTEM_AVAILABLE = True
except ImportError:
    PROVIDERS_SYSTEM_AVAILABLE = False

from .config import WEB_PROVIDERS_CONFIG
from .auth import WebAuthManager

logger = logging.getLogger(__name__)


def _implemented_provider_configs() -> Dict[str, Dict]:
    """Return only providers that declare a concrete client implementation."""
    return {
        provider_id: config
        for provider_id, config in WEB_PROVIDERS_CONFIG.items()
        if config.get("client_module") and config.get("client_class")
    }


def register_web_model_providers() -> None:
    """Register all Zero Token web model providers with Hermes."""
    if not PROVIDERS_SYSTEM_AVAILABLE:
        logger.warning("[WebModels] Provider registration system not available")
        return

    for provider_id, config in _implemented_provider_configs().items():
        try:
            aliases = [f"{config['name'].lower().replace(' ', '-')}-web"]
            if config.get("alias"):
                aliases.append(config["alias"])
            profile = ProviderProfile(
                name=provider_id,
                aliases=tuple(aliases),
                env_vars=(),
                display_name=config["name"],
                description=f"{config['description']} (Zero Token - no API key required)",
                signup_url=config.get("auth_url", ""),
                fallback_models=(config["default_model"],),
                base_url=config["base_url"],
                auth_type="browser_session",
            )

            register_provider(profile)
            logger.info(f"[WebModels] Registered provider: {provider_id}")

        except Exception as e:
            logger.error(f"[WebModels] Failed to register {provider_id}: {e}")


def get_auth_manager() -> WebAuthManager:
    """Get the authentication manager instance."""
    return WebAuthManager()


def list_available_providers() -> List[Dict]:
    """List all available web model providers with their configurations."""
    return [
        {
            "id": provider_id,
            **config,
        }
        for provider_id, config in _implemented_provider_configs().items()
    ]


def is_provider_authenticated(provider_id: str) -> bool:
    """Check if a provider has valid authentication."""
    manager = get_auth_manager()
    return manager.has_auth(provider_id)


# Auto-register on import
if __name__ != "__main__":
    try:
        register_web_model_providers()
    except Exception as e:
        logger.error(f"[WebModels] Auto-registration failed: {e}")
