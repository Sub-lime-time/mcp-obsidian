"""Frontmatter parsing and stringification using python-frontmatter + PyYAML.

Uses a custom YAML handler that:
- Preserves key insertion order (sort_keys=False)
- Allows unicode
- Serializes dates as YYYY-MM-DD (PyYAML SafeDumper default)
- Removes sexagesimal int resolution (e.g. "6:30" stays "6:30", not 390)
"""
from __future__ import annotations

import re

import yaml
import frontmatter as _fm
from frontmatter.default_handlers import YAMLHandler


# Custom loader: SafeLoader minus YAML 1.1 sexagesimal int resolution.
# PyYAML parses unquoted "6:30" as integer 390 — this constructor overrides that.
class _ObsidianLoader(yaml.SafeLoader):
    pass


_SEXAGESIMAL_RE = re.compile(r"^[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+$")
_orig_int = yaml.SafeLoader.yaml_constructors["tag:yaml.org,2002:int"]


def _int_no_sexagesimal(loader: yaml.SafeLoader, node: yaml.ScalarNode) -> int | str:
    value = loader.construct_scalar(node)
    if _SEXAGESIMAL_RE.match(value):
        return value
    return _orig_int(loader, node)


_ObsidianLoader.add_constructor("tag:yaml.org,2002:int", _int_no_sexagesimal)


class _ObsidianHandler(YAMLHandler):
    """YAML handler that preserves key order, allows unicode, and skips sexagesimal."""

    def load(self, fm: str, **kwargs) -> dict:
        return yaml.load(fm, Loader=_ObsidianLoader) or {}

    def export(self, metadata: dict, **kwargs) -> str:  # type: ignore[override]
        return yaml.dump(
            metadata,
            Dumper=yaml.SafeDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        ).strip()


_HANDLER = _ObsidianHandler()

# Frontmatter only exists when the note *starts* with a fence. Passing an explicit
# handler to frontmatter.loads() skips its own start-of-file check, and the handler's
# split() treats any '---' line as a fence — so a note with no frontmatter but '---'
# dividers would lose everything above the second divider (issue #4).
_LEADING_FENCE_RE = re.compile(r"\A---[ \t]*\r?\n")


class FrontmatterHandler:
    def parse(self, content: str, strict: bool = False) -> tuple[dict, str]:
        """Return (metadata_dict, body_string) for any note content.

        Unparseable frontmatter falls back to ({}, content) for reads. Writers pass
        strict=True: the fallback body still holds the broken block, so writing new
        frontmatter over it would leave two stacked blocks (issue #6).
        """
        if not _LEADING_FENCE_RE.match(content):
            return {}, content
        try:
            post = _fm.loads(content, handler=_HANDLER)
            return dict(post.metadata), post.content
        except Exception as e:
            if strict:
                raise ValueError(
                    f"Existing frontmatter is not valid YAML ({e}). "
                    "Fix it by hand before updating; refusing to write a second block."
                ) from e
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
        metadata, body = self.parse(content, strict=True)
        if merge:
            metadata.update(updates)
        else:
            metadata = dict(updates)
        return self.stringify(metadata, body)
