"""Entry point for `python -m ai_shifu_mcp`.

Supports two transport modes:
  - stdio (default): for Claude Code and Claude Desktop
  - http: for Claude.ai and other remote MCP clients
"""

import argparse

from ai_shifu_mcp.server import mcp


def main():
    parser = argparse.ArgumentParser(
        description="AI-Shifu MCP Server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: stdio (local) or http (remote, for Claude.ai)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind when using http transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind when using http transport (default: 8000)",
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
