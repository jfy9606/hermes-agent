"""
Claude Web Client Implementation
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional

try:
    import httpx
except ImportError:
    httpx = None

from ..base import WebModelAuth, StreamChunk, WebModelClient

logger = logging.getLogger(__name__)


class ClaudeWebClient(WebModelClient):
    """Client for Claude Web (claude.ai)."""

    BASE_URL = "https://claude.ai/api"
    DEFAULT_MODEL = "claude-sonnet-4-6"
    PROVIDER_ID = "claude-web"

    def __init__(self, auth: WebModelAuth):
        super().__init__(auth)
        if not self.auth.cookie and not self.auth.session_key:
            raise ValueError("Either cookie or session_key must be provided")

    async def _get_headers(self) -> Dict[str, str]:
        headers = self._get_default_headers()
        headers.update({
            "Referer": "https://claude.ai/",
            "Origin": "https://claude.ai",
            "anthropic-client-platform": "web_claude_ai",
            "anthropic-device-id": str(self._device_id),
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })
        return headers

    async def initialize(self) -> None:
        """Initialize client and discover organization ID."""
        if self._organization_id or not httpx:
            return

        try:
            headers = await self._get_headers()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/organizations",
                    headers=headers,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    orgs = response.json()
                    if orgs and len(orgs) > 0 and orgs[0].get("uuid"):
                        self._organization_id = orgs[0]["uuid"]
                        logger.info(f"[Claude Web] Discovered organization ID: {self._organization_id}")
                else:
                    logger.warning(f"[Claude Web] Failed to fetch organizations: {response.status_code}")
        except Exception as e:
            logger.warning(f"[Claude Web] Failed to discover organization: {e}")

    async def create_conversation(self) -> str:
        """Create a new conversation and return UUID."""
        if not httpx:
            raise ImportError("httpx is required for ClaudeWebClient")

        headers = await self._get_headers()
        url = (
            f"{self.BASE_URL}/organizations/{self._organization_id}/chat_conversations"
            if self._organization_id
            else f"{self.BASE_URL}/chat_conversations"
        )

        payload = {
            "name": f"Conversation {datetime.now(timezone.utc).isoformat()}",
            "uuid": str(uuid.uuid4()),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)

            if response.status_code != 200:
                raise Exception(f"Failed to create conversation: {response.status_code}")

            data = response.json()
            return data.get("uuid", "")

    async def chat_completions(
        self,
        message: str,
        model: Optional[str] = None,
        conversation_id: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """Send a chat completion request to Claude Web."""
        if not httpx:
            yield StreamChunk(error="httpx is required", done=True)
            return

        if not conversation_id:
            try:
                conversation_id = await self.create_conversation()
            except Exception as e:
                yield StreamChunk(error=f"Failed to create conversation: {e}", done=True)
                return

        model = model or self.DEFAULT_MODEL
        headers = await self._get_headers()

        url = (
            f"{self.BASE_URL}/organizations/{self._organization_id}/chat_conversations/{conversation_id}/completion"
            if self._organization_id
            else f"{self.BASE_URL}/chat_conversations/{conversation_id}/completion"
        )

        timezone_str = datetime.now(timezone.utc).astimezone().tzname() or "UTC"

        payload = {
            "prompt": message,
            "timezone": timezone_str,
            "attachments": [],
            "files": [],
            "model": model,
        }

        signal = kwargs.get("signal")

        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                    timeout=120.0,
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread().decode()
                        yield StreamChunk(content=f"Error: HTTP {response.status_code}", error=error_text, done=True)
                        return

                    async for line in response.aiter_lines():
                        if signal and getattr(signal, 'cancelled', False):
                            break

                        if not line.strip():
                            continue

                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                yield StreamChunk(done=True)
                                break

                            try:
                                data = json.loads(data_str)
                                if "completion" in data:
                                    yield StreamChunk(content=data["completion"])
                                elif "message_stop" in data or "stop_reason" in data:
                                    yield StreamChunk(done=True)
                            except json.JSONDecodeError:
                                continue

            except Exception as e:
                logger.error(f"[Claude Web] Error during stream: {e}")
                yield StreamChunk(error=str(e), done=True)
