"""Vault-wide scans skip dot-folders, as Obsidian does.

The old prune built "./.obsidian" for root folders and lstrip("./") turned it
into "obsidian", so nothing at the root was pruned: get_vault_stats counted
.obsidian, .obsidian-windows, .trash and .stfolder as folders, and trashed
notes leaked into list_all_tags and search_notes.
"""
from obsidian_mcp.filesystem import FileSystemService
from obsidian_mcp.pathfilter import PathFilter
from obsidian_mcp.search import SearchService

FILES = {
    "Notes/A.md": "#live findme\n",
    "Notes/Sub/B.md": "x\n",
    ".obsidian/plugins/p/readme.md": "#plugin findme\n",
    ".obsidian-windows/plugins/p/readme.md": "#plugin findme\n",
    ".trash/Old.md": "#trashed findme\n",
    ".stfolder/.keep": "",
    "node_modules/pkg/x.md": "#dep\n",
}


def vault(tmp_path):
    for rel, text in FILES.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return FileSystemService(str(tmp_path), PathFilter())


def test_vault_stats_counts_only_real_folders(tmp_path):
    stats = vault(tmp_path).get_vault_stats(recent_count=20)
    assert stats["totalFolders"] == 2
    assert stats["totalNotes"] == 2
    assert sorted(r["path"] for r in stats["recentlyModified"]) == ["Notes/A.md", "Notes/Sub/B.md"]


def test_list_all_tags_ignores_dot_folders(tmp_path):
    tags = [t["tag"] for t in vault(tmp_path).list_all_tags()]
    assert tags == ["live"]


def test_search_ignores_dot_folders(tmp_path):
    vault(tmp_path)
    hits = SearchService(str(tmp_path), PathFilter()).search("findme", limit=20)
    assert [h["p"] for h in hits] == ["Notes/A.md"]


def test_explicit_trash_read_still_works(tmp_path):
    svc = vault(tmp_path)
    assert "trashed" in svc.read_note(".trash/Old.md")["content"]
