"""Regression tests for frontmatter parsing on write paths.

#4: a note with no frontmatter but '---' dividers lost everything above the second
divider on update_frontmatter / manage_tags.
#6: a note with invalid frontmatter got a second block stacked on top of it.
"""
import pytest

from obsidian_mcp.filesystem import FileSystemService
from obsidian_mcp.fm import FrontmatterHandler
from obsidian_mcp.pathfilter import PathFilter

NO_FM_WITH_DIVIDERS = (
    "# Title\n\nIntro line\n\n---\n\n## Section\nBody text\n\n---\n\nTail\n"
)
WITH_FM = "---\ntype: reference\ntags:\n- a\n---\n\n# Title\n\nBody\n\n---\n\nTail\n"

fm = FrontmatterHandler()


def test_parse_no_frontmatter_keeps_whole_body():
    meta, body = fm.parse(NO_FM_WITH_DIVIDERS)
    assert meta == {}
    assert body == NO_FM_WITH_DIVIDERS


def test_parse_with_frontmatter_still_works():
    meta, body = fm.parse(WITH_FM)
    assert meta == {"type": "reference", "tags": ["a"]}
    assert body.startswith("# Title")
    assert body.rstrip().endswith("Tail")


def test_update_no_frontmatter_prepends_block():
    out = fm.update(NO_FM_WITH_DIVIDERS, {"type": "reference"})
    assert out.startswith("---\ntype: reference\n---\n")
    assert NO_FM_WITH_DIVIDERS.strip() in out


def _vault(tmp_path, name, text):
    (tmp_path / name).write_text(text, encoding="utf-8")
    return FileSystemService(str(tmp_path), PathFilter())


def test_update_frontmatter_tool_preserves_body(tmp_path):
    svc = _vault(tmp_path, "note.md", NO_FM_WITH_DIVIDERS)
    svc.update_frontmatter("note.md", {"type": "reference"})
    out = (tmp_path / "note.md").read_text(encoding="utf-8")
    assert "# Title" in out and "## Section" in out and "Tail" in out


def test_manage_tags_preserves_body(tmp_path):
    svc = _vault(tmp_path, "note.md", NO_FM_WITH_DIVIDERS)
    svc.manage_tags("note.md", "add", ["network/wifi"])
    out = (tmp_path / "note.md").read_text(encoding="utf-8")
    assert out.startswith("---\ntags:\n- network/wifi\n---\n")
    assert "# Title" in out and "## Section" in out and "Tail" in out


def test_read_note_returns_full_body(tmp_path):
    svc = _vault(tmp_path, "note.md", NO_FM_WITH_DIVIDERS)
    note = svc.read_note("note.md")
    assert note["frontmatter"] == {}
    assert note["content"] == NO_FM_WITH_DIVIDERS


# ── Invalid existing frontmatter (issue #6) ──────────────────────────────────
# Writers used to stack a new block on top of a block that failed to parse.

INVALID_FM = '---\ntype: process\ntrigger: "a" / "b"\n---\n\n# Title\n\nBody\n'


def test_parse_invalid_frontmatter_lenient_for_reads():
    assert fm.parse(INVALID_FM) == ({}, INVALID_FM)


def test_update_invalid_frontmatter_refuses():
    with pytest.raises(ValueError, match="not valid YAML"):
        fm.update(INVALID_FM, {"updated": "2026-10-13"})


def test_update_frontmatter_tool_leaves_invalid_note_untouched(tmp_path):
    svc = _vault(tmp_path, "note.md", INVALID_FM)
    with pytest.raises(ValueError):
        svc.update_frontmatter("note.md", {"updated": "2026-10-13"})
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == INVALID_FM


def test_manage_tags_add_refuses_but_list_works(tmp_path):
    svc = _vault(tmp_path, "note.md", INVALID_FM)
    with pytest.raises(ValueError):
        svc.manage_tags("note.md", "add", ["x"])
    assert (tmp_path / "note.md").read_text(encoding="utf-8") == INVALID_FM
    assert svc.manage_tags("note.md", "list")["success"] is True
