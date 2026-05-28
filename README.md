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
- [uv](https://docs.astral.sh/uv/) — Python package manager (`brew install uv`)
- Python 3.11+ (installed automatically by `uv`)
- Claude Desktop or Claude Code

## Quick Start (no clone required)

Install `uv`, then point your MCP client config at the GitHub repo directly — `uvx` handles the rest.

```bash
brew install uv
```

### Claude Code

```bash
claude mcp add --scope user obsidian-my-vault \
  uvx -- \
  --from git+https://github.com/Sub-Lime-Time/mcp-obsidian \
  obsidian-mcp "/path/to/your/vault" obsidian-my-vault
```

### Claude Desktop — `~/Library/Application Support/Claude/claude_desktop_config.json`

> **Note:** Claude Desktop's "Add custom connector" UI (Settings → Connectors) only supports remote HTTP/SSE servers. Local stdio servers like this one require JSON config editing.

Claude Desktop doesn't inherit your shell PATH, so use the full path to `uvx` (find it with `which uvx`):

```json
{
  "mcpServers": {
    "obsidian-my-vault": {
      "command": "/opt/homebrew/bin/uvx",
      "args": [
        "--from", "git+https://github.com/Sub-Lime-Time/mcp-obsidian",
        "obsidian-mcp",
        "/path/to/your/vault",
        "obsidian-my-vault"
      ]
    }
  }
}
```

> Common `uvx` paths: `/opt/homebrew/bin/uvx` (macOS Apple Silicon), `/usr/local/bin/uvx` (macOS Intel), `~/.local/bin/uvx` (Linux).

### iCloud Vault Path (macOS)

```text
/Users/<username>/Library/Mobile Documents/iCloud~md~obsidian/Documents/<Vault Name>
```

### Multiple vaults

Run one instance per vault, each with a unique server name:

```bash
claude mcp add --scope user obsidian-work \
  uvx -- \
  --from git+https://github.com/Sub-Lime-Time/mcp-obsidian \
  obsidian-mcp "/path/to/work/vault" obsidian-work
```

### Updating

`uvx` caches the installed package. To pull the latest version:

```bash
uvx cache clean
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
# Clone and install
git clone https://github.com/Sub-Lime-Time/mcp-obsidian.git
cd mcp-obsidian
uv sync

# Verify
uv run obsidian-mcp --help

# Run against a vault
uv run obsidian-mcp /path/to/vault

# Add a dependency
uv add <package>
```

See [CLAUDE.md](CLAUDE.md) for architecture notes and rules for AI assistants working in this repo.

## Contributing

Bug fixes and clear improvements are welcome — open a PR. For new features, please open an issue first to discuss before writing code. I'll merge fixes that are unambiguously correct, but make no guarantees on feature additions.

## Credits

Based on [bitbonsai/mcpvault](https://github.com/bitbonsai/mcpvault) (MIT). Security model mirrors mcpvault v0.9.1.

## License

MIT
