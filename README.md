# obsidian-mcp

Python MCP server for Obsidian vault access. A port of [bitbonsai/mcpvault](https://github.com/bitbonsai/mcpvault) using `uv` Python instead of Node.js — designed for local use across multiple vaults.

## Features

- **15 tools** covering all vault operations: read, write, patch, search, move, delete, tag management, frontmatter, and vault stats
- **BM25 full-text search** with multi-word relevance reranking
- **Safe frontmatter** — YAML parsed with `yaml.safe_load`, key order preserved on writes
- **Security hardened** — path traversal prevention with lexical + symlink boundary checks (mirrors mcpvault v0.9.1), PathFilter blocks `.obsidian/`, `.git/`, and non-note extensions, destructive ops require path confirmation
- **Multi-vault** — run one instance per vault, each with its own MCP server name
- **Pure Python** — no Node.js required, managed entirely by `uv`

## Requirements

- macOS (tested) or Linux
- [uv](https://docs.astral.sh/uv/) — Python package manager
- Python 3.11+ (installed automatically by `uv`)
- Claude Desktop or Claude Code

## Quick Start

```bash
# Install uv (macOS)
brew install uv

# Clone and install
git clone git@github.com:Sub-lime-time/obsidian-mcp.git
cd obsidian-mcp
uv sync

# Verify
uv run obsidian-mcp --help
```

## Configuration

Run one instance per vault. Add to your MCP client config:

### Claude Desktop — `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "obsidian-my-vault": {
      "command": "/opt/homebrew/bin/uv",
      "args": [
        "--directory", "/path/to/obsidian-mcp",
        "run", "obsidian-mcp",
        "/path/to/your/vault",
        "obsidian-my-vault"
      ]
    }
  }
}
```

### Claude Code — `~/.claude/settings.json`

```json
{
  "mcpServers": {
    "obsidian-my-vault": {
      "type": "stdio",
      "command": "/opt/homebrew/bin/uv",
      "args": [
        "--directory", "/path/to/obsidian-mcp",
        "run", "obsidian-mcp",
        "/path/to/your/vault",
        "obsidian-my-vault"
      ]
    }
  }
}
```

Replace `/path/to/obsidian-mcp` with the cloned repo path and `/path/to/your/vault` with your Obsidian vault directory.

### iCloud Vault Path (macOS)

```text
/Users/<username>/Library/Mobile Documents/iCloud~md~obsidian/Documents/<Vault Name>
```

## Tools

| Tool | Description |
| --- | --- |
| `read_note` | Read a note with frontmatter |
| `write_note` | Create or update a note (overwrite / append / prepend) |
| `patch_note` | Edit part of a note via find-and-replace |
| `list_directory` | Browse vault folders |
| `delete_note` | Delete a note (requires path confirmation) |
| `search_notes` | Full-text BM25 search across content and/or frontmatter |
| `move_note` | Move or rename a note |
| `move_file` | Move any file with dual path confirmation |
| `read_multiple_notes` | Batch read up to 10 notes |
| `update_frontmatter` | Update YAML frontmatter without touching body |
| `get_notes_info` | File metadata without reading content |
| `get_frontmatter` | Extract frontmatter only |
| `manage_tags` | Add, remove, or list tags |
| `get_vault_stats` | Total notes, folders, size, recently modified |
| `list_all_tags` | All tags across vault with occurrence counts |

## Development

```bash
uv run obsidian-mcp /path/to/vault        # run against a vault
uv add <package>                           # add a dependency
```

See [CLAUDE.md](CLAUDE.md) for architecture notes and rules for AI assistants working in this repo.

## Contributing

This is a personal project. Issues are welcome, but PRs are not actively reviewed.

## Credits

Based on [bitbonsai/mcpvault](https://github.com/bitbonsai/mcpvault) (MIT). Security model mirrors mcpvault v0.9.1.

## License

MIT
