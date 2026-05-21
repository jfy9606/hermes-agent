"""
Base classes for Web Model clients
"""

import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WebModelAuth:
    """Authentication credentials for web models."""
    session_key: str = ""
    cookie: str = ""
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    organization_id: Optional[str] = None
    device_id: Optional[str] = None

    def to_dict(self) -> Dict[str, str]:
        return {
            "sessionKey": self.session_key,
            "cookie": self.cookie,
            "userAgent": self.user_agent,
            "organizationId": self.organization_id or "",
            "deviceId": self.device_id or "",
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "WebModelAuth":
        return cls(
            session_key=data.get("sessionKey", ""),
            cookie=data.get("cookie", ""),
            user_agent=data.get("userAgent", "Mozilla/5.0"),
            organization_id=data.get("organizationId"),
            device_id=data.get("deviceId"),
        )


@dataclass
class StreamChunk:
    """A chunk from the stream response."""
    content: str = ""
    is_thinking: bool = False
    is_tool_call: bool = False
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    done: bool = False
    error: Optional[str] = None


class WebModelClient(ABC):
    """Abstract base class for web model clients."""

    BASE_URL: str = ""
    DEFAULT_MODEL: str = ""
    PROVIDER_ID: str = ""

    def __init__(self, auth: WebModelAuth):
        self.auth = auth
        self._device_id = auth.device_id or str(uuid.uuid4())
        self._organization_id = auth.organization_id

    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for requests."""
        return {
            "Content-Type": "application/json",
            "Cookie": self.auth.cookie or f"sessionKey={self.auth.session_key}",
            "User-Agent": self.auth.user_agent,
            "Accept": "text/event-stream",
        }

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the client (e.g., discover organization ID)."""
        ...

    @abstractmethod
    async def chat_completions(
        self,
        message: str,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """
        Send a chat completion request and yield stream chunks.

        Args:
            message: The user message
            **kwargs: Additional parameters (model, conversation_id, signal, etc.)
        """
        ...

    async def health_check(self) -> bool:
        """Check if the client is properly authenticated."""
        try:
            await self.initialize()
            return True
        except Exception as e:
            logger.warning(f"[{self.PROVIDER_ID}] Health check failed: {e}")
            return False
