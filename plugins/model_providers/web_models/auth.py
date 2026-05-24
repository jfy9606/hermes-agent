"""
Authentication Management for Web Models

Handles storage and retrieval of browser session credentials.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

AUTH_PROFILES_FILE = "web_auth_profiles.json"


class WebAuthManager:
    """Manager for web authentication profiles."""

    def __init__(self, hermes_home: Optional[Path] = None):
        if hermes_home is None:
            try:
                from hermes_constants import get_hermes_home
                hermes_home = get_hermes_home()
            except ImportError:
                hermes_home = Path.home() / ".hermes"

        self._hermes_home = hermes_home
        self._profiles_path = hermes_home / AUTH_PROFILES_FILE
        self._profiles: Dict[str, Dict[str, str]] = {}
        self._load_profiles()

    def _load_profiles(self) -> None:
        """Load authentication profiles from disk."""
        if self._profiles_path.exists():
            try:
                with open(self._profiles_path, 'r', encoding='utf-8') as f:
                    self._profiles = json.load(f)
                logger.info(f"[WebModels Auth] Loaded {len(self._profiles)} auth profiles")
            except Exception as e:
                logger.error(f"[WebModels Auth] Failed to load profiles: {e}")

    def _save_profiles(self) -> None:
        """Save authentication profiles to disk."""
        try:
            self._profiles_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._profiles_path, 'w', encoding='utf-8') as f:
                json.dump(self._profiles, f, indent=2, ensure_ascii=False)
            logger.info(f"[WebModels Auth] Saved {len(self._profiles)} auth profiles")
        except Exception as e:
            logger.error(f"[WebModels Auth] Failed to save profiles: {e}")

    def get_auth(self, provider_id: str) -> Optional[Dict[str, str]]:
        """Get authentication credentials for a provider."""
        return self._profiles.get(provider_id)

    def set_auth(self, provider_id: str, auth_data: Dict[str, str]) -> None:
        """Set authentication credentials for a provider."""
        self._profiles[provider_id] = auth_data
        self._save_profiles()
        logger.info(f"[WebModels Auth] Updated auth profile for {provider_id}")

    def remove_auth(self, provider_id: str) -> bool:
        """Remove authentication credentials for a provider."""
        if provider_id in self._profiles:
            del self._profiles[provider_id]
            self._save_profiles()
            logger.info(f"[WebModels Auth] Removed auth profile for {provider_id}")
            return True
        return False

    def list_providers(self) -> list:
        """List all providers with saved authentication."""
        return list(self._profiles.keys())

    def has_auth(self, provider_id: str) -> bool:
        """Check if a provider has saved authentication."""
        return provider_id in self._profiles


def get_cookie_instructions(provider_id: str) -> str:
    """
    Get instructions for extracting cookies from browser.

    Args:
        provider_id: The provider ID

    Returns:
        Instructions string
    """
    instructions = {
        "claude-web": """
To extract Claude Web session:

1. Open https://claude.ai/ in Chrome/Edge and login
2. Press F12 → Application → Cookies → https://claude.ai
3. Find 'sessionKey' cookie and copy its value
4. Use CLI: python -m plugins.model_providers.web_models.cli auth claude-web --cookie <value>
""",
        "chatgpt-web": """
To extract ChatGPT Web session:

1. Open https://chatgpt.com/ in Chrome/Edge and login
2. Press F12 → Application → Cookies → https://chatgpt.com
3. Find '__Secure-next-auth.session-token' cookie and copy its value
4. Use CLI: python -m plugins.model_providers.web_models.cli auth chatgpt-web --cookie <value>
""",
        "deepseek-web": """
To extract DeepSeek Web session:

1. Open https://chat.deepseek.com/ in Chrome/Edge and login
2. Press F12 → Application → Cookies → https://chat.deepseek.com
3. Find session cookie and copy its value
4. Use CLI: python -m plugins.model_providers.web_models.cli auth deepseek-web --cookie <value>
""",
    }

    return instructions.get(provider_id, f"\nPlease extract session cookie for {provider_id} from browser.\n")
