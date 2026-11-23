"""Link resolution, link-aware moves, and the link report tools.

Fixtures use the link shapes found in the real vaults (survey 2026-11-23):
bare names, folder paths, `.md` suffixes, suffix paths, #heading / #^block,
|alias, \\| aliases inside tables, embeds, quoted frontmatter links, and
markdown links with %20.
"""
from pathlib import Path

import pytest

from obsidian_mcp import links
from obsidian_mcp.filesystem import FileSystemService
from obsidian_mcp.pathfilter import PathFilter


def make_vault(tmp_path: Path, files: dict[str, str]) -> FileSystemService:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return FileSystemService(str(tmp_path), PathFilter(), move_verify_delay=0)


def read(tmp_path: Path, rel: str) -> str:
    return (tmp_path / rel).read_text(encoding="utf-8")


# ── Resolution ────────────────────────────────────────────────────────────────

INDEX = links.LinkIndex([
    "01_Network/IPV6.md",
    "02_Homelab_Servers/HQ/hal.hq.802ski.com.md",
    "04_Automation/Matter.md",
    "02_Homelab_Servers/Services/Home Assistant/Matter.md",
    "03_Device_management/Network/UniFi UDR - LA.md",
    "Attachments/Pasted image 1.png",
    "cert-manager.sh.md",
])


@pytest.mark.parametrize("link,source,expected", [
    ("IPV6", "x.md", "01_Network/IPV6.md"),
    ("ipv6", "x.md", "01_Network/IPV6.md"),                       # case-insensitive
    ("01_Network/IPV6.md", "x.md", "01_Network/IPV6.md"),          # .md suffix
    ("hal.hq.802ski.com", "x.md", "02_Homelab_Servers/HQ/hal.hq.802ski.com.md"),  # dots in name
    ("Network/UniFi UDR - LA.md", "x.md", "03_Device_management/Network/UniFi UDR - LA.md"),  # suffix path
    ("Pasted image 1.png", "x.md", "Attachments/Pasted image 1.png"),
    ("cert-manager.sh", "x.md", "cert-manager.sh.md"),
    ("Nope", "x.md", None),
    ("Matter", "04_Automation/Thread.md", "04_Automation/Matter.md"),  # same folder wins
])
def test_resolve(link, source, expected):
    assert INDEX.resolve(link, source).target == expected


def test_resolve_ambiguous_flags_shortest_path():
    res = INDEX.resolve("Matter", "x.md")
    assert res.target == "04_Automation/Matter.md"
    assert res.ambiguous


def test_relative_resolution():
    idx = links.LinkIndex(["a/b/note.md", "a/other.md"])
    assert idx.resolve("../other", "a/b/note.md").target == "a/other.md"
    assert idx.resolve("./note", "a/b/x.md").target == "a/b/note.md"
    assert idx.resolve("../../../escape", "a/b/note.md").target is None


# ── Parsing ───────────────────────────────────────────────────────────────────


def test_parse_skips_code():
    text = (
        "[[Real]]\n"
        "```\n[[InFence]]\n```\n"
        "Inline `[[InCode]]` and ~~~ not a fence\n"
        "~~~md\n[[Tilde]]\n~~~\n"
        "[[After]]\n"
    )
    assert [l.target for l in links.parse_links(text)] == ["Real", "After"]


def test_parse_parts_and_lines():
    text = "a\n| [[dir/Note#Head\\|Alias]] |\n![[img.png]]\n[x](Some%20Note.md#sec)\n[w](https://x.y)\n"
    ls = links.parse_links(text)
    assert [(l.target, l.subpath, l.rest, l.line) for l in ls] == [
        ("dir/Note", "#Head", "\\|Alias", 2),
        ("img.png", "", "", 3),
        ("Some Note.md", "#sec", "x", 4),
    ]
    assert ls[1].embed and ls[2].encoded


# ── Moves ─────────────────────────────────────────────────────────────────────

SHAPES = (
    "---\nrelated:\n  - '[[Old Name]]'\n  - '[[Area/Old Name|alias]]'\n---\n"
    "Bare [[Old Name]], path [[Area/Old Name]], ext [[Area/Old Name.md]]\n"
    "Heading [[Old Name#Setup]], block [[Area/Old Name#^abc123]], alias [[Old Name|the note]]\n"
    "| table | [[Area/Old Name\\|Old]] |\n"
    "Embed ![[Old Name]] and md [doc](Area/Old%20Name.md#Setup)\n"
    "```\n[[Old Name]] stays in code\n```\n"
    "Ghost [[Never Existed]] and other [[Other]]\n"
)


def test_rename_rewrites_every_shape(tmp_path):
    svc = make_vault(tmp_path, {
        "Area/Old Name.md": "# Old\n",
        "Other.md": "x",
        "Links.md": SHAPES,
    })
    r = svc.move_note("Area/Old Name.md", "Area/New Name.md")
    assert r["success"] and r["filesUpdated"] == ["Links.md"]
    out = read(tmp_path, "Links.md")
    assert out == (
        "---\nrelated:\n  - '[[New Name]]'\n  - '[[Area/New Name|alias]]'\n---\n"
        "Bare [[New Name]], path [[Area/New Name]], ext [[Area/New Name.md]]\n"
        "Heading [[New Name#Setup]], block [[Area/New Name#^abc123]], alias [[New Name|the note]]\n"
        "| table | [[Area/New Name\\|Old]] |\n"
        "Embed ![[New Name]] and md [doc](Area/New%20Name.md#Setup)\n"
        "```\n[[Old Name]] stays in code\n```\n"
        "Ghost [[Never Existed]] and other [[Other]]\n"
    )
    assert r["linksUpdated"] == 11


def test_folder_move_keeps_bare_links_and_fixes_paths(tmp_path):
    svc = make_vault(tmp_path, {
        "88_Incoming/Stub.md": "x",
        "Hub.md": "[[Stub]] and [[88_Incoming/Stub]] and [[88_Incoming/Stub|s]]\n",
    })
    r = svc.move_note("88_Incoming/Stub.md", "02_Homelab_Servers/Stub.md")
    assert r["linksUpdated"] == 2
    assert read(tmp_path, "Hub.md") == (
        "[[Stub]] and [[02_Homelab_Servers/Stub]] and [[02_Homelab_Servers/Stub|s]]\n"
    )


def test_rename_into_name_collision_uses_full_path(tmp_path):
    svc = make_vault(tmp_path, {
        "a/Thing.md": "x",
        "b/Matter.md": "y",
        "Hub.md": "[[Thing]]\n",
    })
    svc.move_note("a/Thing.md", "a/Matter.md")
    # [[Matter]] would be ambiguous, so the link gets the path.
    assert read(tmp_path, "Hub.md") == "[[a/Matter]]\n"


def test_moved_notes_own_relative_links(tmp_path):
    svc = make_vault(tmp_path, {
        "a/b/note.md": "[[../sib]] [img](pic.png) [[Abs/Target]]\n",
        "a/sib.md": "x",
        "a/b/pic.png": "png",
        "Abs/Target.md": "t",
        "a/b/pic2/x.md": "",
    })
    svc.move_note("a/b/note.md", "z/note.md")
    # pic.png is unique in the vault, so it still resolves by name: untouched.
    assert read(tmp_path, "z/note.md") == "[[../a/sib]] [img](pic.png) [[Abs/Target]]\n"


def test_folder_move_rewrites_contents(tmp_path):
    svc = make_vault(tmp_path, {
        "Old/One.md": "[[Old/Two]]\n",
        "Old/Two.md": "x",
        "Hub.md": "[[Old/One]] [[One]]\n",
    })
    r = svc.move_note("Old", "New")
    assert r["success"]
    assert read(tmp_path, "Hub.md") == "[[New/One]] [[One]]\n"
    assert read(tmp_path, "New/One.md") == "[[New/Two]]\n"


def test_dry_run_changes_nothing(tmp_path):
    svc = make_vault(tmp_path, {"A.md": "x", "Hub.md": "[[A]]\n"})
    r = svc.move_note("A.md", "B.md", dry_run=True)
    assert r["dryRun"] and r["changes"] == [
        {"file": "Hub.md", "line": 1, "old": "[[A]]", "new": "[[B]]"}
    ]
    assert (tmp_path / "A.md").exists() and not (tmp_path / "B.md").exists()
    assert read(tmp_path, "Hub.md") == "[[A]]\n"


def test_update_links_false_is_plain_move(tmp_path):
    svc = make_vault(tmp_path, {"A.md": "x", "Hub.md": "[[A]]\n"})
    r = svc.move_note("A.md", "B.md", update_links=False)
    assert r["success"] and "linksUpdated" not in r
    assert read(tmp_path, "Hub.md") == "[[A]]\n"


def test_failed_move_touches_no_links(tmp_path, monkeypatch):
    svc = make_vault(tmp_path, {"A.md": "x", "Hub.md": "[[A]]\n"})
    # Simulate a sync client undoing the move: shutil.move does nothing.
    monkeypatch.setattr("obsidian_mcp.filesystem.shutil.move", lambda *a, **k: None)
    r = svc.move_note("A.md", "B.md")
    assert not r["success"]
    assert read(tmp_path, "Hub.md") == "[[A]]\n"


def test_writes_lf_and_ignores_obsidian_dir(tmp_path):
    svc = make_vault(tmp_path, {
        "A.md": "x",
        ".obsidian/workspace.md": "[[A]]",
    })
    (tmp_path / "Hub.md").write_bytes(b"[[A]]\r\nline\r\n")
    svc.move_note("A.md", "B.md")
    assert (tmp_path / "Hub.md").read_bytes() == b"[[B]]\nline\n"
    assert read(tmp_path, ".obsidian/workspace.md") == "[[A]]"


def test_trash_is_not_rewritten_or_audited(tmp_path):
    svc = make_vault(tmp_path, {"A.md": "x", ".trash/Old.md": "[[A]]", "Hub.md": "[[A]]"})
    r = svc.move_note("A.md", "B.md")
    assert r["filesUpdated"] == ["Hub.md"]
    assert read(tmp_path, ".trash/Old.md") == "[[A]]"
    assert ".trash/Old.md" not in svc.audit_links()["orphans"]


def test_folder_into_itself_refused(tmp_path):
    svc = make_vault(tmp_path, {"Dir/A.md": "x"})
    r = svc.move_note("Dir", "Dir/Sub")
    assert not r["success"] and "into itself" in r["message"]


def test_traversal_still_refused(tmp_path):
    svc = make_vault(tmp_path, {"A.md": "x"})
    with pytest.raises(PermissionError):
        svc.move_note("A.md", "../outside.md")


# ── Report tools ──────────────────────────────────────────────────────────────


def test_get_note_links(tmp_path):
    svc = make_vault(tmp_path, {
        "Svc/Graylog.md": "[[graylog-hq1]] [[Missing]] [[#Self]]\n",
        "Servers/graylog-hq1.md": "Runs [[Graylog]]\n",
        "Hub.md": "a\n[[Svc/Graylog|GL]]\n",
    })
    r = svc.get_note_links("Svc/Graylog.md")
    assert [o["target"] for o in r["outgoing"]] == ["Servers/graylog-hq1.md", None]
    assert [u["link"] for u in r["unresolved"]] == ["[[Missing]]"]
    assert r["backlinkSources"] == ["Hub.md", "Servers/graylog-hq1.md"]
    assert {"source": "Hub.md", "line": 2, "link": "[[Svc/Graylog|GL]]"} in r["backlinks"]


def test_audit_links(tmp_path):
    svc = make_vault(tmp_path, {
        "A.md": "[[Ghost]] [[Ghost]] [[B]]",
        "B.md": "[[A]]",
        "Lonely.md": "[[Ghost2]]",
        "sub/C.md": "",
    })
    r = svc.audit_links()
    assert [u["target"] for u in r["unresolved"]] == ["Ghost", "Ghost2"]
    assert r["unresolved"][0]["count"] == 2
    assert r["orphans"] == ["Lonely.md", "sub/C.md"]
    assert svc.audit_links("sub")["orphans"] == ["sub/C.md"]
