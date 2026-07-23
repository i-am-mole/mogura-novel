from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from html.parser import HTMLParser
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import sys
import tempfile
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import md
from novel import Novel


SITES = ("narou", "kakuyomu", "pixiv", "hameln")
SEPARATOR = "◇　◇　◇"


class ExportError(Exception):
    """An expected, user-facing repost export failure."""


class ValidationError(ExportError):
    """Validation errors returned by the existing novel loader."""

    def __init__(self, index_path: Path, errors: Sequence[str]) -> None:
        self.index_path = index_path
        self.errors = tuple(errors)
        super().__init__(f"原稿の検証に失敗しました: {index_path}")


class FieldKind(Enum):
    WORK_TITLE = "作品タイトル"
    OUTLINE = "あらすじ"
    STORY_TITLE = "各話タイトル"
    BODY = "各話本文"


class RubyForm(Enum):
    PLAIN = "plain"
    BAR = "bar"
    PIXIV = "pixiv"


RubyValidator = Callable[[str, str], Optional[str]]


@dataclass(frozen=True)
class SiteStrategy:
    ruby_forms: Mapping[FieldKind, RubyForm]
    ruby_validator: Optional[RubyValidator] = None


@dataclass(frozen=True)
class RubyWarning:
    source: str
    base: str
    reading: str
    reason: str

    def format(self) -> str:
        original = f"|{self.base}<{self.reading}>".replace("\n", "\\n")
        fallback = f"{self.base}（{self.reading}）".replace("\n", "\\n")
        return (
            f"警告: {self.source}: ルビ「{original}」を"
            f"「{fallback}」へフォールバックしました（{self.reason}）"
        )


@dataclass
class _HtmlNode:
    tag: str
    attrs: Dict[str, Optional[str]] = field(default_factory=dict)
    children: List[Union["_HtmlNode", str]] = field(default_factory=list)


class _HtmlTreeParser(HTMLParser):
    """Build the small tree needed for deterministic plain-text rendering."""

    _VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _HtmlNode("document")
        self._stack = [self.root]

    def handle_starttag(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]]
    ) -> None:
        normalized_tag = tag.lower()
        node = _HtmlNode(normalized_tag, dict(attrs))
        self._stack[-1].children.append(node)
        if normalized_tag not in self._VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]]
    ) -> None:
        node = _HtmlNode(tag.lower(), dict(attrs))
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == normalized_tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


def _validate_narou_ruby(base: str, reading: str) -> Optional[str]:
    if not 1 <= len(base) <= 10:
        return f"親文字が1～10文字ではありません（{len(base)}文字）"
    if not 1 <= len(reading) <= 10:
        return f"ルビが1～10文字ではありません（{len(reading)}文字）"
    unsafe = sorted(set(base + reading) & set('&"<>'))
    if unsafe:
        return f"安全に扱えない文字 {''.join(unsafe)!r} を含みます"
    return None


def _validate_kakuyomu_ruby(base: str, reading: str) -> Optional[str]:
    if "\n" in base or "\r" in base or "\n" in reading or "\r" in reading:
        return "改行をまたいでいます"
    if not 1 <= len(base) <= 20:
        return f"親文字が1～20文字ではありません（{len(base)}文字）"
    if not 1 <= len(reading) <= 50:
        return f"ルビが1～50文字ではありません（{len(reading)}文字）"
    return None


_HALF_WIDTH_ALNUM = re.compile(r"[A-Za-z0-9]+")


def _hameln_limit(text: str) -> int:
    return 60 if _HALF_WIDTH_ALNUM.fullmatch(text) else 20


def _validate_hameln_ruby(base: str, reading: str) -> Optional[str]:
    base_limit = _hameln_limit(base)
    reading_limit = _hameln_limit(reading)
    if not 1 <= len(base) <= base_limit:
        kind = "半角英数字" if base_limit == 60 else "通常・混在文字列"
        return f"親文字が{kind}の上限{base_limit}文字を超えています（{len(base)}文字）"
    if not 1 <= len(reading) <= reading_limit:
        kind = "半角英数字" if reading_limit == 60 else "通常・混在文字列"
        return f"ルビが{kind}の上限{reading_limit}文字を超えています（{len(reading)}文字）"
    return None


_PLAIN_EXCEPT_BODY = {
    FieldKind.WORK_TITLE: RubyForm.PLAIN,
    FieldKind.OUTLINE: RubyForm.PLAIN,
    FieldKind.STORY_TITLE: RubyForm.PLAIN,
    FieldKind.BODY: RubyForm.BAR,
}

SITE_STRATEGIES: Mapping[str, SiteStrategy] = {
    "narou": SiteStrategy(_PLAIN_EXCEPT_BODY, _validate_narou_ruby),
    "kakuyomu": SiteStrategy(_PLAIN_EXCEPT_BODY, _validate_kakuyomu_ruby),
    "pixiv": SiteStrategy(
        {
            FieldKind.WORK_TITLE: RubyForm.PLAIN,
            FieldKind.OUTLINE: RubyForm.PLAIN,
            FieldKind.STORY_TITLE: RubyForm.PLAIN,
            FieldKind.BODY: RubyForm.PIXIV,
        }
    ),
    "hameln": SiteStrategy(
        {
            FieldKind.WORK_TITLE: RubyForm.PLAIN,
            FieldKind.OUTLINE: RubyForm.BAR,
            FieldKind.STORY_TITLE: RubyForm.BAR,
            FieldKind.BODY: RubyForm.BAR,
        },
        _validate_hameln_ruby,
    ),
}


def get_site_strategy(site: str) -> SiteStrategy:
    try:
        return SITE_STRATEGIES[site]
    except KeyError as exc:
        raise ExportError(
            f"未対応の転載先です: {site!r}（対応: {', '.join(SITES)}）"
        ) from exc


def convert_ruby(
    base: str,
    reading: str,
    *,
    site: str,
    field_kind: FieldKind,
    source: str,
    warnings: List[RubyWarning],
) -> str:
    strategy = get_site_strategy(site)
    form = strategy.ruby_forms[field_kind]
    fallback = f"{base}（{reading}）"

    if form is RubyForm.PLAIN:
        return fallback

    if strategy.ruby_validator is not None:
        reason = strategy.ruby_validator(base, reading)
        if reason is not None:
            warnings.append(RubyWarning(source, base, reading, reason))
            return fallback

    if form is RubyForm.BAR:
        return f"｜{base}《{reading}》"
    if form is RubyForm.PIXIV:
        return f"[[rb: {base} > {reading}]]"
    raise ExportError(f"未対応のルビ出力形式です: {form}")


class _TextRenderer:
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "header",
        "main",
        "nav",
        "pre",
        "section",
        "summary",
    }

    def __init__(
        self,
        *,
        site: str,
        field_kind: FieldKind,
        source: str,
        warnings: List[RubyWarning],
    ) -> None:
        self.site = site
        self.field_kind = field_kind
        self.source = source
        self.warnings = warnings

    def render(self, node: _HtmlNode) -> str:
        tag = node.tag
        if tag == "document":
            return self._render_children(node)
        if tag == "ruby":
            base, reading = self._ruby_parts(node)
            return convert_ruby(
                base,
                reading,
                site=self.site,
                field_kind=self.field_kind,
                source=self.source,
                warnings=self.warnings,
            )
        if tag in {"rt", "rp"}:
            return ""
        if tag == "br":
            return "\n"
        if tag == "hr":
            return f"\n\n{SEPARATOR}\n\n"
        if tag == "p":
            return f"\n\n{self._render_children(node).strip(chr(10))}\n\n"
        if tag in {"ul", "ol"}:
            return self._render_list(node, ordered=tag == "ol")
        if tag == "li":
            return self._render_children(node)
        if tag == "blockquote":
            text = self._render_children(node).strip("\n")
            quoted = "\n".join(f"＞{line}" for line in text.splitlines())
            return f"\n\n{quoted}\n\n"
        if tag == "a":
            label = self._render_children(node).strip("\n")
            url = node.attrs.get("href") or ""
            if not url or label == url:
                return label or url
            return f"{label}（{url}）"
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return f"\n\n{self._render_children(node).strip(chr(10))}\n\n"
        if tag in self._BLOCK_TAGS:
            return f"\n\n{self._render_children(node).strip(chr(10))}\n\n"
        return self._render_children(node)

    def _render_children(self, node: _HtmlNode) -> str:
        chunks: List[str] = []
        previous_was_br = False
        for child in node.children:
            if isinstance(child, str):
                # Python-Markdown emits "<br>\n" for one source line break.
                # The newline is HTML formatting; the <br> already represents it.
                if previous_was_br and child.startswith("\n"):
                    child = child[1:]
                chunks.append(child)
                previous_was_br = False
            else:
                chunks.append(self.render(child))
                previous_was_br = child.tag == "br"
        return "".join(chunks)

    def _render_list(self, node: _HtmlNode, *, ordered: bool) -> str:
        lines: List[str] = []
        item_number = 0
        for child in node.children:
            if not isinstance(child, _HtmlNode) or child.tag != "li":
                continue
            item_number += 1
            text = self._render_children(child).strip("\n")
            item_lines = text.splitlines() or [""]
            prefix = f"{item_number}. " if ordered else "・"
            lines.append(prefix + item_lines[0])
            lines.extend(item_lines[1:])
        return f"\n\n{chr(10).join(lines)}\n\n"

    def _ruby_parts(self, node: _HtmlNode) -> Tuple[str, str]:
        base_chunks: List[str] = []
        reading_chunks: List[str] = []
        for child in node.children:
            if isinstance(child, _HtmlNode) and child.tag == "rt":
                reading_chunks.append(self._plain_text(child))
            elif isinstance(child, _HtmlNode) and child.tag == "rp":
                continue
            else:
                base_chunks.append(
                    child if isinstance(child, str) else self._plain_text(child)
                )
        return "".join(base_chunks), "".join(reading_chunks)

    def _plain_text(self, node: _HtmlNode) -> str:
        if node.tag == "br":
            return "\n"
        chunks: List[str] = []
        for child in node.children:
            if isinstance(child, str):
                chunks.append(child)
            elif child.tag == "br":
                chunks.append("\n")
            else:
                chunks.append(self._plain_text(child))
        return "".join(chunks)


def normalize_text(text: str) -> str:
    """Normalize generated text without removing indentation."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip(" \t") for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip("\n") + "\n"


def html_to_text(
    html: str,
    *,
    site: str,
    field_kind: FieldKind,
    source: str,
    warnings: Optional[List[RubyWarning]] = None,
) -> str:
    warning_list = warnings if warnings is not None else []
    parser = _HtmlTreeParser()
    parser.feed(html)
    parser.close()
    rendered = _TextRenderer(
        site=site,
        field_kind=field_kind,
        source=source,
        warnings=warning_list,
    ).render(parser.root)
    return normalize_text(rendered)


def markdown_to_text(
    content: str,
    *,
    site: str,
    field_kind: FieldKind,
    source: str,
    warnings: Optional[List[RubyWarning]] = None,
) -> str:
    """Use the SSG Markdown converter, then render its HTML as repost text."""
    get_site_strategy(site)
    return html_to_text(
        md.to_html(content),
        site=site,
        field_kind=field_kind,
        source=source,
        warnings=warnings,
    )


def validate_slug(slug: str) -> str:
    """Accept one directory name and reject every path-like value."""
    if not slug or slug in {".", ".."}:
        raise ExportError(f"不正なslugです: {slug!r}（単一のディレクトリ名を指定）")
    if "/" in slug or "\\" in slug or "\x00" in slug:
        raise ExportError(
            f"不正なslugです: {slug!r}（パス区切り文字は使用できません）"
        )
    windows_path = PureWindowsPath(slug)
    if windows_path.is_absolute() or windows_path.drive:
        raise ExportError(f"不正なslugです: {slug!r}（絶対パスは指定できません）")
    if Path(slug).name != slug:
        raise ExportError(f"不正なslugです: {slug!r}（単一のディレクトリ名を指定）")
    return slug


def resolve_novel_index(root: Path, slug: str) -> Path:
    validated_slug = validate_slug(slug)
    root = Path(root).resolve()
    private_dir = (root / "private").resolve()
    novel_dir = private_dir / validated_slug
    try:
        resolved_novel_dir = novel_dir.resolve()
    except OSError as exc:
        raise ExportError(
            f"作品ディレクトリを確認できません: {novel_dir}（{exc}）"
        ) from exc
    if resolved_novel_dir.parent != private_dir:
        raise ExportError(
            f"不正なslugです: {slug!r}（private/ の外は参照できません）"
        )
    if not novel_dir.exists():
        raise ExportError(f"作品slugが存在しません: {slug!r}（{novel_dir}）")
    if not novel_dir.is_dir():
        raise ExportError(f"作品slugがディレクトリではありません: {novel_dir}")
    index_path = novel_dir / "index.md"
    if not index_path.is_file():
        raise ExportError(f"作品情報ファイルが存在しません: {index_path}")
    return index_path


def load_novel(root: Path, slug: str) -> Novel:
    index_path = resolve_novel_index(root, slug)
    try:
        result = Novel.load_if_valid(index_path)
    except (OSError, UnicodeError) as exc:
        raise ExportError(f"原稿を読み込めません: {index_path}（{exc}）") from exc
    if isinstance(result, list):
        raise ValidationError(index_path, result)
    return result


def _field_text(
    content: str,
    *,
    site: str,
    field_kind: FieldKind,
    source: Path,
    warnings: List[RubyWarning],
) -> str:
    return markdown_to_text(
        content,
        site=site,
        field_kind=field_kind,
        source=str(source),
        warnings=warnings,
    ).rstrip("\n")


def build_export_files(
    novel: Novel,
    *,
    site: str,
    taiara: bool,
    warnings: List[RubyWarning],
) -> Dict[str, str]:
    get_site_strategy(site)
    if taiara:
        title = _field_text(
            novel.title,
            site=site,
            field_kind=FieldKind.WORK_TITLE,
            source=novel.path,
            warnings=warnings,
        )
        outline = _field_text(
            novel.outline,
            site=site,
            field_kind=FieldKind.OUTLINE,
            source=novel.path,
            warnings=warnings,
        )
        return {
            "title-outline.txt": (
                f"【タイトル】\n{title}\n\n【あらすじ】\n{outline}\n"
            )
        }

    if not novel.stories:
        raise ExportError(
            f"通常モードで出力できる話がありません: {novel.path.parent}"
        )

    width = max(3, len(str(len(novel.stories))))
    files: Dict[str, str] = {}
    for index, story in enumerate(novel.stories, start=1):
        title = _field_text(
            story.title,
            site=site,
            field_kind=FieldKind.STORY_TITLE,
            source=story.path,
            warnings=warnings,
        )
        body = _field_text(
            story.content,
            site=site,
            field_kind=FieldKind.BODY,
            source=story.path,
            warnings=warnings,
        )
        files[f"{index:0{width}d}.txt"] = (
            f"【タイトル】\n{title}\n\n【本文】\n{body}\n"
        )
    return files


def _write_output_file(path: Path, content: str) -> None:
    try:
        with path.open("w", encoding="utf-8", newline="\n") as output:
            output.write(content)
    except OSError as exc:
        raise ExportError(f"出力ファイルを書き込めません: {path}（{exc}）") from exc


def _unique_output_path(parent: Path, timestamp: str) -> Path:
    candidate = parent / timestamp
    suffix = 0
    while candidate.exists():
        suffix += 1
        candidate = parent / f"{timestamp}-{suffix:03d}"
    return candidate


@dataclass(frozen=True)
class ExportResult:
    output_dir: Path
    file_count: int
    warnings: Tuple[RubyWarning, ...]


def export_novel(
    root: Path,
    *,
    slug: str,
    site: str,
    taiara: bool,
    now: Optional[datetime] = None,
) -> ExportResult:
    validated_slug = validate_slug(slug)
    get_site_strategy(site)
    root = Path(root).resolve()
    novel = load_novel(root, validated_slug)
    warnings: List[RubyWarning] = []
    files = build_export_files(
        novel, site=site, taiara=taiara, warnings=warnings
    )

    configured_output_root = root / ".novel-editor" / "repost-export"
    output_root = configured_output_root.resolve()
    if not output_root.is_relative_to(root):
        raise ExportError(
            f"出力先がリポジトリの許可範囲外です: {configured_output_root}"
        )
    final_parent = output_root / validated_slug / site
    if final_parent.resolve().parent.parent != output_root:
        raise ExportError(f"出力先が許可範囲外です: {final_parent}")

    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError(f"出力ディレクトリを作成できません: {output_root}（{exc}）") from exc

    staging_path: Optional[Path] = None
    try:
        try:
            staging_path = Path(
                tempfile.mkdtemp(prefix=".repost-build-", dir=output_root)
            )
        except OSError as exc:
            raise ExportError(
                f"一時出力ディレクトリを作成できません: {output_root}（{exc}）"
            ) from exc

        for filename, content in files.items():
            _write_output_file(staging_path / filename, content)

        try:
            final_parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ExportError(
                f"出力ディレクトリを作成できません: {final_parent}（{exc}）"
            ) from exc

        timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        final_path = _unique_output_path(final_parent, timestamp)
        try:
            os.rename(staging_path, final_path)
        except OSError as exc:
            raise ExportError(
                f"完成した出力を配置できません: {final_path}（{exc}）"
            ) from exc
        staging_path = None
    finally:
        if staging_path is not None:
            shutil.rmtree(staging_path, ignore_errors=True)

    return ExportResult(final_path.resolve(), len(files), tuple(warnings))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="private/ の小説原稿を投稿サイト向けテキストへ変換します。"
    )
    parser.add_argument(
        "--slug",
        required=True,
        help="private/<slug>/ のディレクトリ名",
    )
    parser.add_argument(
        "--to",
        required=True,
        choices=SITES,
        dest="site",
        help="転載先サイト",
    )
    parser.add_argument(
        "--taiara",
        action="store_true",
        help="全話ではなく作品タイトルとあらすじを出力",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        result = export_novel(
            root,
            slug=args.slug,
            site=args.site,
            taiara=args.taiara,
        )
    except ValidationError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    except ExportError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"予期しないエラー: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    for warning in result.warnings:
        print(warning.format(), file=sys.stderr)
    mode = "タイトル・あらすじ" if args.taiara else "全話"
    print(f"対象作品slug: {args.slug}")
    print(f"転載先: {args.site}")
    print(f"モード: {mode}")
    print(f"出力先: {result.output_dir}")
    print(f"出力ファイル数: {result.file_count}")
    print(f"警告数: {len(result.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
