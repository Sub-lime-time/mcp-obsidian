"""Property check for link-aware moves, run against a real vault.

Obsidian: [[05_Projects/Development/MCP/obsidian-mcp-python]]
Repo: ~/repos/projects/mcp-obsidian/scripts/check_link_moves.py

Copies the vault to a temporary folder (the original is never touched), makes
N random note and folder moves with move_note, and after each one checks that
every link that resolved before the move still reaches the same file, is not
newly ambiguous, and that no unresolved link was rewritten.

    uv run python scripts/check_link_moves.py "/path/to/vault" [moves=40] [seed=1]

Exit status is 1 if any move broke a link.
"""
from __future__ import annotations

import posixpath
import random
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from obsidian_mcp import links
from obsidian_mcp.filesystem import FileSystemService
from obsidian_mcp.pathfilter import PathFilter


def snapshot(vault: str, pf: PathFilter) -> dict[str, list[tuple[str, links.Resolution]]]:
    idx = links.LinkIndex(list(links.iter_vault_files(vault, pf)))
    out: dict[str, list] = defaultdict(list)
    for src, link, res in links.scan_vault(vault, idx):
        out[src].append((link.raw, res))
    return out


def pick_move(rnd: random.Random, notes: list[str], i: int) -> tuple[str, str]:
    if rnd.random() < 0.25:
        dirs = sorted({posixpath.dirname(n) for n in notes} - {""})
        old = rnd.choice(dirs)
        parent = posixpath.dirname(old)
        new = rnd.choice([f"Moved {i}", f"99_Archive/Moved {i}",
                          posixpath.join(parent, f"Renamed {i}")])
        return old, new
    old = rnd.choice(notes)
    stem = posixpath.basename(old)
    new = rnd.choice([
        f"Moved {i}/{stem}",                                            # new folder
        posixpath.join(posixpath.dirname(old), f"Renamed {i}.md"),      # rename in place
        posixpath.join(posixpath.dirname(rnd.choice(notes)), stem),     # other existing folder
    ])
    return old, new


def check(before, after, remap) -> list[tuple]:
    bad = []
    for note, bl in before.items():
        al = after.get(remap(note), [])
        if len(al) != len(bl):
            bad.append((remap(note), "link count changed", len(bl), len(al)))
            continue
        for (braw, br), (araw, ar) in zip(bl, al):
            if br.target and ar.target != remap(br.target):
                bad.append((remap(note), braw, araw, f"now -> {ar.target}"))
            elif br.target and ar.ambiguous and not br.ambiguous:
                bad.append((remap(note), braw, araw, "newly ambiguous"))
            elif not br.target and araw != braw:
                bad.append((remap(note), braw, araw, "unresolved link rewritten"))
    return bad


def main() -> int:
    src = Path(sys.argv[1]).expanduser()
    moves = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    if not src.is_dir():
        sys.exit(f"Not a directory: {src}")

    tmp = Path(tempfile.mkdtemp(prefix="link-move-check-"))
    vault = str(tmp / "vault")
    try:
        shutil.copytree(src, vault, ignore=shutil.ignore_patterns(".git"))
        pf = PathFilter()
        svc = FileSystemService(vault, pf, move_verify_delay=0)
        rnd = random.Random(seed)
        failures = rewritten = 0
        for i in range(moves):
            notes = [f for f in links.iter_vault_files(vault, pf) if f.endswith(".md")]
            old, new = pick_move(rnd, notes, i)
            if Path(vault, new).exists():
                continue
            before = snapshot(vault, pf)
            t = time.time()
            res = svc.move_note(old, new)
            if not res["success"]:
                print(f"{i:02d} refused {old!r} -> {new!r}: {res['message']}")
                continue
            bad = check(before, snapshot(vault, pf), links.make_remap(old, new))
            rewritten += res["linksUpdated"]
            status = "BROKEN" if bad else "ok"
            print(f"{i:02d} {status} {time.time() - t:.2f}s {old!r} -> {new!r}: "
                  f"{res['linksUpdated']} links in {len(res['filesUpdated'])} files")
            for b in bad[:5]:
                print("     ", b)
            failures += bool(bad)
        print(f"done: {failures} broken moves, {rewritten} links rewritten (seed {seed})")
        return 1 if failures else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
