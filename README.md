# obsidian-mcp

Python MCP server for Obsidian vault access. A port of [bitbonsai/mcpvault](https://github.com/bitbonsai/mcpvault) using `uv` Python instead of Node.js — designed for local use across multiple vaults.

## Features

- **17 tools** covering all vault operations: read, write, patch, search, move, delete, tag management, frontmatter, vault stats, and links
- **Link-aware moves**: moving or renaming a note or folder rewrites the links it would break, like Obsidian's "Automatically update internal links", without Obsidian running. See [Links](#links)
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

`uvx` caches the installed package. To pull the latest `main` and confirm which commit you're on:

```bash
uvx --refresh --from git+https://github.com/Sub-Lime-Time/mcp-obsidian python -c "import json, importlib.metadata as m; print('mcp-obsidian at', json.loads(m.distribution('obsidian-mcp').read_text('direct_url.json'))['vcs_info']['commit_id'][:7])"
```

Compare the printed commit with the latest one on `main`, then restart your MCP client so the server process picks up the new code. In Claude Desktop, quit with ⌘Q and reopen. In Claude Code, start a new session or reconnect the server in `/mcp`.

This works while the server is running, so an AI assistant can run it for you. Don't use `uv cache clean` for updates: a running `uvx` server holds uv's cache lock, so the clean waits and then fails after `UV_LOCK_TIMEOUT` (300 s by default) unless every client using the server is closed first. (`uvx cache clean` doesn't work either; it tries to run a tool named `cache`.)

## Tools

| Tool | Description |
| --- | --- |
| `read_note` | Read a note with frontmatter |
| `write_note` | Create or update a note (overwrite / append / prepend) |
| `patch_note` | Edit part of a note via find-and-replace |
| `list_directory` | Browse vault folders |
| `delete_note` | Delete a note (requires path confirmation) |
| `search_notes` | Full-text BM25 search across content and/or frontmatter |
| `move_note` | Move or rename a note or folder, rewriting links it would break (`update_links`, `dry_run`) |
| `move_file` | Move any file with dual path confirmation (also rewrites links) |
| `read_multiple_notes` | Batch read up to 10 notes |
| `update_frontmatter` | Update YAML frontmatter without touching body |
| `get_notes_info` | File metadata without reading content |
| `get_frontmatter` | Extract frontmatter only |
| `manage_tags` | Add, remove, or list tags |
| `get_vault_stats` | Total notes, folders, size, recently modified |
| `list_all_tags` | All tags across vault with occurrence counts |
| `get_note_links` | A note's outgoing links, unresolved links, and backlinks (source + line) |
| `audit_links` | Vault or folder link health: unresolved targets, orphan notes, ambiguous links |

## Links

`move_note` and `move_file` update links by default (`update_links=true`). Pass `dry_run=true` to see every change first without moving anything.

**What gets rewritten:** wikilinks and embeds (`[[Note]]`, `[[Folder/Note]]`, `[[Note.md]]`, `#heading`, `#^block`, `|alias`, and the `\|alias` form used inside tables), wikilinks in frontmatter, and markdown links (`[text](Folder/Note%20Name.md)`), including relative links inside the moved note. Links in fenced or inline code are left alone.

**The rule:** a link changes only if its current text would stop resolving to the same file after the move. A bare `[[Note]]` survives a folder move unchanged; a path link gets the new path; a rename that makes a bare name ambiguous gets the full path. Unresolved (placeholder) links are never touched. Each link keeps its own style.

**Resolution** approximates Obsidian's: a case-insensitive path-suffix match with `.md` implied; when several files match, a path relative to the linking note, then from the vault root, then the linking note's folder, then the shortest path. Links that only resolve by that last tiebreak are reported as `ambiguous`, since Obsidian may pick differently. Dot-folders (`.obsidian`, `.trash`) are ignored, as Obsidian does.

**Not covered:** `.canvas` and `.base` files, and reference-style markdown links (`[x][ref]`). A file edited between planning and writing is skipped and listed in `filesSkipped`. If a sync client undoes the move, no links are changed.

**Windows (iCloud for Windows):** a move into a folder that doesn't exist yet creates the folder and stops, returning `success: false, retry: true`; nothing moves and no links change. Retry the same call about a minute later. iCloud for Windows reverted every move into a just-created folder in testing (15/15, some 10–34 s after the move looked done, which left the rewritten links dangling), while renames and moves into existing folders never reverted (0/30). macOS and Linux are unaffected.

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
