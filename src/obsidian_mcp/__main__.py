"""CLI entry point: obsidian-mcp <vault-path> [server-name]"""
from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(
            "Usage: obsidian-mcp <vault-path> [server-name]\n"
            "\n"
            "  vault-path   Absolute path to your Obsidian vault directory\n"
            "  server-name  Optional MCP server name (default: obsidian-mcp)\n"
            "\n"
            "Examples:\n"
            "  obsidian-mcp /Users/alice/Documents/MyVault\n"
            "  obsidian-mcp /Users/alice/Documents/MyVault alice-vault\n",
            file=sys.stderr,
        )
        sys.exit(1 if len(sys.argv) < 2 else 0)

    vault_path = sys.argv[1]
    server_name = sys.argv[2] if len(sys.argv) > 2 else "obsidian-mcp"

    from .server import create_server  # deferred so --help is fast

    mcp = create_server(vault_path, server_name)
    mcp.run()


if __name__ == "__main__":
    main()
