"""Path filtering: blocks system dirs and enforces allowed extensions."""
from __future__ import annotations

import re

_IGNORED_PATTERNS = [
    ".obsidian",
    ".obsidian/**",
    ".git",
    ".git/**",
    "node_modules",
    "node_modules/**",
    ".DS_Store",
    "Thumbs.db",
]

_ALLOWED_EXTENSIONS = {".md", ".markdown", ".txt", ".base", ".canvas"}


def _glob_match(pattern: str, path: str) -> bool:
    """Convert a simple glob pattern to a regex and test it against path."""
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        if i < len(pattern) - 1 and pattern[i : i + 2] == "**":
            parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            parts.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(pattern[i]))
            i += 1
    return bool(re.fullmatch("".join(parts), path))


def _is_file_path(path: str) -> bool:
    """Return True if the path looks like a file (has a short alphanumeric extension)."""
    if path.endswith("/"):
        return False
    last = path.split("/")[-1]
    dot = last.rfind(".")
    if dot <= 0:
        return False
    ext = last[dot + 1 :]
    return 1 <= len(ext) <= 10 and ext.isalnum()


class PathFilter:
    def __init__(
        self,
        extra_ignored: list[str] | None = None,
        extra_extensions: set[str] | None = None,
    ) -> None:
        self._ignored = _IGNORED_PATTERNS + (extra_ignored or [])
        self._extensions = _ALLOWED_EXTENSIONS | (extra_extensions or set())

    def _is_ignored(self, path: str) -> bool:
        return any(_glob_match(p, path) for p in self._ignored)

    def is_allowed(self, path: str) -> bool:
        """True if path is accessible for note read/write operations."""
        path = path.replace("\\", "/")
        if self._is_ignored(path):
            return False
        if _is_file_path(path):
            dot = path.rfind(".")
            suffix = path[dot:].lower() if dot != -1 else ""
            if suffix not in self._extensions:
                return False
        return True

    def is_allowed_for_listing(self, path: str) -> bool:
        """True if path should appear in directory listings (includes non-note files)."""
        return not self._is_ignored(path.replace("\\", "/"))
