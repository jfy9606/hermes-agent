# Zero Token Web Models Plugin

**Browser-based AI model access without API keys - Zero cost**

## Overview

This plugin integrates **Zero Token** functionality into Hermes Agent's **Plugin System**, allowing access to 9 major AI models through browser sessions (cookies) instead of paid API keys.

## Architecture (Correct Pattern) ✅

```
plugins/model_providers/web_models/    # ✅ Follows Hermes plugin conventions
├── __init__.py                        #    register_provider() for all 9 providers
├── plugin.yaml                        #    Plugin metadata
├── config.py                          #    Provider configurations
├── base.py                            #    Abstract base classes
├── auth.py                            #    Authentication management
├── tool_calling.py                    #    Tool calling via prompt injection
├── cli.py                             #    CLI interface
└── clients/                           #    Client implementations
    ├── __init__.py
    └── claude_web.py                 #    Claude.ai client (reference)
```

## Why This Architecture? 🤔

### ❌ Wrong Approach (Previous)
```bash
zerotoken/           # ❌ Independent top-level package
├── __init__.py      #    Violates project structure
└── ...              #    Not discoverable by plugin system
```

**Problems:**
- Breaks Hermes Agent's plugin discovery mechanism
- Not auto-loaded with other model providers
- Requires manual import/initialization
- Inconsistent with 30+ existing provider plugins

### ✅ Correct Approach (Current)
```bash
plugins/model_providers/web_models/   # ✅ Standard plugin location
├── __init__.py                       #    Auto-discovered and loaded
└── plugin.yaml                       #    Proper metadata
```

**Benefits:**
- ✅ Auto-registered with `providers.register_provider()`
- ✅ Appears in `hermes models` / `hermes tools` output
- ✅ Follows same pattern as `anthropic`, `deepseek`, `openai_codex`, etc.
- ✅ Consistent with Hermes AGENTS.md specifications
- ✅ Can be enabled/disabled like any other plugin

## Supported Providers

| Provider ID | Name | Default Model | Context | Cost |
|-------------|------|--------------|---------|------|
| `claude-web` | Claude Web | claude-sonnet-4-6 | 200K | $0 |
| `chatgpt-web` | ChatGPT Web | gpt-4 | 128K | $0 |
| `deepseek-web` | DeepSeek Web | deepseek-chat | 64K | $0 |
| `doubao-web` | Doubao Web | doubao-seed-2.0 | 64K | $0 |
| `gemini-web` | Gemini Web | gemini-pro | 32K | $0 |
| `glm-web` | GLM Web | glm-4-plus | 32K | $0 |
| `grok-web` | Grok Web | grok-2 | 32K | $0 |
| `kimi-web` | Kimi Web | moonshot-v1-32k | 32K | $0 |
| `qwen-web` | Qwen Web | qwen-max | 32K | $0 |

## Quick Start

### 1. List Available Models

```bash
cd /home/jfy/hermes-agent
python3 -m plugins.model_providers.web_models.cli list
```

### 2. Authenticate

**Option A: Direct Cookie**

```bash
python3 -m plugins.model_providers.web_models.cli auth claude-web --cookie <sessionKey>
```

**Option B: Get Instructions**

```bash
python3 -m plugins.model_providers.web_models.cli auth claude-web
```

### 3. Check Status

```bash
python3 -m plugins.model_providers.web_models.cli status
```

### 4. Test Connection

```bash
python3 -m plugins.model_providers.web_models.cli test claude-web
```

## Usage in Python

```python
from web_models.config import WEB_PROVIDERS_CONFIG
from web_models.auth import WebAuthManager
from web_models.base import WebModelAuth
from web_models.clients.claude_web import ClaudeWebClient

async def main():
    # Load saved credentials
    manager = WebAuthManager()
    auth_data = manager.get_auth("claude-web")

    if not auth_data:
        print("Please authenticate first!")
        return

    # Create client
    auth = WebModelAuth.from_dict(auth_data)
    client = ClaudeWebClient(auth)

    # Initialize (discovers org ID, etc.)
    await client.initialize()

    # Send message
    print("Sending to Claude Web...")
    async for chunk in client.chat_completions(message="Hello!"):
        if chunk.content:
            print(chunk.content, end="", flush=True)
        if chunk.done:
            print("\n[Done]")

import asyncio
asyncio.run(main())
```

## Tool Calling Support

Web models don't support native tool calling. This plugin implements it via **prompt injection**:

```python
from web_models.tool_calling import (
    should_inject_tool_prompt,
    get_tool_prompt,
    parse_tool_call,
)

# Check if injection needed
if should_inject_tool_prompt("claude-web"):
    # Generate tool prompt
    tools = [{"name": "get_weather", "description": "Get weather", "parameters": {...}}]
    prompt = get_tool_prompt("claude-web", tools)

    # Append to system/user message
    full_message = f"{prompt}\n\nUser: What's the weather in Beijing?"

# Parse response
response = '```tool_json\n{"tool":"get_weather","parameters":{"city":"Beijing"}}\n```'
tool_call = parse_tool_call(response)
# → {"tool": "get_weather", "parameters": {"city": "Beijing"}}
```

## Authentication Storage

Credentials stored at:
```
~/.hermes/web_auth_profiles.json
```

Format:
```json
{
  "claude-web": {
    "sessionKey": "sk-ant-...",
    "userAgent": "Mozilla/5.0 ..."
  }
}
```

## Integration with Hermes Agent

This plugin **auto-registers** all 9 web providers on import. They appear as:

```bash
$ hermes models | grep web
claude-web          Claude Web (Zero Token)
chatgpt-web         ChatGPT Web (Zero Token)
deepseek-web        DeepSeek Web (Zero Token)
...
```

Usage in Hermes:
```bash
# Select web model
/model claude-web/claude-sonnet-4-6

# Use normally - no API key needed!
Hello, how are you?
```

## Adding New Providers

1. Create client in `clients/new_provider_web.py`
2. Add config to `config.py` (`WEB_PROVIDERS_CONFIG`)
3. Import client in `clients/__init__.py`
4. Update README

## Comparison: Example vs Implementation

| Aspect | example/openclaw-zero-token | plugins/model-providers/web-models |
|--------|---------------------------|-----------------------------------|
| Language | TypeScript | Python |
| Location | Standalone repo | Hermes plugin |
| Discovery | Manual import | Auto `register_provider()` |
| Auth storage | openclaw.json | ~/.hermes/web_auth_profiles.json |
| HTTP library | fetch/node:http | httpx |
| Streaming | StreamFn interface | AsyncGenerator[StreamChunk] |

## Files Created

**Core Plugin (8 files):**
- [__init__.py](./__init__.py) - Provider registration
- [plugin.yaml](./plugin.yaml) - Metadata
- [config.py](./config.py) - Provider definitions
- [base.py](./base.py) - Base classes
- [auth.py](./auth.py) - Authentication management
- [tool_calling.py](./tool_calling.py) - Tool calling support
- [cli.py](./cli.py) - CLI interface
- [clients/claude_web.py](./clients/claude_web.py) - Reference implementation

## Security Notes

⚠️ **Important:**
- Session cookies are sensitive credentials
- Stored locally only (~/.hermes/)
- Sessions expire and require refresh
- All connections use HTTPS

## Dependencies

```bash
pip install httpx  # Required for streaming HTTP requests
```

## Status

✅ **Architecture**: Correctly follows Plugin System pattern  
⚠️ **Implementation**: Alpha - Claude Web fully implemented, others need clients  
🔄 **Testing**: Needs real session cookies for E2E validation  

---

**Version**: 1.0.0  
**Pattern**: Model Provider Plugin (AGENTS.md compliant)  
**Reference**: [example/openclaw-zero-token/](../../../example/openclaw-zero-token/)
