from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional
import os
import re
import uuid


class DocumentError(Exception):
    """Base error for lossless document operations."""


class ConcurrentModificationError(DocumentError):
    """Raised when a file changed on disk after it was opened."""


@dataclass(frozen=True)
class Section:
    key: str
    header_start: int
    value_start: int
    value_end: int
    value: str
    terminal_eol: str


def _physical_lines(text: str) -> Iterable[tuple[int, int, int, str]]:
    """Yield content start/end, full end, and line ending for every line."""
    start = 0
    for match in re.finditer(r"\r\n|\n|\r", text):
        yield start, match.start(), match.end(), match.group(0)
        start = match.end()
    if start < len(text):
        yield start, len(text), len(text), ""


def _semantic_value(raw: str) -> str:
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    # The last terminator is structural: it starts the next H1 line or records
    # the file's final newline. md.md_to_json() does not include it in a value.
    return normalized[:-1] if normalized.endswith("\n") else normalized


class RoundTripDocument:
    """H1-section Markdown document that preserves untouched bytes exactly."""

    def __init__(self, path: Path, original: bytes, *, existed: bool = True):
        self.path = Path(path)
        self.original_bytes = original
        self.existed = existed
        self.has_bom = original.startswith(b"\xef\xbb\xbf")
        payload = original[3:] if self.has_bom else original
        try:
            self.text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentError(f"UTF-8として読み込めません: {self.path}") from exc
        self.newline = self._detect_newline(self.text)
        self.sections = self._parse_sections(self.text)

    @classmethod
    def load(cls, path: Path) -> "RoundTripDocument":
        p = Path(path)
        return cls(p, p.read_bytes(), existed=True)

    @classmethod
    def new(cls, path: Path, text: str) -> "RoundTripDocument":
        return cls(Path(path), text.encode("utf-8"), existed=False)

    @staticmethod
    def _detect_newline(text: str) -> str:
        endings = re.findall(r"\r\n|\n|\r", text)
        if not endings:
            return "\n"
        return max(dict.fromkeys(endings), key=endings.count)

    @staticmethod
    def _parse_sections(text: str) -> Dict[str, Section]:
        headers: list[tuple[str, int, int]] = []
        seen: set[str] = set()
        for content_start, content_end, full_end, _eol in _physical_lines(text):
            line = text[content_start:content_end]
            stripped = line.lstrip()
            if stripped.startswith("# "):
                key = stripped[2:].strip()
                if key in seen:
                    raise DocumentError(f"H1見出しが重複しています: {key}")
                seen.add(key)
                headers.append((key, content_start, full_end))

        sections: Dict[str, Section] = {}
        for index, (key, _header_start, value_start) in enumerate(headers):
            value_end = headers[index + 1][1] if index + 1 < len(headers) else len(text)
            raw = text[value_start:value_end]
            match = re.search(r"(\r\n|\n|\r)$", raw)
            terminal = match.group(1) if match else ""
            sections[key] = Section(
                key=key,
                header_start=_header_start,
                value_start=value_start,
                value_end=value_end,
                value=_semantic_value(raw),
                terminal_eol=terminal,
            )
        return sections

    def values(self) -> Dict[str, str]:
        return {key: section.value for key, section in self.sections.items()}

    def render(self, updates: Dict[str, Optional[str]]) -> bytes:
        replacements: list[tuple[int, int, str]] = []
        additions: list[tuple[str, str]] = []
        for key, value in updates.items():
            if key not in self.sections:
                if value is not None and value.strip():
                    additions.append((key, value))
                continue
            section = self.sections[key]
            if value is None:
                replacements.append((section.header_start, section.value_end, ""))
                continue
            normalized = value.replace("\r\n", "\n").replace("\r", "\n")
            if normalized == section.value:
                continue
            rendered = normalized.replace("\n", self.newline)
            if section.terminal_eol:
                rendered += section.terminal_eol
            replacements.append((section.value_start, section.value_end, rendered))

        result = self.text
        for start, end, value in sorted(replacements, reverse=True):
            result = result[:start] + value + result[end:]
        for key, value in additions:
            if result and not result.endswith(("\n", "\r")):
                result += self.newline
            normalized = value.replace("\r\n", "\n").replace("\r", "\n")
            result += f"# {key}{self.newline}"
            result += normalized.replace("\n", self.newline)
            result += self.newline
        payload = result.encode("utf-8")
        return (b"\xef\xbb\xbf" + payload) if self.has_bom else payload

    def render_raw(self, text: str) -> bytes:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        original_normalized = self.text.replace("\r\n", "\n").replace("\r", "\n")
        if normalized == original_normalized:
            return self.original_bytes
        payload = normalized.replace("\n", self.newline).encode("utf-8")
        return (b"\xef\xbb\xbf" + payload) if self.has_bom else payload

    def save(
        self,
        state_dir: Path,
        *,
        updates: Optional[Dict[str, Optional[str]]] = None,
        raw_text: Optional[str] = None,
    ) -> tuple[bool, Optional[Path]]:
        if updates is not None and raw_text is not None:
            raise ValueError("updatesとraw_textは同時に指定できません")
        new_bytes = self.render(updates or {}) if raw_text is None else self.render_raw(raw_text)
        if new_bytes == self.original_bytes and self.existed:
            return False, None

        if self.existed:
            if not self.path.is_file() or self.path.read_bytes() != self.original_bytes:
                raise ConcurrentModificationError(
                    "ファイルがエディタ外で変更されました。再読み込みしてください。"
                )
        elif self.path.exists():
            raise ConcurrentModificationError("同名のファイルが既に作成されています。")

        state = Path(state_dir)
        temp_dir = state / "write-tmp"
        backup_dir = state / "backups"
        temp_dir.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup: Optional[Path] = None
        if self.existed:
            backup = backup_dir / f"{uuid.uuid4().hex}-{self.path.name}"
            backup.write_bytes(self.original_bytes)
        temporary = temp_dir / f"{uuid.uuid4().hex}.tmp"
        temporary.write_bytes(new_bytes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, self.path)
        return True, backup

    def character_count(
        self,
        *,
        updates: Optional[Dict[str, Optional[str]]] = None,
        raw_text: Optional[str] = None,
    ) -> int:
        data = self.render(updates or {}) if raw_text is None else self.render_raw(raw_text)
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        text = data.decode("utf-8")
        return len(text.replace("\r", "").replace("\n", ""))
