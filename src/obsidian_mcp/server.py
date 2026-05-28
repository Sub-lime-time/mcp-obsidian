"""MCP server factory: registers all 15 Obsidian vault tools via FastMCP."""
from __future__ import annotations

import json
import os
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .filesystem import FileSystemService
from .pathfilter import PathFilter
from .search import SearchService


def create_server(vault_path: str, name: str = "obsidian-mcp") -> FastMCP:
    if not os.path.isdir(vault_path):
        raise NotADirectoryError(
            f"Vault path does not exist or is not a directory: {vault_path!r}"
        )

    path_filter = PathFilter()
    fs = FileSystemService(vault_path, path_filter)
    search_svc = SearchService(vault_path, path_filter)
    mcp = FastMCP(name)

    # ── read_note ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def read_note(
        path: Annotated[str, Field(description="Path to the note relative to vault root")],
        pretty_print: Annotated[bool, Field(description="Format JSON response with indentation")] = False,
    ) -> str:
        """Read a note from the Obsidian vault."""
        note = fs.read_note(path)
        indent = 2 if pretty_print else None
        return json.dumps({"fm": note["frontmatter"], "content": note["content"]}, indent=indent, default=str)

    # ── write_note ────────────────────────────────────────────────────────────

    @mcp.tool()
    def write_note(
        path: Annotated[str, Field(description="Path to the note relative to vault root")],
        content: Annotated[str, Field(description="Body content of the note")],
        frontmatter: Annotated[dict | None, Field(description="Frontmatter object (optional)")] = None,
        mode: Annotated[str, Field(description="Write mode: overwrite (default), append, or prepend")] = "overwrite",
    ) -> str:
        """Write a note to the Obsidian vault."""
        fs.write_note(path, content, frontmatter, mode)
        return f"Successfully wrote note: {path} (mode: {mode})"

    # ── patch_note ────────────────────────────────────────────────────────────

    @mcp.tool()
    def patch_note(
        path: Annotated[str, Field(description="Path to the note relative to vault root")],
        old_string: Annotated[str, Field(description="Exact string to replace (including whitespace/newlines)")],
        new_string: Annotated[str, Field(description="Replacement string")],
        replace_all: Annotated[bool, Field(description="Replace all occurrences (default: false — fails on multiple matches)")] = False,
    ) -> str:
        """Efficiently update part of a note by replacing a specific string."""
        result = fs.patch_note(path, old_string, new_string, replace_all)
        return json.dumps(result, indent=2)

    # ── list_directory ────────────────────────────────────────────────────────

    @mcp.tool()
    def list_directory(
        path: Annotated[str, Field(description="Path relative to vault root (default: vault root)")] = "/",
        pretty_print: Annotated[bool, Field(description="Format JSON response with indentation")] = False,
    ) -> str:
        """List files and directories in the vault."""
        listing = fs.list_directory(path)
        indent = 2 if pretty_print else None
        return json.dumps({"dirs": listing["directories"], "files": listing["files"]}, indent=indent)

    # ── delete_note ───────────────────────────────────────────────────────────

    @mcp.tool()
    def delete_note(
        path: Annotated[str, Field(description="Path to the note relative to vault root")],
        confirm_path: Annotated[str, Field(description="Must exactly match path to confirm deletion")],
        trash_mode: Annotated[str, Field(description="permanent (default) — delete forever; local — move to .trash/ inside vault; system — move to OS trash")] = "permanent",
    ) -> str:
        """Delete a note from the Obsidian vault. confirm_path must exactly match path."""
        result = fs.delete_note(path, confirm_path, trash_mode)
        return json.dumps(result, indent=2)

    # ── search_notes ──────────────────────────────────────────────────────────

    @mcp.tool()
    def search_notes(
        query: Annotated[str, Field(description="Search query text")],
        limit: Annotated[int, Field(description="Maximum results (default: 5, max: 20)")] = 5,
        search_content: Annotated[bool, Field(description="Search in note body (default: true)")] = True,
        search_frontmatter: Annotated[bool, Field(description="Search in frontmatter (default: false)")] = False,
        case_sensitive: Annotated[bool, Field(description="Case-sensitive search (default: false)")] = False,
        pretty_print: Annotated[bool, Field(description="Format JSON response with indentation")] = False,
    ) -> str:
        """Search for notes in the vault by content or frontmatter. Returns BM25-ranked results."""
        results = search_svc.search(query, limit, search_content, search_frontmatter, case_sensitive)
        indent = 2 if pretty_print else None
        return json.dumps(results, indent=indent)

    # ── move_note ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def move_note(
        old_path: Annotated[str, Field(description="Current path of the note")],
        new_path: Annotated[str, Field(description="New path for the note")],
        overwrite: Annotated[bool, Field(description="Allow overwriting existing file (default: false)")] = False,
    ) -> str:
        """Move or rename a note in the vault."""
        result = fs.move_note(old_path, new_path, overwrite)
        return json.dumps(result, indent=2)

    # ── move_file ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def move_file(
        old_path: Annotated[str, Field(description="Current path of the file")],
        new_path: Annotated[str, Field(description="New path for the file")],
        confirm_old_path: Annotated[str, Field(description="Must exactly match old_path")],
        confirm_new_path: Annotated[str, Field(description="Must exactly match new_path")],
        overwrite: Annotated[bool, Field(description="Allow overwriting existing file (default: false)")] = False,
    ) -> str:
        """Move or rename any file in the vault (binary-safe). Requires path confirmation."""
        result = fs.move_file(old_path, new_path, confirm_old_path, confirm_new_path, overwrite)
        return json.dumps(result, indent=2)

    # ── read_multiple_notes ───────────────────────────────────────────────────

    @mcp.tool()
    def read_multiple_notes(
        paths: Annotated[list[str], Field(description="Array of note paths to read (max 10)")],
        include_content: Annotated[bool, Field(description="Include note body (default: true)")] = True,
        include_frontmatter: Annotated[bool, Field(description="Include frontmatter (default: true)")] = True,
        pretty_print: Annotated[bool, Field(description="Format JSON response with indentation")] = False,
    ) -> str:
        """Read multiple notes in a single batch (max 10 files)."""
        result = fs.read_multiple_notes(paths, include_content, include_frontmatter)
        indent = 2 if pretty_print else None
        return json.dumps({"ok": result["successful"], "err": result["failed"]}, indent=indent, default=str)

    # ── update_frontmatter ────────────────────────────────────────────────────

    @mcp.tool()
    def update_frontmatter(
        path: Annotated[str, Field(description="Path to the note")],
        frontmatter: Annotated[dict, Field(description="Frontmatter fields to update")],
        merge: Annotated[bool, Field(description="Merge with existing frontmatter (default: true)")] = True,
    ) -> str:
        """Update frontmatter of a note without changing its body content."""
        fs.update_frontmatter(path, frontmatter, merge)
        return f"Successfully updated frontmatter for: {path}"

    # ── get_notes_info ────────────────────────────────────────────────────────

    @mcp.tool()
    def get_notes_info(
        paths: Annotated[list[str], Field(description="Array of note paths to inspect")],
        pretty_print: Annotated[bool, Field(description="Format JSON response with indentation")] = False,
    ) -> str:
        """Get metadata (size, modified date, has frontmatter) without reading full content."""
        result = fs.get_notes_info(paths)
        indent = 2 if pretty_print else None
        return json.dumps(result, indent=indent)

    # ── get_frontmatter ───────────────────────────────────────────────────────

    @mcp.tool()
    def get_frontmatter(
        path: Annotated[str, Field(description="Path to the note relative to vault root")],
        pretty_print: Annotated[bool, Field(description="Format JSON response with indentation")] = False,
    ) -> str:
        """Extract frontmatter from a note without reading its body content."""
        note = fs.read_note(path)
        indent = 2 if pretty_print else None
        return json.dumps(note["frontmatter"], indent=indent, default=str)

    # ── manage_tags ───────────────────────────────────────────────────────────

    @mcp.tool()
    def manage_tags(
        path: Annotated[str, Field(description="Path to the note relative to vault root")],
        operation: Annotated[str, Field(description="Operation: add, remove, or list")],
        tags: Annotated[list[str] | None, Field(description="Tags for add/remove operations")] = None,
    ) -> str:
        """Add, remove, or list tags in a note's frontmatter."""
        result = fs.manage_tags(path, operation, tags)
        return json.dumps(result, indent=2)

    # ── get_vault_stats ───────────────────────────────────────────────────────

    @mcp.tool()
    def get_vault_stats(
        recent_count: Annotated[int, Field(description="Number of recently modified files to return (default: 5, max: 20)")] = 5,
        pretty_print: Annotated[bool, Field(description="Format JSON response with indentation")] = False,
    ) -> str:
        """Get vault statistics: total notes, folders, size, and recently modified files."""
        stats = fs.get_vault_stats(recent_count)
        indent = 2 if pretty_print else None
        return json.dumps(
            {
                "notes": stats["totalNotes"],
                "folders": stats["totalFolders"],
                "size": stats["totalSize"],
                "recent": stats["recentlyModified"],
            },
            indent=indent,
        )

    # ── list_all_tags ─────────────────────────────────────────────────────────

    @mcp.tool()
    def list_all_tags(
        pretty_print: Annotated[bool, Field(description="Format JSON response with indentation")] = False,
    ) -> str:
        """List all tags across the vault with occurrence counts, sorted by frequency."""
        tags = fs.list_all_tags()
        indent = 2 if pretty_print else None
        return json.dumps(tags, indent=indent)

    return mcp
