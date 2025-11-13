# tools/novel.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Union, Optional

import hashlib
from collections import Counter

import md
from story import Story

VALID_STATUS = {"連載中", "完結済", "更新停止"}


@dataclass(frozen=True)
class Novel:
    """一つの小説を表現する"""

    path: Path  # index.md へのパス（プロジェクトルートからの相対パス想定）
    title: str
    tags: str
    status: str
    outline: str
    external_links: Optional[str]
    chapters: Optional[Dict[str, int]]
    has_external_links: bool
    has_chapters: bool
    stories: Tuple[Story, ...]        # 話数番号順
    num_stories: int
    total_length: int                 # 全話本文の文字数合計

    @staticmethod
    def load_if_valid(path: Union[str, Path]) -> Union["Novel", List[str]]:
        """index.md + 配下の話ファイルを検証し、妥当なら Novel を返す。"""
        p = Path(path)
        errors: List[str] = []

        if not p.is_file():
            return [f"Novel index file not found: {p}"]

        # --- index.md の検証 ---

        try:
            data = md.md_to_json(str(p))
        except md.JsonKeyDuplicateError as e:
            return [f"Duplicate header: {e}"]

        allowed = {"title", "tags", "status", "outline", "external links", "chapters"}
        required = {"title", "tags", "status", "outline"}

        if not data:
            errors.append(
                "No H1 headers found. Required headers: title, tags, status, outline"
            )

        # 未定義ヘッダ
        for key in data.keys():
            if key not in allowed:
                errors.append(f"Unexpected header: {key}")

        # 必須ヘッダ不足
        for key in required:
            if key not in data:
                errors.append(f"Missing required header: {key}")

        # ブランクチェック
        for key, value in data.items():
            if not str(value).strip():
                errors.append(f"`{key}` must not be empty")

        # title: 1行限定
        title_val = data.get("title", "")
        if "title" in data and ("\n" in title_val or "\r" in title_val):
            errors.append("`title` must be a single line")

        # tags: 要素数1以上の Markdown リスト
        tags_val = data.get("tags", "")
        if "tags" in data:
            tag_lines = [
                line.strip()
                for line in tags_val.strip().splitlines()
                if line.strip()
            ]
            if not tag_lines or any(not l.startswith("- ") for l in tag_lines):
                errors.append(
                    "`tags` must be a Markdown list with at least one item"
                )

        # status: 定義済みリテラルのみ
        status_val = data.get("status", "")
        if "status" in data:
            s = status_val.strip()
            if s not in VALID_STATUS:
                errors.append(
                    '`status` must be one of "連載中", "完結済", "更新停止"'
                )

        # external links: オプション・「- "Markdownリンク"」形式のリスト
        external_links_val = data.get("external links")
        external_links_str: Optional[str] = None
        has_external_links = False
        if external_links_val is not None:
            lines = [
                line.strip()
                for line in external_links_val.strip().splitlines()
                if line.strip()
            ]
            if not lines:
                errors.append(
                    "`external links` must be a Markdown list with at least one item"
                )
            else:
                for l in lines:
                    if not l.startswith("- "):
                        errors.append(
                            "`external links` must be a Markdown list"
                        )
                        break
                    item = l[2:].strip()
                    # if not (item.startswith('"') and item.endswith('"')):
                    #     errors.append(
                    #         'Each `external links` item must be a quoted Markdown link: - "[text](url)"'
                    #     )
                    #     break
                    # inner = item[1:-1]
                    inner = item
                    if not (
                        inner.startswith("[")
                        and "](" in inner
                        and inner.endswith(")")
                    ):
                        errors.append(
                            'Each `external links` item must contain a Markdown link like "[text](url)" inside quotes'
                        )
                        break
            if not errors:
                external_links_str = external_links_val
                has_external_links = True

        # chapters: オプション・「章タイトル: 章区切り番号」の列挙（YAML風）
        chapters_val = data.get("chapters")
        chapters_dict: Optional[Dict[str, int]] = None
        has_chapters = False
        if chapters_val is not None:
            lines = [
                line.strip()
                for line in chapters_val.strip().splitlines()
                if line.strip()
            ]
            if not lines:
                errors.append("`chapters` must not be empty if provided")
            else:
                tmp: Dict[str, int] = {}
                titles_seen = set()
                nums_seen = set()
                for l in lines:
                    if ":" not in l:
                        errors.append(
                            "`chapters` must be in '章タイトル: 章区切り番号' format"
                        )
                        tmp = {}
                        break
                    k, v = l.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    if not k or not v:
                        errors.append(
                            "`chapters` must be valid key: value pairs"
                        )
                        tmp = {}
                        break
                    if k in titles_seen:
                        errors.append("`chapters` titles must be unique")
                        tmp = {}
                        break
                    if not _is_int_string(v):
                        errors.append("`chapters` values must be integers")
                        tmp = {}
                        break
                    num = int(v)
                    if num in nums_seen:
                        errors.append("`chapters` numbers must be unique")
                        tmp = {}
                        break
                    titles_seen.add(k)
                    nums_seen.add(num)
                    tmp[k] = num
                if tmp and not errors:
                    # 章区切り番号昇順で順序付辞書化
                    chapters_dict = dict(
                        sorted(tmp.items(), key=lambda kv: kv[1])
                    )
                    has_chapters = True

        if errors:
            return errors

        # --- 話ファイルの収集・単体検証 ---

        novel_dir = p.parent
        story_files = sorted(
            f
            for f in novel_dir.iterdir()
            if f.is_file()
            and f.suffix == ".md"
            and f.name != "index.md"
            and not f.name.startswith("_")
        )

        stories: List[Story] = []
        for sf in story_files:
            result = Story.load_if_valid(sf)
            if isinstance(result, list):
                for msg in result:
                    errors.append(f"{sf}: {msg}")
            else:
                stories.append(result)

        # --- 複数話をまたぐ検証 ---

        # number の重複
        nums = [s.number for s in stories]
        for num, cnt in Counter(nums).items():
            if cnt > 1:
                errors.append(f"Duplicate story number found: {num}")

        # 章区切りがある場合、全話がいずれかの章に属するか判定
        if has_chapters and chapters_dict:
            bounds = list(chapters_dict.items())  # (章タイトル, 章区切り番号), 昇順
            for s in stories:
                if _find_chapter_for_number(s.number, bounds) is None:
                    errors.append(
                        f"Story {s.path.name} (number={s.number}) does not belong to any chapter"
                    )

        if errors:
            return errors

        # --- プロパティ構築 ---

        stories_sorted = tuple(sorted(stories, key=lambda s: s.number))
        total_length = sum(s.length for s in stories_sorted)

        return Novel(
            path=p,
            title=title_val.strip(),
            tags=tags_val,
            status=status_val.strip(),
            outline=data.get("outline", ""),
            external_links=external_links_str,
            chapters=chapters_dict,
            has_external_links=has_external_links,
            has_chapters=has_chapters,
            stories=stories_sorted,
            num_stories=len(stories_sorted),
            total_length=total_length,
        )

    def get_stories_ordered(
        self,
    ) -> Union[Tuple[Story, ...], Dict[str, Tuple[Story, ...]]]:
        """
        has_chapters が False の場合:
            話数順のタプル（self.stories）を返す。
        has_chapters が True の場合:
            章タイトルをキー、当該章に属する Story のタプルを値とする
            順序付辞書を返す（章順は章区切り番号の昇順）。
        """
        if not self.has_chapters or not self.chapters:
            return self.stories

        ordered: Dict[str, List[Story]] = {
            title: [] for title in self.chapters.keys()
        }
        bounds = list(self.chapters.items())  # (章タイトル, 章区切り番号), 昇順

        for s in self.stories:
            chapter = _find_chapter_for_number(s.number, bounds)
            if chapter is not None:
                ordered[chapter].append(s)

        return {k: tuple(v) for k, v in ordered.items()}

    def hash(self) -> str:
        """
        コンテンツのハッシュを
        title, tags, status, outline, external_links, chapters,
        stories の全 Story.hash() から計算する。
        """
        parts = [
            self.title,
            self.tags,
            self.status,
            self.outline,
            self.external_links or "",
            repr(self.chapters) if self.chapters else "",
        ]
        for s in self.stories:
            parts.append(s.hash())

        base = "\n".join(parts)
        return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _is_int_string(s: str) -> bool:
    if not s:
        return False
    if s[0] in "+-":
        return s[1:].isdigit()
    return s.isdigit()


def _find_chapter_for_number(
    number: int, bounds: List[tuple[str, int]]
) -> Optional[str]:
    """
    章区切り番号に基づいて話数が属する章タイトルを返す。
    ルール: 話数番号 <= 章区切り番号 を満たす最初の章（境界値昇順）に属する。
    条件を満たす章が無ければ None。
    """
    for title, boundary in bounds:
        if number <= boundary:
            return title
    return None
