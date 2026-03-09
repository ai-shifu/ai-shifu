---
name: mcp-setup
description: Guide for setting up and using the AI-Shifu MCP server. Use when a user asks about connecting Claude Code or Claude Desktop to AI-Shifu, configuring the MCP server, generating API keys, troubleshooting MCP connection issues, or wants to manage AI-Shifu courses through MCP tools.
argument-hint: "[setup|usage|troubleshoot]"
---

# AI-Shifu MCP Server Setup & Usage

This skill covers the full lifecycle of the AI-Shifu MCP server: from generating an API key, to configuring Claude Code / Claude Desktop, to using the 13 course management tools.

## Architecture Overview

```
Claude (Client)
  │  stdio or Streamable HTTP
  ▼
FastMCP Server (src/mcp-server/)
  │  server.py — 13 @mcp.tool functions
  │  api_client.py — async HTTP wrapper
  │  HTTP REST
  ▼
AI-Shifu Backend (Flask, port 8080)
```

- **Source code**: `src/mcp-server/`
- **Entry point**: `src/mcp-server/src/ai_shifu_mcp/__main__.py`
- **Dependencies**: `fastmcp>=2.0.0`, `httpx>=0.27.0`

---

## Step 1: Prerequisites

Ensure the AI-Shifu backend is running (Docker or local):

```bash
# Docker (local build)
cd docker && ./dev_in_docker.sh

# Or official images
cd docker && docker compose -f docker-compose.latest.yml up -d
```

Verify: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/user/info` should return `200`.

Also ensure `uv` is installed:

```bash
which uv || pip install uv
```

---

## Step 2: Generate an API Key

The MCP server authenticates via API key (`sk-xxx` format). Create one through the backend API:

1. Log in to Cook Web (`http://localhost:8080/admin`) and obtain a session token from browser DevTools (Network tab → any API request → `Authorization` header).

2. Create the API key:

```bash
curl -X POST http://localhost:8080/api/user/api-keys \
  -H "Authorization: Bearer <your-session-token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "MCP Server"}'
```

3. Save the returned `key` field (`sk-xxx`). It is shown **only once** — the database stores only the SHA-256 hash.

Manage keys:
- **List**: `GET /api/user/api-keys`
- **Revoke**: `DELETE /api/user/api-keys/<key_bid>`

---

## Step 3: Configure Claude Code (global)

Use the `claude` CLI to add the MCP server at user scope (available across all projects):

```bash
claude mcp add ai-shifu --scope user \
  -e AISHIFU_BASE_URL=http://localhost:8080 \
  -e AISHIFU_API_KEY=sk-YOUR_KEY_HERE \
  -e NO_PROXY=localhost,127.0.0.1 \
  -e ALL_PROXY= \
  -e HTTP_PROXY= \
  -e HTTPS_PROXY= \
  -e http_proxy= \
  -e https_proxy= \
  -- /opt/anaconda3/envs/ai/bin/uv \
  --directory /Users/heshaofu/Documents/code/myproject/AI/ai-shifu-code/ai-shifu/src/mcp-server \
  run ai-shifu-mcp
```

> **Why clear proxy vars?** If the system has SOCKS proxy configured (`ALL_PROXY=socks5://...`), `httpx` will fail at client initialization because `socksio` is not installed. Clearing proxy vars for the MCP subprocess avoids this while not affecting other programs.

Then add `"ai-shifu"` to `enabledMcpjsonServers` in `~/.claude/settings.json`:

```json
{
  "enabledMcpjsonServers": ["context7", "ai-shifu"]
}
```

**Verify**: Restart Claude Code, run `/mcp` — `ai-shifu` should show as `connected` under User MCPs.

---

## Step 4: Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ai-shifu": {
      "command": "/opt/anaconda3/envs/ai/bin/uv",
      "args": [
        "--directory",
        "/Users/heshaofu/Documents/code/myproject/AI/ai-shifu-code/ai-shifu/src/mcp-server",
        "run",
        "ai-shifu-mcp"
      ],
      "env": {
        "AISHIFU_BASE_URL": "http://localhost:8080",
        "AISHIFU_API_KEY": "sk-YOUR_KEY_HERE",
        "NO_PROXY": "localhost,127.0.0.1",
        "ALL_PROXY": "",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "http_proxy": "",
        "https_proxy": ""
      }
    }
  }
}
```

**Verify**: Restart Claude Desktop — AI-Shifu tools should appear in the tools menu.

---

## Available MCP Tools (13 total)

### Course Management
| Tool | Description |
|------|-------------|
| `list_courses` | List all courses with pagination |
| `create_course` | Create a new course (name, description) |
| `get_course_detail` | Get full course config (system prompt, model, temperature) |
| `update_course_detail` | Update course settings |

### Outline Management
| Tool | Description |
|------|-------------|
| `get_outlines` | Get chapter/section tree structure |
| `create_outline` | Create chapter or section |
| `update_outline` | Update chapter/section properties |
| `delete_outline` | Delete chapter/section (cascading) |
| `reorder_outlines` | Reorder by position |

### Content Management
| Tool | Description |
|------|-------------|
| `get_lesson_content` | Get MDFlow content of a lesson |
| `save_lesson_content` | Save/update MDFlow content |

### Preview & Publish
| Tool | Description |
|------|-------------|
| `preview_course` | Generate preview link |
| `publish_course` | Publish course (returns public URL) |

### Example Usage (natural language)

- "Create a new course called 'Python Basics'"
- "Add a chapter 'Variables' to course xxx, then add sections for integers, strings, and lists"
- "Show me the MDFlow content of the first section"
- "Publish the course and give me the link"

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `/mcp` shows no `ai-shifu` | Not in `enabledMcpjsonServers` | Add to `~/.claude/settings.json` |
| `ai-shifu` shows but "failed to connect" | Proxy or startup error | Clear proxy vars in env config |
| `ImportError: socksio` | SOCKS proxy detected by httpx | Set `ALL_PROXY=` in MCP env |
| `AiShifuAPIError` | Invalid/revoked API key | Generate a new key via `/api/user/api-keys` |
| Backend unreachable | Docker not running | Start Docker services first |
| Tools work in one project but not another | MCP added at project scope | Use `--scope user` for global access |

### Debug Commands

```bash
# Test MCP server locally
cd src/mcp-server
AISHIFU_BASE_URL=http://localhost:8080 \
AISHIFU_API_KEY=sk-xxx \
uv run ai-shifu-mcp --help

# Interactive testing with FastMCP Inspector
uv run fastmcp dev src/ai_shifu_mcp/server.py

# Check Claude Code MCP status
claude mcp list
```

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `src/mcp-server/pyproject.toml` | Package definition and dependencies |
| `src/mcp-server/src/ai_shifu_mcp/__main__.py` | CLI entry point (transport selection) |
| `src/mcp-server/src/ai_shifu_mcp/server.py` | FastMCP server with 13 tool definitions |
| `src/mcp-server/src/ai_shifu_mcp/api_client.py` | Async HTTP wrapper for AI-Shifu REST API |
| `src/api/flaskr/service/user/api_key_funcs.py` | API key CRUD and validation logic |
| `src/api/flaskr/service/user/api_key_models.py` | API key database model |
| `~/.claude.json` | Global MCP server config (user scope) |
| `~/Library/Application Support/Claude/claude_desktop_config.json` | Claude Desktop config |
