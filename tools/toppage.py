from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Iterable, Iterator, Tuple, List, Union

import hashlib

from novel import Novel

@dataclass(frozen=True)
class TopPage:
    """もぐらノベルのトップページを表現する"""

    path: Path                     # self_intro.md へのパス（プロジェクトルートからの相対パス想定）
    title: str                     # サイトタイトル
    url: str                       # サイトトップ URL
    self_intro: str                # 「自己紹介」見出しを含まない本文
    novels: Tuple[Novel, ...]      # 指定ルール順に並んだ Novel
    novel_directories: Tuple[Path, ...]  # 小説ディレクトリ一覧（相対パス）

    @staticmethod
    def load_if_valid(path: Union[str, Path]) -> Union["TopPage", List[str]]:
        """
        path で指定された自己紹介文と同ディレクトリ配下の小説ディレクトリを検証する。
        妥当なら TopPage インスタンスを返し、不正があればエラーメッセージ一覧を返す。
        """
        p = Path(path)
        errors: List[str] = []

        # self_intro.md 存在確認
        if not p.is_file():
            return [f"Self intro file not found: {p}"]

        # 自己紹介本文読み込み
        try:
            raw = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return [f"Self intro file is not valid UTF-8: {p}"]

        # ブランクチェック（README に明記されている）
        if not raw.strip():
            errors.append("Self intro must not be empty")

        if errors:
            return errors

        # novels の探索: self_intro.md と同じディレクトリ直下のサブディレクトリで、
        # index.md を持つものを「小説ディレクトリ」とみなす。
        private_dir = p.parent
        novel_dirs: List[Path] = []
        novels: List[Novel] = []

        for child in sorted(private_dir.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith("-"):
                continue
            index_md = child / "index.md"
            if not index_md.is_file():
                continue

            novel_result = Novel.load_if_valid(index_md)
            if isinstance(novel_result, list):
                # Novel 側のエラーを TopPage のエラーとして連結
                for msg in novel_result:
                    errors.append(f"{index_md}: {msg}")
            else:
                novel_dirs.append(child)
                novels.append(novel_result)

        if errors:
            return errors

        # サイトタイトル / URL は仕様に沿って固定値とする
        site_title = "もぐらノベル"
        site_url = "https://www.mogura-novel.com/"

        return TopPage(
            path=p,
            title=site_title,
            url=site_url,
            self_intro=raw.strip(),
            # 更新日時順への並び替えは、ファイルシステムの mtime ではなく
            # update_history.csv を読める publish.py 側で行う。
            novels=tuple(novels),
            novel_directories=tuple(novel_dirs),
        )

    def hash(self) -> str:
        """self_intro.md が表す自己紹介本文のハッシュを計算する。"""
        return hashlib.sha256(self.self_intro.encode("utf-8")).hexdigest()

    def legacy_hash(self) -> str:
        """Return the pre-fix aggregate hash used for CSV migration."""
        return self._legacy_hash_for(self.novels)

    def legacy_hash_candidates(self) -> Iterator[str]:
        """Return possible hashes from the former mtime-dependent ordering.

        The old implementation hashed novels after sorting them by filesystem
        mtime. A checkout can lose that order, so migration has to accept every
        possible order for the small set of works that existed in that format.
        """
        if len(self.novels) > 8:
            yield self.legacy_hash()
            return
        for items in permutations(self.novels):
            yield self._legacy_hash_for(items)

    def _legacy_hash_for(self, novels: Iterable[Novel]) -> str:
        parts: List[str] = [self.title, self.self_intro]
        for novel in novels:
            parts.append(novel.legacy_hash())
        base = "\n".join(parts)
        return hashlib.sha256(base.encode("utf-8")).hexdigest()
