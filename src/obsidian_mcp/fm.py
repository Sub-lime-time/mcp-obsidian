"""Frontmatter parsing and stringification using python-frontmatter + PyYAML.

Uses a custom YAML handler that:
- Preserves key insertion order (sort_keys=False)
- Allows unicode
- Serializes dates as YYYY-MM-DD (PyYAML SafeDumper default)
"""
from __future__ import annotations

import yaml
import frontmatter as _fm
from frontmatter.default_handlers import YAMLHandler


class _ObsidianHandler(YAMLHandler):
    """YAML handler that preserves key order and allows unicode."""

    def export(self, metadata: dict, **kwargs) -> str:  # type: ignore[override]
        return yaml.dump(
            metadata,
            Dumper=yaml.SafeDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        ).strip()


_HANDLER = _ObsidianHandler()


class FrontmatterHandler:
    def parse(self, content: str) -> tuple[dict, str]:
        """Return (metadata_dict, body_string) for any note content."""
        try:
            post = _fm.loads(content, handler=_HANDLER)
            return dict(post.metadata), post.content
        except Exception:
            return {}, content

    def stringify(self, metadata: dict, body: str) -> str:
        """Combine metadata and body into a note string with YAML front matter."""
        if not metadata:
            return body
        try:
            post = _fm.Post(body, handler=_HANDLER, **metadata)
            return _fm.dumps(post, handler=_HANDLER)
        except Exception as e:
            raise ValueError(f"Failed to stringify frontmatter: {e}") from e

    def update(self, content: str, updates: dict, merge: bool = True) -> str:
        """Update frontmatter fields in-place, preserving body content."""
        metadata, body = self.parse(content)
        if merge:
            metadata.update(updates)
        else:
            metadata = dict(updates)
        return self.stringify(metadata, body)
