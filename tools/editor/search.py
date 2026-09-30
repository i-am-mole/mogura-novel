"""Literal manuscript search, independent of Tk and publication validation."""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right
from pathlib import Path
import re

from editor.repository import Repository


@dataclass(frozen=True)
class SearchHit:
    path: Path
    number: str
    line: int
    column: int
    context: str


def search_manuscripts(repo: Repository, current: Path, current_text: str,
                       query: str, scope: str):
    """Yield hits and cooperative checkpoints (None), including overlapping hits.

    The current editor buffer replaces its disk file. No validation or writes
    are performed, so incomplete unpublished drafts remain searchable.
    """
    if not query:
        raise ValueError("検索文字列を入力してください。")
    if scope not in {"file", "work", "all"}:
        raise ValueError("検索範囲が不正です。")
    if scope == "file":
        paths = [current]
    else:
        slugs = repo.work_slugs() if scope == "all" else [current.parent.name]
        paths = [path for slug in slugs
                 for path in (repo.private / slug).glob("*.md")
                 if path.is_file() and not path.name.startswith("_")]
    documents = []
    for path in paths:
        try:
            text = current_text if path == current else path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"読み込めません: {path}\n{exc}") from exc
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        number_match = re.search(r"(?m)^# number\n([+-]?\d+)\s*$", text)
        number = number_match.group(1) if number_match else ""
        order = (path.parent.name, path.name != "index.md",
                 int(number) if number else float("inf"), path.name)
        documents.append((order, path, number, text))
        yield None
    for _, path, number, text in sorted(documents):
        starts = [0] + [m.end() for m in re.finditer("\n", text)]
        position = text.find(query)
        while position >= 0:
            line = bisect_right(starts, position)
            end = position + len(query)
            context = (text[max(starts[line - 1], position - 35):position]
                       + "【" + query + "】" + text[end:end + 55].split("\n")[0])
            yield SearchHit(path, number, line, position - starts[line - 1] + 1,
                            context.replace("\n", "↵").replace("\t", "    "))
            position = text.find(query, position + 1)
        yield None
