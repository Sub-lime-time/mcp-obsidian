"""Full-text search with BM25 relevance reranking.

Mirrors the TypeScript SearchService: multi-word matching, per-document
term frequencies, IDF weighting (k1=1.2, b=0.75).
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pathfilter import PathFilter


def _vault_name(vault_path: str) -> str:
    return os.path.basename(vault_path)


def _obsidian_uri(vault_path: str, rel_path: str) -> str:
    name = _vault_name(vault_path)
    encoded = "/".join(p.replace(" ", "%20") for p in rel_path.split("/"))
    return f"obsidian://open?vault={name}&file={encoded}"


@dataclass
class _Candidate:
    p: str
    t: str
    ex: str
    mc: int
    ln: int
    uri: str
    term_freqs: dict[str, int] = field(default_factory=dict)
    doc_length: int = 0


_FM_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


class SearchService:
    def __init__(self, vault_path: str, path_filter: "PathFilter") -> None:
        self.vault_path = os.path.realpath(vault_path)
        self.path_filter = path_filter

    def search(
        self,
        query: str,
        limit: int = 5,
        search_content: bool = True,
        search_frontmatter: bool = False,
        case_sensitive: bool = False,
    ) -> list[dict]:
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")

        max_limit = min(limit, 20)
        q = query if case_sensitive else query.lower()
        terms = [t for t in q.split() if t]
        scoring_terms = terms + [q] if len(terms) > 1 else list(terms)

        total_doc_len = 0
        doc_count = 0
        term_df: dict[str, int] = {}
        candidates: list[_Candidate] = []

        prefix_len = len(self.vault_path) + 1

        for full_path in self._find_md(self.vault_path):
            rel = full_path[prefix_len:].replace("\\", "/")
            if not self.path_filter.is_allowed(rel):
                continue

            try:
                with open(full_path, encoding="utf-8") as f:
                    raw = f.read()
            except OSError:
                continue

            fm_match = _FM_RE.match(raw)
            if search_content and search_frontmatter:
                searchable = raw
            elif search_content:
                searchable = raw[len(fm_match.group(0)) :] if fm_match else raw
            elif search_frontmatter:
                searchable = fm_match.group(0)[4:-4] if fm_match else ""
            else:
                searchable = ""

            search_in = searchable if case_sensitive else searchable.lower()
            title = rel.split("/")[-1].removesuffix(".md")

            words = search_in.split()
            doc_len = len(words)
            total_doc_len += doc_len
            doc_count += 1

            for term in scoring_terms:
                if term in search_in:
                    term_df[term] = term_df.get(term, 0) + 1

            fname_check = title if case_sensitive else title.lower()
            fname_match = any(t in fname_check for t in terms)

            indices = [search_in.find(t) for t in terms]
            found = [i for i in indices if i != -1]
            first_idx = min(found) if found else -1

            if first_idx == -1 and not fname_match:
                continue

            term_freqs: dict[str, int] = {}
            match_count = 0
            line_number = 0
            excerpt = ""

            if first_idx != -1:
                ft_idx = indices.index(first_idx)
                first_term = terms[ft_idx]
                start = max(0, first_idx - 21)
                end = min(len(searchable), first_idx + len(first_term) + 21)
                excerpt = searchable[start:end].strip()
                if start > 0:
                    excerpt = "..." + excerpt
                if end < len(searchable):
                    excerpt = excerpt + "..."

                for term in scoring_terms:
                    count = search_in.count(term)
                    term_freqs[term] = count
                    match_count += count

                line_number = search_in[:first_idx].count("\n") + 1
            else:
                excerpt = searchable[:50].strip()
                if len(searchable) > 50:
                    excerpt += "..."

            if fname_match:
                match_count += 1

            candidates.append(
                _Candidate(
                    p=rel,
                    t=title,
                    ex=excerpt,
                    mc=match_count,
                    ln=line_number,
                    uri=_obsidian_uri(self.vault_path, rel),
                    term_freqs=term_freqs,
                    doc_length=doc_len,
                )
            )

        ranked = self._rerank(candidates, scoring_terms, term_df, doc_count, total_doc_len, max_limit)
        return [{"p": c.p, "t": c.t, "ex": c.ex, "mc": c.mc, "ln": c.ln, "uri": c.uri} for c in ranked]

    def _find_md(self, dir_path: str) -> list[str]:
        files: list[str] = []
        prefix_len = len(self.vault_path) + 1
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    rel = entry.path[prefix_len:].replace("\\", "/")
                    if entry.is_dir(follow_symlinks=False):
                        if self.path_filter.is_allowed_for_listing(rel):
                            files.extend(self._find_md(entry.path))
                    elif entry.is_file() and entry.name.endswith(".md"):
                        files.append(entry.path)
        except OSError:
            pass
        return files

    def _rerank(
        self,
        candidates: list[_Candidate],
        terms: list[str],
        term_df: dict[str, int],
        doc_count: int,
        total_doc_len: int,
        max_limit: int,
    ) -> list[_Candidate]:
        avgdl = total_doc_len / doc_count if doc_count > 0 else 1
        k1, b = 1.2, 0.75

        scored: list[tuple[float, _Candidate]] = []
        for c in candidates:
            score = 0.0
            for term in terms:
                tf = c.term_freqs.get(term, 0)
                df = term_df.get(term, 0)
                idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
                denom = tf + k1 * (1 - b + b * c.doc_length / avgdl)
                score += idf * (tf * (k1 + 1)) / denom if denom else 0
            scored.append((score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:max_limit]]
