"""Link parsing, resolution, and rewrite planning for Obsidian vaults.

Obsidian: [[05_Projects/Development/MCP/obsidian-mcp-python]]
Repo: ~/repos/projects/mcp-obsidian/src/obsidian_mcp/links.py

Resolution approximates Obsidian's getFirstLinkpathDest without the app:
a link names a file by its path suffix (`[[Note]]`, `[[Folder/Note]]`,
`[[Note.md]]`), case-insensitively, with `.md` implied. When several files
match, the order is: exact path relative to the linking note, exact path from
the vault root, a match in the linking note's own folder, then the shortest
path (alphabetical as a tiebreak). Matches that fall through to that last rule
are reported as ambiguous, because Obsidian's own choice there may differ.

The rewrite rule after a move is deliberately conservative: a link is only
changed when, after the move, its existing text would no longer resolve to the
file it pointed at before. Links that still work keep their exact text.
"""
from __future__ import annotations

import os
import posixpath
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterator
from urllib.parse import quote, unquote

if TYPE_CHECKING:
    from .pathfilter import PathFilter

# Files whose text is scanned for links. Canvas and Base files store links in
# JSON / expressions and are not rewritten (reported as a limitation).
LINK_SOURCE_EXTENSIONS = (".md", ".markdown")

_WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
_MDLINK_RE = re.compile(
    r"(!?)\[([^\]\n]*)\]\((<[^>\n]+>|[^)\s]+)(\s+\"[^\"\n]*\")?\)"
)
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})", re.MULTILINE)
_INLINE_CODE_RE = re.compile(r"(`+)(?:(?!\1).)+?\1", re.DOTALL)


# ── Vault walking ─────────────────────────────────────────────────────────────


def iter_vault_files(vault_path: str, path_filter: "PathFilter") -> Iterator[str]:
    """Yield every vault-relative file path (POSIX separators), all types.

    Attachments are included because links can point at them. Like Obsidian,
    every dot-folder and dotfile (.obsidian, .trash, .git, .DS_Store) is
    skipped, as is anything the PathFilter ignores.
    """
    for root, dirs, files in os.walk(vault_path):
        rel_root = os.path.relpath(root, vault_path).replace("\\", "/")
        prefix = "" if rel_root == "." else rel_root + "/"
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and path_filter.is_allowed_for_listing(prefix + d)
        ]
        for name in files:
            rel = prefix + name
            if not name.startswith(".") and path_filter.is_allowed_for_listing(rel):
                yield rel


def _linkname(path: str) -> str:
    """The name a link uses for a file: its path with a `.md` suffix dropped."""
    return path[:-3] if path.lower().endswith(".md") else path


# ── Index + resolution ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Resolution:
    target: str | None
    ambiguous: bool = False


class LinkIndex:
    """Maps link text to vault files, for one snapshot of the file list."""

    def __init__(self, files: list[str]) -> None:
        self.files = sorted(set(files))
        self._lower = {f.lower(): f for f in self.files}
        self._by_last: dict[str, list[str]] = {}
        for f in self.files:
            last = _linkname(f).rsplit("/", 1)[-1].lower()
            self._by_last.setdefault(last, []).append(f)

    def _exact(self, path: str) -> str | None:
        p = path.lower()
        return self._lower.get(p) or self._lower.get(p + ".md")

    def resolve(self, linkpath: str, source: str) -> Resolution:
        lp = linkpath.strip().replace("\\", "/")
        if not lp:
            return Resolution(None)
        src_dir = posixpath.dirname(source)

        if lp.startswith(("./", "../")):
            joined = posixpath.normpath(posixpath.join(src_dir, lp))
            if joined.startswith(".."):
                return Resolution(None)
            return Resolution(self._exact(joined))

        lp = lp.lstrip("/")
        if src_dir:
            rel = self._exact(posixpath.normpath(posixpath.join(src_dir, lp)))
            if rel:
                return Resolution(rel)
        root = self._exact(lp)
        if root:
            return Resolution(root)

        want = _linkname(lp).lower()
        last = want.rsplit("/", 1)[-1]
        cands = [
            f for f in self._by_last.get(last, [])
            if (n := _linkname(f).lower()) == want or n.endswith("/" + want)
        ]
        if not cands:
            return Resolution(None)
        if len(cands) == 1:
            return Resolution(cands[0])
        same_dir = [c for c in cands if posixpath.dirname(c) == src_dir]
        if len(same_dir) == 1:
            return Resolution(same_dir[0])
        cands.sort(key=lambda c: (c.count("/"), len(c), c))
        return Resolution(cands[0], ambiguous=True)


# ── Parsing ───────────────────────────────────────────────────────────────────


@dataclass
class Link:
    kind: str          # "wikilink" | "markdown"
    start: int         # offset of the whole link in the text
    end: int
    raw: str           # full original text, e.g. "![[a/b#h\\|x]]"
    embed: bool
    target: str        # path part as written (decoded for markdown links)
    subpath: str       # "#heading" / "#^block" including the '#', or ""
    rest: str          # wikilink: alias part incl. separator; markdown: text
    angle: bool = False   # markdown: <...> destination
    encoded: bool = False  # markdown: destination used %-encoding
    title: str = ""       # markdown: optional "title"
    line: int = 0         # 1-indexed, filled in by parse_links


def _code_ranges(text: str) -> list[tuple[int, int]]:
    """Offsets covered by fenced code blocks and inline code spans."""
    ranges: list[tuple[int, int]] = []
    fence: str | None = None
    fence_start = 0
    for m in _FENCE_RE.finditer(text):
        marker = m.group(1)
        if fence is None:
            fence, fence_start = marker, m.start()
        elif marker[0] == fence[0] and len(marker) >= len(fence):
            line_end = text.find("\n", m.end())
            end = len(text) if line_end == -1 else line_end
            ranges.append((fence_start, end))
            fence = None
    if fence is not None:
        ranges.append((fence_start, len(text)))

    def in_fence(i: int) -> bool:
        return any(s <= i < e for s, e in ranges)

    inline = [
        (m.start(), m.end())
        for m in _INLINE_CODE_RE.finditer(text)
        if not in_fence(m.start()) and "\n\n" not in m.group(0)
    ]
    return ranges + inline


def _split_wikilink(inner: str) -> tuple[str, str, str]:
    """Split `target#sub|alias` (or `target#sub\\|alias`) into its parts."""
    pipe = inner.find("|")
    if pipe == -1:
        head, rest = inner, ""
    elif pipe > 0 and inner[pipe - 1] == "\\":
        head, rest = inner[: pipe - 1], inner[pipe - 1:]
    else:
        head, rest = inner[:pipe], inner[pipe:]
    hash_ = head.find("#")
    if hash_ == -1:
        return head, "", rest
    return head[:hash_], head[hash_:], rest


def parse_links(text: str) -> list[Link]:
    """Every internal link in a note, skipping code. Sorted by offset."""
    code = _code_ranges(text)

    def in_code(i: int) -> bool:
        return any(s <= i < e for s, e in code)

    links: list[Link] = []
    for m in _WIKILINK_RE.finditer(text):
        if in_code(m.start()):
            continue
        target, sub, rest = _split_wikilink(m.group(2))
        links.append(Link("wikilink", m.start(), m.end(), m.group(0), bool(m.group(1)),
                          target, sub, rest))

    for m in _MDLINK_RE.finditer(text):
        if in_code(m.start()):
            continue
        dest = m.group(3)
        angle = dest.startswith("<")
        if angle:
            dest = dest[1:-1]
        if _SCHEME_RE.match(dest) or dest.startswith("#"):
            continue
        path, _, frag = dest.partition("#")
        decoded = unquote(path)
        links.append(Link("markdown", m.start(), m.end(), m.group(0), bool(m.group(1)),
                          decoded, ("#" + frag) if frag else "", m.group(2),
                          angle=angle, encoded=decoded != path, title=m.group(4) or ""))

    links.sort(key=lambda l: l.start)
    # Line numbers (1-indexed) in a single pass.
    line, last = 1, 0
    for l in links:
        line += text.count("\n", last, l.start)
        last = l.start
        l.line = line
    return links


# ── Rendering ─────────────────────────────────────────────────────────────────


def _render(link: Link, new_target: str) -> str:
    bang = "!" if link.embed else ""
    if link.kind == "wikilink":
        return f"{bang}[[{new_target}{link.subpath}{link.rest}]]"
    if link.angle:
        dest = f"<{new_target}{link.subpath}>"
    elif link.encoded or " " in new_target:
        dest = quote(new_target, safe="/") + link.subpath
    else:
        dest = new_target + link.subpath
    return f"{bang}[{link.rest}]({dest}{link.title})"


def _candidates(link: Link, target: str, source: str) -> list[str]:
    """Link texts for `target` in the style of `link`, most preferred first."""
    # Markdown links always carry the extension; wikilinks keep `.md` only if
    # the original did.
    keep_ext = link.kind == "markdown" or link.target.lower().endswith(".md")
    full = target if keep_ext else _linkname(target)
    as_written = link.target.replace("\\", "/")

    if link.kind == "markdown" or as_written.startswith(("./", "../")):
        rel = posixpath.relpath(full, posixpath.dirname(source) or ".")
        if as_written.startswith(("./", "../")):
            if not rel.startswith("../"):
                rel = "./" + rel
            return [rel, full]
        return [full, rel]
    if "/" in as_written:
        return [full]
    return [full.rsplit("/", 1)[-1], full]


# ── Planning ──────────────────────────────────────────────────────────────────


@dataclass
class Rewrite:
    source: str      # note path before the move
    new_source: str  # note path after the move
    line: int
    old: str
    new: str
    start: int
    end: int


@dataclass
class MovePlan:
    rewrites: dict[str, list[Rewrite]]      # keyed by note path before the move
    contents: dict[str, str]                # text the plan was computed from
    ambiguous: list[dict]
    unrewritable: list[dict]

    @property
    def link_count(self) -> int:
        return sum(len(v) for v in self.rewrites.values())


def make_remap(old: str, new: str) -> Callable[[str], str]:
    old_l = old.lower()

    def remap(p: str) -> str:
        pl = p.lower()
        if pl == old_l:
            return new
        if pl.startswith(old_l + "/"):
            return new + p[len(old):]
        return p

    return remap


def read_text(vault_path: str, rel: str) -> str | None:
    try:
        with open(os.path.join(vault_path, rel), encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def plan_move(vault_path: str, files: list[str], old: str, new: str) -> MovePlan:
    """Work out which links break if `old` (a file or folder) becomes `new`."""
    remap = make_remap(old, new)
    before = LinkIndex(files)
    after = LinkIndex([remap(f) for f in files])

    rewrites: dict[str, list[Rewrite]] = {}
    contents: dict[str, str] = {}
    ambiguous: list[dict] = []
    unrewritable: list[dict] = []

    for note in before.files:
        if not note.lower().endswith(LINK_SOURCE_EXTENSIONS):
            continue
        text = read_text(vault_path, note)
        if text is None or ("[[" not in text and "](" not in text):
            continue
        new_note = remap(note)
        for link in parse_links(text):
            if not link.target.strip():
                continue  # [[#heading]]: points at the note itself
            res = before.resolve(link.target, note)
            if res.target is None:
                continue  # unresolved before the move: leave ghost links alone
            want = remap(res.target)
            now = after.resolve(link.target, new_note)
            # Still works, and the move didn't make it newly ambiguous (where
            # only our tiebreak, not Obsidian's, would pick the right file).
            if now.target == want and (not now.ambiguous or res.ambiguous):
                continue
            if res.ambiguous:
                ambiguous.append({"source": note, "line": link.line, "link": link.raw,
                                  "assumedTarget": res.target})
            for cand in _candidates(link, want, new_note):
                cres = after.resolve(cand, new_note)
                if cres.target == want and not cres.ambiguous:
                    rw = Rewrite(note, new_note, link.line, link.raw, _render(link, cand),
                                 link.start, link.end)
                    rewrites.setdefault(note, []).append(rw)
                    contents[note] = text
                    break
            else:
                unrewritable.append({"source": note, "line": link.line, "link": link.raw,
                                     "target": want})
    return MovePlan(rewrites, contents, ambiguous, unrewritable)


def apply_rewrites(text: str, rewrites: list[Rewrite]) -> str:
    out = text
    for rw in sorted(rewrites, key=lambda r: r.start, reverse=True):
        assert out[rw.start:rw.end] == rw.old, "plan offsets no longer match"
        out = out[: rw.start] + rw.new + out[rw.end:]
    return out


# ── Reporting (get_note_links / audit_links) ──────────────────────────────────


def _note_files(index: LinkIndex) -> list[str]:
    return [f for f in index.files if f.lower().endswith(LINK_SOURCE_EXTENSIONS)]


def scan_vault(vault_path: str, index: LinkIndex) -> Iterator[tuple[str, Link, Resolution]]:
    for note in _note_files(index):
        text = read_text(vault_path, note)
        if text is None:
            continue
        for link in parse_links(text):
            if not link.target.strip():
                continue
            yield note, link, index.resolve(link.target, note)


def note_links(vault_path: str, index: LinkIndex, path: str) -> dict:
    text = read_text(vault_path, path)
    if text is None:
        raise FileNotFoundError(f"Note not found: {path!r}")
    outgoing = []
    for link in parse_links(text):
        if not link.target.strip():
            continue
        res = index.resolve(link.target, path)
        entry = {"line": link.line, "link": link.raw, "target": res.target}
        if res.ambiguous:
            entry["ambiguous"] = True
        outgoing.append(entry)

    path_l = path.lower()
    backlinks = [
        {"source": src, "line": link.line, "link": link.raw}
        for src, link, res in scan_vault(vault_path, index)
        if res.target and res.target.lower() == path_l and src.lower() != path_l
    ]
    return {
        "path": path,
        "outgoing": outgoing,
        "unresolved": [o for o in outgoing if o["target"] is None],
        "backlinks": backlinks,
        "backlinkSources": sorted({b["source"] for b in backlinks}),
    }


def audit(vault_path: str, index: LinkIndex, folder: str = "", limit: int = 100) -> dict:
    prefix = folder.strip("/").lower()
    prefix = prefix + "/" if prefix else ""

    unresolved: dict[str, list[dict]] = {}
    ambiguous: list[dict] = []
    linked: set[str] = set()
    for src, link, res in scan_vault(vault_path, index):
        if res.target:
            if res.target != src:
                linked.add(res.target)
            if res.ambiguous and src.lower().startswith(prefix):
                ambiguous.append({"source": src, "line": link.line, "link": link.raw,
                                  "assumedTarget": res.target})
        elif src.lower().startswith(prefix):
            unresolved.setdefault(link.target.strip(), []).append({"source": src, "line": link.line})

    orphans = [
        f for f in _note_files(index)
        if f.lower().startswith(prefix) and f not in linked
    ]
    ranked = sorted(unresolved.items(), key=lambda kv: (-len(kv[1]), kv[0].lower()))
    return {
        "folder": folder or "/",
        "unresolvedTargets": len(ranked),
        "unresolved": [{"target": t, "count": len(s), "sources": s[:10]} for t, s in ranked[:limit]],
        "orphanCount": len(orphans),
        "orphans": orphans[:limit],
        "ambiguousCount": len(ambiguous),
        "ambiguous": ambiguous[:limit],
        "truncated": len(ranked) > limit or len(orphans) > limit or len(ambiguous) > limit,
    }
