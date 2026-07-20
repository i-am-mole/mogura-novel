from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os
import re
import uuid

from novel import Novel

from editor.document import RoundTripDocument


SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
WORK_RESERVED = {"blog", "wiki", "css"}
EPISODE_RESERVED = {"index"}


class RepositoryError(Exception):
    pass


@dataclass
class DeletedStory:
    original: Path
    trashed: Path
    history_line: Optional[str]
    history_index: int


def validate_slug(slug: str, *, kind: str) -> str:
    value = slug.strip()
    if not SLUG_PATTERN.fullmatch(value):
        raise RepositoryError(
            "slugは小文字の半角英数字をハイフン1個で区切って入力してください。"
        )
    if value.lower() in WINDOWS_RESERVED:
        raise RepositoryError("Windowsの予約名は使用できません。")
    if kind == "work" and value in WORK_RESERVED:
        raise RepositoryError("blog、wiki、cssは作品slugに使用できません。")
    if kind == "episode" and value in EPISODE_RESERVED:
        raise RepositoryError("indexは話slugに使用できません。")
    return value


def validate_work_fields(values: dict[str, str]) -> None:
    required = ("title", "tags", "status", "outline")
    for key in required:
        if not values.get(key, "").strip():
            raise RepositoryError(f"{key}は空にできません。")
    if "\n" in values["title"] or "\r" in values["title"]:
        raise RepositoryError("タイトルは1行で入力してください。")
    if values["status"].strip() not in {"連載中", "完結済", "更新停止"}:
        raise RepositoryError("連載ステータスが不正です。")
    tag_lines = [line.strip() for line in values["tags"].splitlines() if line.strip()]
    if not tag_lines or any(not line.startswith("- ") for line in tag_lines):
        raise RepositoryError("タグは「- タグ名」の形式で1件以上入力してください。")
    links = values.get("external links")
    if links is not None:
        link_lines = [line.strip() for line in links.splitlines() if line.strip()]
        if not link_lines:
            raise RepositoryError("外部リンク見出しを残す場合は1件以上必要です。")
        for line in link_lines:
            if not (line.startswith("- [") and "](" in line and line.endswith(")")):
                raise RepositoryError("外部リンクは「- [表示名](URL)」形式で入力してください。")
    chapters = values.get("chapters")
    if chapters is not None:
        titles: set[str] = set()
        numbers: set[int] = set()
        lines = [line.strip() for line in chapters.splitlines() if line.strip()]
        if not lines:
            raise RepositoryError("章見出しを残す場合は1件以上必要です。")
        for line in lines:
            if ":" not in line:
                raise RepositoryError("章は「章タイトル: 境界番号」の形式で入力してください。")
            title, raw_number = (part.strip() for part in line.split(":", 1))
            if not title or not re.fullmatch(r"[+-]?\d+", raw_number):
                raise RepositoryError("章タイトルまたは境界番号が不正です。")
            number = int(raw_number)
            if title in titles or number in numbers:
                raise RepositoryError("章タイトルと境界番号は重複できません。")
            titles.add(title)
            numbers.add(number)


def validate_story_fields(values: dict[str, str]) -> None:
    if not values.get("title", "").strip():
        raise RepositoryError("タイトルは空にできません。")
    if "\n" in values["title"] or "\r" in values["title"]:
        raise RepositoryError("タイトルは1行で入力してください。")
    raw_number = values.get("number", "").strip()
    if not re.fullmatch(r"[+-]?\d+", raw_number):
        raise RepositoryError("話数番号は整数で入力してください。")
    if not values.get("content", "").strip():
        raise RepositoryError("本文は空にできません。")


class Repository:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.private = self.root / "private"
        self.state = self.root / ".novel-editor"
        self.history = self.root / "data" / "update_history.csv"
        self.last_deleted: Optional[DeletedStory] = None

    def work_slugs(self) -> list[str]:
        result: list[str] = []
        for child in sorted(self.private.iterdir()):
            if child.is_dir() and (child / "index.md").is_file():
                result.append(child.name)
        return result

    def load_novel(self, work_slug: str):
        return Novel.load_if_valid(self.private / work_slug / "index.md")

    def load_self_intro(self) -> RoundTripDocument:
        return RoundTripDocument.load(self.private / "self_intro.md")

    def load_work(self, work_slug: str) -> RoundTripDocument:
        return RoundTripDocument.load(self.private / work_slug / "index.md")

    def load_story(self, work_slug: str, episode_slug: str) -> RoundTripDocument:
        return RoundTripDocument.load(self.private / work_slug / f"{episode_slug}.md")

    def new_work_document(
        self,
        slug: str,
        *,
        title: str,
        tags: str,
        status: str,
        outline: str,
    ) -> RoundTripDocument:
        slug = validate_slug(slug, kind="work")
        if any(existing.lower() == slug.lower() for existing in self.work_slugs()):
            raise RepositoryError("同名の作品slugが既に存在します。")
        values = {
            "title": title,
            "tags": tags,
            "status": status,
            "outline": outline,
        }
        validate_work_fields(values)
        text = (
            f"# title\n{title.strip()}\n"
            f"# tags\n{tags.strip()}\n"
            f"# status\n{status.strip()}\n"
            f"# outline\n{outline.rstrip()}\n"
        )
        return RoundTripDocument.new(self.private / slug / "index.md", text)

    def new_story_document(
        self,
        work_slug: str,
        slug: str,
        *,
        title: str,
        number: str,
        content: str,
    ) -> RoundTripDocument:
        slug = validate_slug(slug, kind="episode")
        target = self.private / work_slug / f"{slug}.md"
        if any(
            child.name.lower() == target.name.lower()
            for child in target.parent.glob("*.md")
        ):
            raise RepositoryError("同名の話slugが既に存在します。")
        values = {"title": title, "number": number, "content": content}
        validate_story_fields(values)
        self._validate_unique_number(work_slug, int(number), exclude=None)
        text = (
            f"# title\n{title.strip()}\n"
            f"# number\n{number.strip()}\n"
            f"# content\n{content.rstrip()}\n"
        )
        return RoundTripDocument.new(target, text)

    def validate_story_update(
        self, work_slug: str, episode_slug: str, values: dict[str, str]
    ) -> None:
        validate_story_fields(values)
        self._validate_unique_number(
            work_slug, int(values["number"].strip()), exclude=episode_slug
        )

    def _validate_unique_number(
        self, work_slug: str, number: int, *, exclude: Optional[str]
    ) -> None:
        novel = self.load_novel(work_slug)
        if isinstance(novel, list):
            return
        for story in novel.stories:
            if exclude is not None and story.path.stem == exclude:
                continue
            if story.number == number:
                raise RepositoryError(f"話数番号 {number} は既に使用されています。")

    def rename_story(self, work_slug: str, old_slug: str, new_slug: str) -> Path:
        new_slug = validate_slug(new_slug, kind="episode")
        old_path = self.private / work_slug / f"{old_slug}.md"
        new_path = self.private / work_slug / f"{new_slug}.md"
        if new_path.exists() or any(
            p.name.lower() == new_path.name.lower() and p != old_path
            for p in old_path.parent.glob("*.md")
        ):
            raise RepositoryError("同名の話slugが既に存在します。")
        if not old_path.is_file():
            raise RepositoryError("改名元の話ファイルが見つかりません。")

        old_key = old_path.relative_to(self.root).as_posix()
        new_key = new_path.relative_to(self.root).as_posix()
        before = self.history.read_bytes() if self.history.is_file() else b""
        after = self._rename_history_bytes(before, old_key, new_key)
        os.replace(old_path, new_path)
        try:
            if after != before:
                self._atomic_write(self.history, after)
        except Exception:
            os.replace(new_path, old_path)
            raise
        return new_path

    def delete_story(self, work_slug: str, episode_slug: str) -> None:
        original = self.private / work_slug / f"{episode_slug}.md"
        if not original.is_file():
            raise RepositoryError("削除対象の話ファイルが見つかりません。")
        trash_dir = self.state / "trash" / uuid.uuid4().hex
        trash_dir.mkdir(parents=True, exist_ok=False)
        trashed = trash_dir / original.name
        key = original.relative_to(self.root).as_posix()
        before = self.history.read_bytes() if self.history.is_file() else b""
        after, deleted_line, index = self._delete_history_bytes(before, key)
        os.replace(original, trashed)
        try:
            if after != before:
                self._atomic_write(self.history, after)
        except Exception:
            os.replace(trashed, original)
            raise
        self.last_deleted = DeletedStory(original, trashed, deleted_line, index)

    def restore_last_deleted(self) -> Path:
        item = self.last_deleted
        if item is None or not item.trashed.is_file():
            raise RepositoryError("復元できる話はありません。")
        if item.original.exists():
            raise RepositoryError("復元先に同名ファイルが存在します。")
        before = self.history.read_bytes() if self.history.is_file() else b""
        after = self._restore_history_bytes(before, item.history_line, item.history_index)
        item.original.parent.mkdir(parents=True, exist_ok=True)
        os.replace(item.trashed, item.original)
        try:
            if after != before:
                self._atomic_write(self.history, after)
        except Exception:
            os.replace(item.original, item.trashed)
            raise
        self.last_deleted = None
        return item.original

    def _atomic_write(self, path: Path, data: bytes) -> None:
        temporary_dir = self.state / "write-tmp"
        backup_dir = self.state / "backups"
        temporary_dir.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            (backup_dir / f"{uuid.uuid4().hex}-{path.name}").write_bytes(path.read_bytes())
        temporary = temporary_dir / f"{uuid.uuid4().hex}.tmp"
        temporary.write_bytes(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, path)

    @staticmethod
    def _decode_history(data: bytes) -> tuple[bool, list[str]]:
        bom = data.startswith(b"\xef\xbb\xbf")
        payload = data[3:] if bom else data
        return bom, payload.decode("utf-8").splitlines(keepends=True)

    @classmethod
    def _rename_history_bytes(cls, data: bytes, old: str, new: str) -> bytes:
        bom, lines = cls._decode_history(data)
        if any(line.startswith(new + ",") for line in lines):
            raise RepositoryError("更新履歴に改名先のキーが既に存在します。")
        for index, line in enumerate(lines):
            if line.startswith(old + ","):
                lines[index] = new + line[len(old):]
                break
        payload = "".join(lines).encode("utf-8")
        return (b"\xef\xbb\xbf" + payload) if bom else payload

    @classmethod
    def _delete_history_bytes(
        cls, data: bytes, key: str
    ) -> tuple[bytes, Optional[str], int]:
        bom, lines = cls._decode_history(data)
        deleted: Optional[str] = None
        index = len(lines)
        for current, line in enumerate(lines):
            if line.startswith(key + ","):
                deleted = lines.pop(current)
                index = current
                break
        payload = "".join(lines).encode("utf-8")
        result = (b"\xef\xbb\xbf" + payload) if bom else payload
        return result, deleted, index

    @classmethod
    def _restore_history_bytes(
        cls, data: bytes, line: Optional[str], index: int
    ) -> bytes:
        if line is None:
            return data
        bom, lines = cls._decode_history(data)
        lines.insert(min(index, len(lines)), line)
        payload = "".join(lines).encode("utf-8")
        return (b"\xef\xbb\xbf" + payload) if bom else payload
