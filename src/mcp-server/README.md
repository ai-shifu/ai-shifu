# AI-Shifu MCP Server

MCP (Model Context Protocol) server that wraps the AI-Shifu course management API, enabling Claude Code, Claude Desktop, and Claude.ai to manage interactive AI courses through natural language.

## Prerequisites

- Python 3.10+
- An AI-Shifu instance with API Key authentication enabled
- An API Key generated from your AI-Shifu account settings

## Installation

### Via uvx (Recommended)

```bash
uvx ai-shifu-mcp
```

### From Source (Development)

```bash
cd src/mcp-server
uv sync
uv run ai-shifu-mcp
```

## Configuration

### Claude Code

Add to your Claude Code MCP settings (`.claude/settings.json` or project settings):

```json
{
  "mcpServers": {
    "ai-shifu": {
      "command": "uvx",
      "args": ["ai-shifu-mcp"],
      "env": {
        "AISHIFU_BASE_URL": "https://your-domain.com",
        "AISHIFU_API_KEY": "sk-your-api-key"
      }
    }
  }
}
```

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "ai-shifu": {
      "command": "uvx",
      "args": ["ai-shifu-mcp"],
      "env": {
        "AISHIFU_BASE_URL": "https://your-domain.com",
        "AISHIFU_API_KEY": "sk-your-api-key"
      }
    }
  }
}
```

### Claude.ai (Web)

Claude.ai requires a **remote HTTP endpoint** instead of a local stdio process. You need to:

1. **Start the server in HTTP mode** on a publicly accessible host:

```bash
# Set environment variables
export AISHIFU_BASE_URL=https://your-domain.com
export AISHIFU_API_KEY=sk-your-api-key

# Start HTTP server (default port 8000)
ai-shifu-mcp --transport http --port 8000
```

2. **Add as Remote MCP in Claude.ai**:
   - Go to [Claude.ai](https://claude.ai) → Settings → Integrations
   - Click "Add Integration" → "MCP Server"
   - Enter your server URL: `https://your-server:8000/mcp`
   - Save and start using

> **Note**: The HTTP endpoint must be accessible from the internet. For production
> use, deploy behind a reverse proxy (nginx/Caddy) with HTTPS. For quick testing,
> you can use a tunnel service like `ngrok` or `cloudflared`:
>
> ```bash
> # Quick tunnel for testing (not for production)
> ngrok http 8000
> # Then use the ngrok URL in Claude.ai: https://xxxx.ngrok.io/mcp
> ```

### Local Development

Point to your local AI-Shifu instance:

```json
{
  "mcpServers": {
    "ai-shifu": {
      "command": "uv",
      "args": ["--directory", "/path/to/src/mcp-server", "run", "ai-shifu-mcp"],
      "env": {
        "AISHIFU_BASE_URL": "http://localhost:8080",
        "AISHIFU_API_KEY": "sk-your-api-key"
      }
    }
  }
}
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AISHIFU_BASE_URL` | Yes | Base URL of your AI-Shifu instance |
| `AISHIFU_API_KEY` | Yes | API Key for authentication (starts with `sk-`) |

## Available Tools

### Course Management

| Tool | Description |
|------|-------------|
| `list_courses` | List all courses with pagination |
| `create_course` | Create a new course (returns bid for subsequent operations) |
| `get_course_detail` | Get full course config (system prompt, model, temperature, etc.) |
| `update_course_detail` | Update course settings (name, description, system prompt, model, etc.) |

### Outline Management

| Tool | Description |
|------|-------------|
| `get_outlines` | Get the chapter/section tree structure |
| `create_outline` | Create a chapter (top-level) or section (under a chapter) |
| `update_outline` | Update chapter/section properties |
| `delete_outline` | Delete a chapter or section (cascading) |
| `reorder_outlines` | Reorder chapters and sections |

### Content Management

| Tool | Description |
|------|-------------|
| `get_lesson_content` | Get MDFlow content of a section |
| `save_lesson_content` | Save MDFlow content to a section |

### Preview & Publish

| Tool | Description |
|------|-------------|
| `preview_course` | Generate a preview link |
| `publish_course` | Publish a course for learners |

## Usage Examples

Once configured, use natural language in Claude Code, Claude Desktop, or Claude.ai:

```
"List all my courses"
"Create a Python beginner course called 'Python 101'"
"Show me the outline of course <bid>"
"Add a new chapter called 'Variables and Data Types' to course <bid>"
"Write the lesson content for section <outline_bid> about Python variables"
"Preview the course"
"Publish the course"
```

## Development

### Interactive Testing with FastMCP Inspector

```bash
cd src/mcp-server
uv run fastmcp dev src/ai_shifu_mcp/server.py
```

### Running Locally (stdio)

```bash
cd src/mcp-server
uv run ai-shifu-mcp
```

### Running as HTTP Server (for Claude.ai)

```bash
cd src/mcp-server
AISHIFU_BASE_URL=http://localhost:8080 AISHIFU_API_KEY=sk-xxx uv run ai-shifu-mcp --transport http --port 8000
```

## Architecture

```
ai_shifu_mcp/
├── __init__.py       # Package version
├── __main__.py       # CLI entry point (stdio / http transport)
├── server.py         # FastMCP instance + 13 tool definitions
└── api_client.py     # Async HTTP client wrapping AI-Shifu REST API
```

The server uses FastMCP's lifespan pattern to manage a shared `httpx.AsyncClient` that handles authentication and request/response envelope unwrapping. All tools receive the client via `ctx.lifespan_context`.
