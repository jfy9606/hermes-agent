"""
OpenAI-compatible adapter for Zero Token Web Models.

Allows the AIAgent to use browser-session-based models (Claude Web, ChatGPT Web, etc.)
as if they were standard OpenAI-compatible providers.
"""

import json
import logging
import uuid
import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, AsyncIterator

logger = logging.getLogger(__name__)

class WebModelAuxiliaryClient:
    """OpenAI-compatible adapter for Zero Token Web Models."""

    def __init__(self, provider_id: str, model: str):
        self.provider_id = provider_id
        self.model = model
        self.api_key = "web-session"
        self.base_url = f"web-model://{provider_id}"
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        """Sync create() - collects all chunks and returns an OpenAI-like response."""
        if kwargs.get("stream"):
            # Return a sync iterator wrapper for the async generator
            return self._sync_stream_iterator(kwargs)
        
        async def _collect():
            content = ""
            finish_reason = None
            async for chunk in self.acreate(**kwargs):
                if chunk.choices[0].delta.content:
                    content += chunk.choices[0].delta.content
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
            return content, finish_reason

        try:
            loop = asyncio.get_running_loop()
            # If we are in an async loop, we can't use run_until_complete.
            # This case shouldn't happen in standard AIAgent sync calls,
            # but can happen in tests.
            import nest_asyncio
            nest_asyncio.apply()
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
        content, finish_reason = loop.run_until_complete(_collect())
        
        # Build response
        tool_calls = self._extract_tool_calls(content)
        message = SimpleNamespace(
            role="assistant",
            content=content,
            tool_calls=tool_calls
        )
        choice = SimpleNamespace(index=0, message=message, finish_reason=finish_reason or "stop")
        return SimpleNamespace(choices=[choice], model=self.model)

    def _sync_stream_iterator(self, kwargs):
        """Wrapper to allow sync iteration over an async generator."""
        gen = self.acreate(**kwargs)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        class SyncIter:
            def __iter__(self):
                return self
            def __next__(self):
                try:
                    return loop.run_until_complete(gen.__anext__())
                except StopAsyncIteration:
                    raise StopIteration
        return SyncIter()

    async def acreate(self, **kwargs) -> AsyncIterator[Any]:
        """Async create() - yields OpenAI-compatible chunks."""
        client = await self._get_client()
        if not client:
            yield self._error_chunk("Authentication missing or provider not supported: " + self.provider_id)
            return

        messages = kwargs.get("messages", [])
        tools = kwargs.get("tools", [])
        
        # Use plugin's tool calling logic
        try:
            tool_calling = self._get_tool_calling_module()
            if tool_calling and tools and tool_calling.should_inject_tool_prompt(self.provider_id):
                prompt = tool_calling.get_tool_prompt(self.provider_id, tools)
                # Clone messages to avoid modifying original
                messages = [dict(m) for m in messages]
                if messages and messages[0]["role"] == "system":
                    messages[0]["content"] = prompt + "\n\n" + messages[0]["content"]
                else:
                    messages.insert(0, {"role": "system", "content": prompt})
        except Exception as e:
            logger.warning(f"WebModels tool_calling injection failed: {e}")

        full_prompt = self._format_messages(messages)
        
        full_content = ""
        try:
            async for chunk in client.chat_completions(full_prompt, model=self.model):
                if chunk.error:
                    yield self._error_chunk(chunk.error)
                    return
                
                if chunk.content:
                    full_content += chunk.content
                
                if chunk.done:
                    # Final chunk: check for tool calls in the full accumulated content
                    tool_calls = self._extract_tool_calls(full_content)
                    yield self._map_chunk(chunk, tool_calls=tool_calls)
                else:
                    yield self._map_chunk(chunk)
        except Exception as e:
            logger.error(f"Error in web model stream: {e}")
            yield self._error_chunk(str(e))

    def _get_tool_calling_module(self):
        """Helper to safely import the tool_calling module from the plugin."""
        try:
            # Try standard import first (works if providers._discover_providers() was called)
            import sys
            module_name = "plugins.model_providers.web_models.tool_calling"
            if module_name in sys.modules:
                return sys.modules[module_name]
            
            import importlib
            return importlib.import_module(module_name)
        except ImportError:
            try:
                # Manual discovery if not yet loaded
                from providers import _discover_providers
                _discover_providers()
                import importlib
                return importlib.import_module("plugins.model_providers.web_models.tool_calling")
            except Exception:
                return None

    async def _get_client(self):
        try:
            # Use dynamic import for WebAuthManager as well
            import sys
            auth_module_name = "plugins.model_providers.web_models.auth"
            if auth_module_name not in sys.modules:
                try:
                    from providers import _discover_providers
                    _discover_providers()
                except Exception:
                    pass
            
            import importlib
            auth_mod = importlib.import_module(auth_module_name)
            base_mod = importlib.import_module("plugins.model_providers.web_models.base")
            
            manager = auth_mod.WebAuthManager()
            auth_data = manager.get_auth(self.provider_id)
            if not auth_data:
                return None
            
            auth = base_mod.WebModelAuth.from_dict(auth_data)
            
            # Dynamic client loading
            if self.provider_id == "claude-web":
                client_mod = importlib.import_module("plugins.model_providers.web_models.clients.claude_web")
                client = client_mod.ClaudeWebClient(auth)
                await client.initialize()
                return client
            
            # TODO: Add other clients here (ChatGPT, DeepSeek, etc.)
            return None
        except Exception as e:
            logger.error(f"Failed to load web model client for {self.provider_id}: {e}")
            return None

    def _format_messages(self, messages: List[Dict]) -> str:
        """Format messages into a single prompt for web models.
        
        Uses a format compatible with most chat models when used in completion mode.
        """
        res = ""
        for m in messages:
            role = m["role"]
            content = m["content"]
            
            if role == "system":
                res += f"System: {content}\n\n"
            elif role == "user":
                res += f"Human: {content}\n\n"
            elif role == "assistant":
                res += f"Assistant: {content}\n\n"
            else:
                res += f"{role.capitalize()}: {content}\n\n"
        
        # Ensure it ends with Assistant: to prompt the model to respond
        if not res.strip().endswith("Assistant:"):
            res = res.strip() + "\n\nAssistant:"
            
        return res.strip()

    def _map_chunk(self, chunk, tool_calls=None):
        delta = SimpleNamespace(content=chunk.content, role="assistant", tool_calls=tool_calls)
        choice = SimpleNamespace(index=0, delta=delta, finish_reason="stop" if chunk.done else None)
        return SimpleNamespace(choices=[choice], model=self.model)

    def _error_chunk(self, error_msg):
        delta = SimpleNamespace(content=f"\n[Web Model Error] {error_msg}\n", role="assistant")
        choice = SimpleNamespace(index=0, delta=delta, finish_reason="error")
        return SimpleNamespace(choices=[choice], model=self.model)

    def _extract_tool_calls(self, content: str) -> Optional[List[Any]]:
        try:
            tool_calling = self._get_tool_calling_module()
            if not tool_calling:
                return None
                
            call = tool_calling.parse_tool_call(content)
            if not call:
                return None
            
            fn = SimpleNamespace(name=call["tool"], arguments=json.dumps(call["parameters"]))
            tc = SimpleNamespace(id=f"call_{uuid.uuid4().hex[:12]}", type="function", function=fn)
            return [tc]
        except Exception as e:
            logger.debug(f"Failed to extract tool call: {e}")
            return None

    def close(self):
        pass

class AsyncWebModelAuxiliaryClient:
    """Async version of the WebModelAuxiliaryClient."""
    def __init__(self, sync_wrapper: WebModelAuxiliaryClient):
        self._sync = sync_wrapper
        self.chat = SimpleNamespace(completions=self)
        self.api_key = sync_wrapper.api_key
        self.base_url = sync_wrapper.base_url

    async def create(self, **kwargs):
        # Already async
        if kwargs.get("stream"):
            return self._sync.acreate(**kwargs)
        
        # Collect for non-stream
        content = ""
        finish_reason = None
        async for chunk in self._sync.acreate(**kwargs):
            if chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content
            if chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason
        
        tool_calls = self._sync._extract_tool_calls(content)
        message = SimpleNamespace(role="assistant", content=content, tool_calls=tool_calls)
        choice = SimpleNamespace(index=0, message=message, finish_reason=finish_reason or "stop")
        return SimpleNamespace(choices=[choice], model=self.model)

    @property
    def model(self):
        return self._sync.model

    def close(self):
        self._sync.close()
