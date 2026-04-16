# CLAUDE.md — obsidian-mcp

Python MCP server for Obsidian vault access. Port of [bitbonsai/mcpvault](https://github.com/bitbonsai/mcpvault) v0.11.0 using `uv` Python instead of Node.js.

---

## Project Layout

```
src/obsidian_mcp/
├── __main__.py    CLI entry: obsidian-mcp <vault-path> [server-name]
├── server.py      FastMCP server, all 15 tools registered here
├── filesystem.py  All vault I/O + security enforcement
├── search.py      BM25 full-text search
├── fm.py          Frontmatter parse/stringify (python-frontmatter + PyYAML)
└── pathfilter.py  Path allow/deny filtering
```

## Running

```bash
uv run obsidian-mcp /path/to/vault            # single vault
uv run obsidian-mcp /path/to/vault my-name    # custom server name (for multi-vault)
```

## Dependencies

Managed by `uv`. Never use `pip` directly.

```bash
uv add <package>    # add a dep
uv run <cmd>        # run in the project venv
```

## Security Model

- **No shell execution.** All operations are pure Python file I/O. Never add `subprocess`.
- **Path traversal prevention** is in `filesystem.py _resolve()`. Do not weaken it:
  - Lexical check: `os.path.relpath(full, vault_path).startswith("..")`
  - Symlink check: `os.path.realpath(full)` must stay within vault root
- **PathFilter** in `pathfilter.py` blocks `.obsidian/`, `.git/`, `node_modules/`, and non-note extensions. Don't loosen it without explicit request.
- **Destructive ops** (`delete_note`, `move_file`) require confirmation path parameters.
- **YAML safety**: `python-frontmatter` uses `yaml.safe_load` by default. Never switch to `yaml.load`.

## Multi-Vault Usage

The server takes a vault path at startup — run one instance per vault. Each instance gets its own entry in the Claude Code MCP config (`~/.claude.json`):

```json
"obsidian-greg": {
  "command": "uv",
  "args": ["--directory", "/Users/greg/repos/projects/mcp-obsidian", "run", "obsidian-mcp", "/path/to/vault"]
}
```

## Rules for AI Assistants

1. **Python 3.11+** — use modern syntax (`X | Y` unions, `match`, `str.removesuffix`, etc.).
2. **uv only** for package management — never `pip install`.
3. **Don't weaken security checks** — if a path filtering or traversal check seems overly strict, ask before removing it.
4. **Sync I/O is intentional** — MCP requests are serial; async is not needed.
5. **Tool parameter names are snake_case** — the FastMCP schema reflects this. Don't convert to camelCase.
6. **15 tools exactly** — they mirror mcpvault v0.11.0. Add new tools only when explicitly requested.
7. **Preserve key order in frontmatter** — the `_ObsidianHandler` in `fm.py` uses `sort_keys=False`. Keep it that way.
