"""All vault file operations with security boundary enforcement.

Security model (mirrors mcpvault v0.9.1):
- Lexical path traversal check: resolved path must not escape vault root
- Symlink resolution check: realpath must stay within vault boundary
- PathFilter: blocks .obsidian/, .git/, node_modules/, and non-note extensions
"""
from __future__ import annotations

import os
import re
import shutil
from typing import Any

from .fm import FrontmatterHandler
from .pathfilter import PathFilter


def _obsidian_uri(vault_path: str, rel_path: str) -> str:
    name = os.path.basename(vault_path)
    encoded = "/".join(p.replace(" ", "%20") for p in rel_path.split("/"))
    return f"obsidian://open?vault={name}&file={encoded}"


class FileSystemService:
    def __init__(self, vault_path: str, path_filter: PathFilter) -> None:
        try:
            self.vault_path = os.path.realpath(vault_path)
        except OSError:
            self.vault_path = os.path.abspath(vault_path)
        self.path_filter = path_filter
        self.fm = FrontmatterHandler()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resolve(self, relative: str) -> str:
        """Resolve a vault-relative path to an absolute path.

        Raises PermissionError on path traversal or symlink escape.
        """
        relative = (relative or "").strip().lstrip("/")
        full = os.path.normpath(os.path.join(self.vault_path, relative))

        # Lexical check: must not escape vault root
        rel = os.path.relpath(full, self.vault_path)
        if rel.startswith(".."):
            raise PermissionError(f"Path traversal not allowed: {relative!r}")

        # Symlink check: realpath must resolve within vault (mirrors v0.9.1 fix)
        try:
            real = os.path.realpath(full)
            real_rel = os.path.relpath(real, self.vault_path)
            if real_rel.startswith(".."):
                raise PermissionError(
                    f"Symlink target is outside vault: {relative!r}. "
                    "Symbolic links must resolve to a path within the vault directory."
                )
        except FileNotFoundError:
            # File doesn't exist yet — check parent dir instead
            parent = os.path.dirname(full)
            try:
                real_parent = os.path.realpath(parent)
                parent_rel = os.path.relpath(real_parent, self.vault_path)
                if parent_rel.startswith(".."):
                    raise PermissionError(
                        f"Symlink target is outside vault: {relative!r}"
                    )
            except FileNotFoundError:
                pass  # Parent also new — lexical check above is sufficient

        return full

    def _to_rel(self, full_path: str) -> str:
        return os.path.relpath(full_path, self.vault_path).replace("\\", "/")

    def _check_allowed(self, path: str, full: str) -> None:
        rel = self._to_rel(full)
        if not self.path_filter.is_allowed(rel):
            raise PermissionError(
                f"Access denied: {path!r} — system paths (.obsidian, .git) "
                "and non-note file types are not accessible."
            )

    # ── Read ──────────────────────────────────────────────────────────────────

    def read_note(self, path: str) -> dict[str, Any]:
        full = self._resolve(path)
        self._check_allowed(path, full)
        with open(full, encoding="utf-8") as f:
            content = f.read()
        meta, body = self.fm.parse(content)
        return {"frontmatter": meta, "content": body}

    # ── Write ─────────────────────────────────────────────────────────────────

    def write_note(
        self,
        path: str,
        content: str,
        frontmatter: dict | None = None,
        mode: str = "overwrite",
    ) -> None:
        full = self._resolve(path)
        self._check_allowed(path, full)
        os.makedirs(os.path.dirname(full), exist_ok=True)

        text = self.fm.stringify(frontmatter, content) if frontmatter else content

        if mode == "overwrite" or not os.path.exists(full):
            with open(full, "w", encoding="utf-8") as f:
                f.write(text)
        elif mode == "append":
            with open(full, "a", encoding="utf-8") as f:
                f.write(text)
        elif mode == "prepend":
            with open(full, encoding="utf-8") as f:
                existing = f.read()
            with open(full, "w", encoding="utf-8") as f:
                f.write(text + existing)
        else:
            raise ValueError(f"Unknown write mode: {mode!r}. Use overwrite, append, or prepend.")

    # ── Patch ─────────────────────────────────────────────────────────────────

    def patch_note(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> dict[str, Any]:
        full = self._resolve(path)
        self._check_allowed(path, full)

        with open(full, encoding="utf-8") as f:
            content = f.read()

        count = content.count(old_string)
        if count == 0:
            return {"success": False, "path": path, "message": "String not found in note", "matchCount": 0}
        if count > 1 and not replace_all:
            return {
                "success": False,
                "path": path,
                "message": (
                    f"Found {count} occurrences. Set replace_all=true to replace all, "
                    "or provide more context to make the match unique."
                ),
                "matchCount": count,
            }

        replaced = count if replace_all else 1
        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
        with open(full, "w", encoding="utf-8") as f:
            f.write(new_content)

        return {"success": True, "path": path, "message": f"Replaced {replaced} occurrence(s)", "matchCount": count}

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_note(self, path: str, confirm_path: str) -> dict[str, Any]:
        if path.strip() != confirm_path.strip():
            return {"success": False, "path": path, "message": "Confirmation path does not match — deletion aborted."}

        full = self._resolve(path)
        self._check_allowed(path, full)

        if not os.path.exists(full):
            return {"success": False, "path": path, "message": "Note not found"}

        os.unlink(full)
        return {"success": True, "path": path, "message": "Note deleted"}

    # ── List directory ────────────────────────────────────────────────────────

    def list_directory(self, path: str = "") -> dict[str, list[str]]:
        full = self._resolve(path or "")
        if not os.path.isdir(full):
            raise NotADirectoryError(f"Not a directory: {path!r}")

        dirs: list[str] = []
        files: list[str] = []

        try:
            entries = sorted(os.scandir(full), key=lambda e: e.name.lower())
        except OSError as exc:
            raise OSError(f"Cannot read directory: {path!r}") from exc

        for entry in entries:
            rel = self._to_rel(entry.path)
            if entry.is_dir(follow_symlinks=False):
                if self.path_filter.is_allowed_for_listing(rel):
                    dirs.append(entry.name)
            elif entry.is_file():
                if self.path_filter.is_allowed_for_listing(rel):
                    files.append(entry.name)

        return {"directories": dirs, "files": files}

    # ── Move ──────────────────────────────────────────────────────────────────

    def move_note(self, old_path: str, new_path: str, overwrite: bool = False) -> dict[str, Any]:
        old_full = self._resolve(old_path)
        new_full = self._resolve(new_path)

        if not os.path.exists(old_full):
            return {"success": False, "oldPath": old_path, "newPath": new_path, "message": "Source note not found"}
        if os.path.exists(new_full) and not overwrite:
            return {"success": False, "oldPath": old_path, "newPath": new_path, "message": "Destination already exists. Use overwrite=true to overwrite."}

        os.makedirs(os.path.dirname(new_full), exist_ok=True)
        shutil.move(old_full, new_full)
        return {"success": True, "oldPath": old_path, "newPath": new_path, "message": "Note moved successfully"}

    def move_file(
        self,
        old_path: str,
        new_path: str,
        confirm_old: str,
        confirm_new: str,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        if old_path.strip() != confirm_old.strip() or new_path.strip() != confirm_new.strip():
            return {
                "success": False,
                "oldPath": old_path,
                "newPath": new_path,
                "message": "Confirmation paths do not match — move aborted.",
            }
        return self.move_note(old_path, new_path, overwrite)

    # ── Batch read ────────────────────────────────────────────────────────────

    def read_multiple_notes(
        self,
        paths: list[str],
        include_content: bool = True,
        include_frontmatter: bool = True,
    ) -> dict[str, list]:
        if len(paths) > 10:
            raise ValueError("Maximum 10 notes per batch read")

        successful: list[dict] = []
        failed: list[dict] = []

        for path in paths:
            try:
                note = self.read_note(path)
                result: dict[str, Any] = {"path": path, "obsidianUri": _obsidian_uri(self.vault_path, path)}
                if include_frontmatter:
                    result["frontmatter"] = note["frontmatter"]
                if include_content:
                    result["content"] = note["content"]
                successful.append(result)
            except Exception as exc:
                failed.append({"path": path, "error": str(exc)})

        return {"successful": successful, "failed": failed}

    # ── Frontmatter ───────────────────────────────────────────────────────────

    def update_frontmatter(self, path: str, updates: dict, merge: bool = True) -> None:
        full = self._resolve(path)
        self._check_allowed(path, full)
        with open(full, encoding="utf-8") as f:
            content = f.read()
        new_content = self.fm.update(content, updates, merge=merge)
        with open(full, "w", encoding="utf-8") as f:
            f.write(new_content)

    def get_notes_info(self, paths: list[str]) -> list[dict]:
        results: list[dict] = []
        for path in paths:
            try:
                full = self._resolve(path)
                self._check_allowed(path, full)
                st = os.stat(full)
                with open(full, encoding="utf-8") as f:
                    head = f.read(10)
                results.append({
                    "path": path,
                    "size": st.st_size,
                    "modified": int(st.st_mtime * 1000),
                    "hasFrontmatter": head.startswith("---"),
                    "obsidianUri": _obsidian_uri(self.vault_path, path),
                })
            except Exception as exc:
                results.append({"path": path, "error": str(exc)})
        return results

    # ── Tags ──────────────────────────────────────────────────────────────────

    def manage_tags(
        self, path: str, operation: str, tags: list[str] | None = None
    ) -> dict[str, Any]:
        full = self._resolve(path)
        self._check_allowed(path, full)

        with open(full, encoding="utf-8") as f:
            content = f.read()

        meta, body = self.fm.parse(content)

        # Build current tag list from frontmatter + inline #tags
        fm_tags = meta.get("tags", [])
        if isinstance(fm_tags, str):
            fm_tags = [fm_tags]
        elif not isinstance(fm_tags, list):
            fm_tags = []

        inline = re.findall(r"(?<![#\w])#([a-zA-Z0-9_-]+)", body)
        current = list(dict.fromkeys(fm_tags + inline))  # deduplicate, preserve order

        if operation == "list":
            return {"path": path, "operation": "list", "tags": current, "success": True}

        if operation not in ("add", "remove"):
            raise ValueError(f"Unknown operation: {operation!r}. Use add, remove, or list.")

        if not tags:
            raise ValueError("tags parameter is required for add/remove operations")

        if operation == "add":
            new_tags = list(fm_tags)
            for tag in tags:
                if tag not in new_tags:
                    new_tags.append(tag)
        else:  # remove
            new_tags = [t for t in fm_tags if t not in tags]

        if new_tags:
            meta["tags"] = new_tags
        elif "tags" in meta:
            del meta["tags"]

        new_content = self.fm.stringify(meta, body)
        with open(full, "w", encoding="utf-8") as f:
            f.write(new_content)

        verb = "added" if operation == "add" else "removed"
        return {"path": path, "operation": operation, "tags": new_tags, "success": True, "message": f"Tags {verb}"}

    # ── Vault stats ───────────────────────────────────────────────────────────

    def get_vault_stats(self, recent_count: int = 5) -> dict[str, Any]:
        recent_count = min(recent_count, 20)
        total_notes = 0
        total_folders = 0
        total_size = 0
        all_recent: list[dict] = []

        for root, dirs, files in os.walk(self.vault_path):
            rel_root = self._to_rel(root)

            # Prune ignored directories in-place
            dirs[:] = [
                d for d in dirs
                if self.path_filter.is_allowed_for_listing(
                    (rel_root + "/" + d).lstrip("./")
                )
            ]

            if root != self.vault_path:
                total_folders += 1

            for fname in files:
                fpath = os.path.join(root, fname)
                frel = self._to_rel(fpath)
                if not self.path_filter.is_allowed(frel):
                    continue
                try:
                    st = os.stat(fpath)
                    total_notes += 1
                    total_size += st.st_size
                    all_recent.append({"path": frel, "modified": int(st.st_mtime * 1000)})
                except OSError:
                    pass

        all_recent.sort(key=lambda x: x["modified"], reverse=True)

        return {
            "totalNotes": total_notes,
            "totalFolders": total_folders,
            "totalSize": total_size,
            "recentlyModified": all_recent[:recent_count],
        }

    # ── List all tags ─────────────────────────────────────────────────────────

    def list_all_tags(self) -> list[dict[str, Any]]:
        tag_counts: dict[str, int] = {}
        inline_re = re.compile(r"(?:^|\s)#([a-zA-Z][a-zA-Z0-9_/\-]*)", re.MULTILINE)

        for root, dirs, files in os.walk(self.vault_path):
            rel_root = self._to_rel(root)
            dirs[:] = [
                d for d in dirs
                if self.path_filter.is_allowed_for_listing(
                    (rel_root + "/" + d).lstrip("./")
                )
            ]

            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                frel = self._to_rel(fpath)
                if not self.path_filter.is_allowed(frel):
                    continue
                try:
                    with open(fpath, encoding="utf-8") as f:
                        content = f.read()
                except OSError:
                    continue

                meta, body = self.fm.parse(content)

                # Frontmatter tags
                fm_tags = meta.get("tags", [])
                if isinstance(fm_tags, str):
                    fm_tags = [fm_tags]
                elif not isinstance(fm_tags, list):
                    fm_tags = []
                for tag in fm_tags:
                    if isinstance(tag, str) and tag.strip():
                        norm = tag.strip().lower()
                        tag_counts[norm] = tag_counts.get(norm, 0) + 1

                # Inline #tags from body
                for m in inline_re.finditer(body):
                    norm = m.group(1).lower()
                    tag_counts[norm] = tag_counts.get(norm, 0) + 1

        return sorted(
            [{"tag": t, "count": c} for t, c in tag_counts.items()],
            key=lambda x: (-x["count"], x["tag"]),
        )
