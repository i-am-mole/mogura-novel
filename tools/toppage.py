from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, List, Union

import hashlib
import os

from novel import Novel

# Novel.status の優先度
_STATUS_ORDER = {
    "連載中": 0,
    "完結済": 1,
    "更新停止": 2,
}


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

        # Novel の並び替え
        # 優先キー:
        #   1. Novel の更新日時 (降順)
        #   2. Novel.status の優先度 (昇順: 連載中 < 完結済 < 更新停止)
        #   3. Novel.title (昇順)
        #
        # 更新日時は index.md および配下話ファイルの mtime の最大値を使う。
        def novel_last_updated(n: Novel) -> float:
            times: List[float] = []
            # index.md
            try:
                times.append(os.path.getmtime(n.path))
            except OSError:
                pass
            # story ファイル
            for s in n.stories:
                try:
                    times.append(os.path.getmtime(s.path))
                except OSError:
                    pass
            return max(times) if times else 0.0

        def sort_key(n: Novel):
            updated = novel_last_updated(n)
            status_order = _STATUS_ORDER.get(n.status, 999)
            return (-updated, status_order, n.title)

        novels_sorted = tuple(sorted(novels, key=sort_key))
        novel_dirs_sorted = tuple(
            d for _, d in sorted(
                zip(novels, novel_dirs),
                key=lambda pair: sort_key(pair[0])
            )
        )

        # サイトタイトル / URL は仕様に沿って固定値とする
        site_title = "もぐらノベル"
        site_url = "https://www.mogura-novel.com/"

        return TopPage(
            path=p,
            title=site_title,
            url=site_url,
            self_intro=raw.strip(),
            novels=novels_sorted,
            novel_directories=tuple(
                nd for nd in novel_dirs_sorted
            ),
        )

    def hash(self) -> str:
        """
        コンテンツのハッシュを
        title, self_intro, novels の全 Novel.hash()
        から計算する。
        """
        parts: List[str] = [self.title, self.self_intro]
        for n in self.novels:
            parts.append(n.hash())
        base = "\n".join(parts)
        return hashlib.sha256(base.encode("utf-8")).hexdigest()
