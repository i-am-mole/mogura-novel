# tools/story.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union, List

import hashlib

import md


@dataclass(frozen=True)
class Story:
    """小説の一話を表現する。

    単一ファイル内で完結する不正のみ検出する。
    （話数番号の重複など、複数ファイルを見ないと分からない不正は扱わない）
    """

    path: Path
    title: str
    number: int
    content: str
    length: int  # 改行を除いた本文文字数

    @staticmethod
    def load_if_valid(path: Union[str, Path]) -> Union["Story", List[str]]:
        """話ファイルを検証し、妥当なら Story、そうでなければエラーメッセージ一覧を返す。"""
        p = Path(path)
        errors: List[str] = []

        # ファイル存在確認
        if not p.is_file():
            return [f"Story file not found: {p}"]

        # md.py による H1 -> 値 変換
        try:
            data = md.md_to_json(str(p))
        except md.JsonKeyDuplicateError as e:
            return [f"Duplicate header: {e}"]

        allowed_keys = {"title", "number", "content"}

        # H1 が 1 つも無い
        if not data:
            errors.append("No H1 headers found. Required headers: title, number, content")

        # 未定義ヘッダ
        for key in data.keys():
            if key not in allowed_keys:
                errors.append(f"Unexpected header: {key}")

        # 必須ヘッダ不足
        for key in allowed_keys:
            if key not in data:
                errors.append(f"Missing required header: {key}")

        title = data.get("title", "")
        number_raw = data.get("number", "")
        content = data.get("content", "")

        # 空値チェック
        if "title" in data and not title.strip():
            errors.append("`title` must not be empty")
        if "number" in data and not number_raw.strip():
            errors.append("`number` must not be empty")
        if "content" in data and not content.strip():
            errors.append("`content` must not be empty")

        # title: 複数行は禁止
        if "title" in data and ("\n" in title or "\r" in title):
            errors.append("`title` must be a single line")

        # number: 整数必須
        number_val = None
        if "number" in data and number_raw.strip():
            number_str = number_raw.strip()
            if _is_int_string(number_str):
                number_val = int(number_str)
            else:
                errors.append("`number` must be an integer")

        if errors:
            return errors

        # 妥当な場合 Story を生成
        length = _count_text_length(content)
        return Story(
            path=p,
            title=title.strip(),
            number=number_val,
            content=content,
            length=length,
        )

    def hash(self) -> str:
        """title, number, content から SHA256 ハッシュ値を計算して返す。"""
        base = f"{self.title}\n{self.number}\n{self.content}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _is_int_string(s: str) -> bool:
    if not s:
        return False
    if s[0] in "+-":
        return s[1:].isdigit()
    return s.isdigit()


def _count_text_length(text: str) -> int:
    # 「本文の文字数」は改行を含めないカウントとする
    return sum(1 for c in text if c not in ("\n", "\r"))
