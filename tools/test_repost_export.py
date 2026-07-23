from datetime import datetime
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import repost_export
from repost_export import (
    ExportError,
    FieldKind,
    RubyWarning,
    export_novel,
    html_to_text,
    markdown_to_text,
    validate_slug,
)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _make_novel(
    root: Path,
    *,
    slug: str = "sample",
    stories: tuple[tuple[str, int, str, str], ...] = (
        ("later.md", 20, "第二話", "　二番目"),
        (
            "first.md",
            10,
            "|最初<さいしょ>の話",
            "　|漢字<かんじ>です。\n次の行です。\n\n---\n\n終わり。",
        ),
    ),
) -> Path:
    novel_dir = root / "private" / slug
    _write(
        novel_dir / "index.md",
        """# title
|作品<さくひん>名
# tags
- テスト
# status
完結済
# outline
　|概要<がいよう>です。

二段落目です。
""",
    )
    for filename, number, title, content in stories:
        _write(
            novel_dir / filename,
            f"""# title
{title}
# number
{number}
# content
{content}
""",
        )
    return novel_dir


def _convert(
    content: str, site: str, field_kind: FieldKind
) -> tuple[str, list[RubyWarning]]:
    warnings: list[RubyWarning] = []
    converted = markdown_to_text(
        content,
        site=site,
        field_kind=field_kind,
        source="sample.md",
        warnings=warnings,
    )
    return converted, warnings


class TestRubyConversion(unittest.TestCase):
    def test_four_sites_body_ruby(self):
        expected = {
            "narou": "｜漢字《かんじ》\n",
            "kakuyomu": "｜漢字《かんじ》\n",
            "pixiv": "[[rb: 漢字 > かんじ]]\n",
            "hameln": "｜漢字《かんじ》\n",
        }
        for site, output in expected.items():
            with self.subTest(site=site):
                actual, warnings = _convert(
                    "|漢字<かんじ>", site, FieldKind.BODY
                )
                self.assertEqual(actual, output)
                self.assertEqual(warnings, [])

    def test_four_sites_non_body_field_ruby(self):
        expected = {
            "narou": {
                FieldKind.WORK_TITLE: "漢字（かんじ）\n",
                FieldKind.OUTLINE: "漢字（かんじ）\n",
                FieldKind.STORY_TITLE: "漢字（かんじ）\n",
            },
            "kakuyomu": {
                FieldKind.WORK_TITLE: "漢字（かんじ）\n",
                FieldKind.OUTLINE: "漢字（かんじ）\n",
                FieldKind.STORY_TITLE: "漢字（かんじ）\n",
            },
            "pixiv": {
                FieldKind.WORK_TITLE: "漢字（かんじ）\n",
                FieldKind.OUTLINE: "漢字（かんじ）\n",
                FieldKind.STORY_TITLE: "漢字（かんじ）\n",
            },
            "hameln": {
                FieldKind.WORK_TITLE: "漢字（かんじ）\n",
                FieldKind.OUTLINE: "｜漢字《かんじ》\n",
                FieldKind.STORY_TITLE: "｜漢字《かんじ》\n",
            },
        }
        for site, fields in expected.items():
            for field_kind, output in fields.items():
                with self.subTest(site=site, field_kind=field_kind):
                    actual, warnings = _convert(
                        "|漢字<かんじ>", site, field_kind
                    )
                    self.assertEqual(actual, output)
                    self.assertEqual(warnings, [])

    def test_narou_limits_and_unsafe_characters(self):
        valid, warnings = _convert(
            f"|{'親' * 10}<{'読' * 10}>", "narou", FieldKind.BODY
        )
        self.assertEqual(valid, f"｜{'親' * 10}《{'読' * 10}》\n")
        self.assertEqual(warnings, [])

        for source in (
            f"|{'親' * 11}<よみ>",
            f"|親<{'よ' * 11}>",
            "|A&amp;B<reading>",
            "|ABC<quo&quot;te>",
        ):
            with self.subTest(source=source):
                converted, warnings = _convert(
                    source, "narou", FieldKind.BODY
                )
                self.assertEqual(len(warnings), 1)
                self.assertIn("（", converted)
                self.assertNotIn("｜", converted)

    def test_kakuyomu_limits_and_line_break(self):
        valid, warnings = _convert(
            f"|{'親' * 20}<{'読' * 50}>", "kakuyomu", FieldKind.BODY
        )
        self.assertEqual(valid, f"｜{'親' * 20}《{'読' * 50}》\n")
        self.assertEqual(warnings, [])

        for source in (
            f"|{'親' * 21}<よみ>",
            f"|親<{'よ' * 51}>",
        ):
            with self.subTest(source=source):
                converted, warnings = _convert(
                    source, "kakuyomu", FieldKind.BODY
                )
                self.assertEqual(len(warnings), 1)
                self.assertIn("（", converted)

        warnings = []
        converted = html_to_text(
            "<p><ruby>改<br>行<rt>かいぎょう</rt></ruby></p>",
            site="kakuyomu",
            field_kind=FieldKind.BODY,
            source="line.md",
            warnings=warnings,
        )
        self.assertEqual(converted, "改\n行（かいぎょう）\n")
        self.assertEqual(len(warnings), 1)
        self.assertIn("改行", warnings[0].reason)

    def test_hameln_limits(self):
        cases = (
            (f"|{'親' * 20}<{'読' * 20}>", True),
            (f"|{'親' * 21}<よみ>", False),
            (f"|{'A' * 60}<{'b' * 60}>", True),
            (f"|{'A' * 61}<reading>", False),
            (f"|{'A' * 20}漢<reading>", False),
        )
        for source, is_valid in cases:
            with self.subTest(source=source[:30], is_valid=is_valid):
                converted, warnings = _convert(
                    source, "hameln", FieldKind.BODY
                )
                self.assertEqual(bool(warnings), not is_valid)
                if is_valid:
                    self.assertIn("｜", converted)
                else:
                    self.assertIn("（", converted)

    def test_fallback_warning_includes_file_text_and_reason(self):
        converted, warnings = _convert(
            f"|{'長' * 11}<ながい>", "narou", FieldKind.BODY
        )
        self.assertEqual(converted, f"{'長' * 11}（ながい）\n")
        message = warnings[0].format()
        self.assertIn("sample.md", message)
        self.assertIn(f"|{'長' * 11}<ながい>", message)
        self.assertIn("1～10文字", message)

    def test_text_without_ruby_is_unchanged(self):
        content = "ルビのない文章です。\n次の行です。"
        for site in repost_export.SITES:
            with self.subTest(site=site):
                converted, warnings = _convert(content, site, FieldKind.BODY)
                self.assertEqual(converted, content + "\n")
                self.assertEqual(warnings, [])

    def test_multiple_ruby_annotations(self):
        converted, warnings = _convert(
            "|複雑<ふくざつ>な|例<れい>です。",
            "pixiv",
            FieldKind.BODY,
        )
        self.assertEqual(
            converted,
            "[[rb: 複雑 > ふくざつ]]な[[rb: 例 > れい]]です。\n",
        )
        self.assertEqual(warnings, [])


class TestMarkdownRendering(unittest.TestCase):
    def test_full_width_spaces_are_preserved(self):
        converted, _ = _convert(
            "　一行目です。\n　二行目です。\n\n　新しい段落です。",
            "pixiv",
            FieldKind.BODY,
        )
        self.assertEqual(
            converted,
            "　一行目です。\n　二行目です。\n\n　新しい段落です。\n",
        )

    def test_line_breaks_and_paragraphs(self):
        converted, _ = _convert(
            "一行目です。\n二行目です。\n\n二段落目です。",
            "pixiv",
            FieldKind.BODY,
        )
        self.assertEqual(
            converted,
            "一行目です。\n二行目です。\n\n二段落目です。\n",
        )

    def test_horizontal_rule(self):
        converted, _ = _convert(
            "前です。\n\n---\n\n後です。", "pixiv", FieldKind.BODY
        )
        self.assertEqual(converted, f"前です。\n\n{repost_export.SEPARATOR}\n\n後です。\n")

    def test_links_lists_quotes_and_inline_formatting(self):
        converted, _ = _convert(
            """## 見出し

- **太字**
- *斜体*と`コード`

> 引用一行目
> 引用二行目

1. 一番
2. 二番

[表示文字](https://example.com/path)

[https://example.com/same](https://example.com/same)
""",
            "pixiv",
            FieldKind.BODY,
        )
        self.assertEqual(
            converted,
            """見出し

・太字
・斜体とコード

＞引用一行目
＞引用二行目

1. 一番
2. 二番

表示文字（https://example.com/path）

https://example.com/same
""",
        )

    def test_entities_and_unknown_tags_keep_readable_text(self):
        converted = html_to_text(
            "<p>A &amp; B <custom>内部</custom></p>",
            site="pixiv",
            field_kind=FieldKind.BODY,
            source="entity.md",
        )
        self.assertEqual(converted, "A & B 内部\n")

    def test_no_html_tags_remain(self):
        converted, _ = _convert(
            "**太字**と|漢字<かんじ>、[リンク](https://example.com)",
            "pixiv",
            FieldKind.BODY,
        )
        self.assertIsNone(re.search(r"</?[A-Za-z][^>]*>", converted))


class TestExportIntegration(unittest.TestCase):
    def test_stories_are_exported_in_number_order(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_novel(root)
            result = export_novel(
                root,
                slug="sample",
                site="pixiv",
                taiara=False,
                now=datetime(2026, 1, 2, 3, 4, 5),
            )
            self.assertIn("最初", (result.output_dir / "001.txt").read_text("utf-8"))
            self.assertIn("第二話", (result.output_dir / "002.txt").read_text("utf-8"))

    def test_taiara_outputs_only_title_outline(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_novel(root)
            result = export_novel(
                root,
                slug="sample",
                site="hameln",
                taiara=True,
                now=datetime(2026, 1, 2, 3, 4, 5),
            )
            files = list(result.output_dir.iterdir())
            self.assertEqual([path.name for path in files], ["title-outline.txt"])
            text = files[0].read_text("utf-8")
            self.assertIn("作品（さくひん）名", text)
            self.assertIn("｜概要《がいよう》", text)
            self.assertNotIn("【本文】", text)

    def test_normal_mode_outputs_one_file_per_story(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_novel(root)
            result = export_novel(
                root,
                slug="sample",
                site="narou",
                taiara=False,
                now=datetime(2026, 1, 2, 3, 4, 5),
            )
            self.assertEqual(
                sorted(path.name for path in result.output_dir.iterdir()),
                ["001.txt", "002.txt"],
            )
            for path in result.output_dir.iterdir():
                self.assertIn("【タイトル】", path.read_text("utf-8"))
                self.assertIn("【本文】", path.read_text("utf-8"))

    def test_invalid_slugs_and_traversal_are_rejected(self):
        invalid = (
            "",
            ".",
            "..",
            "../sample",
            r"..\sample",
            "private/sample",
            r"C:\sample",
            "/absolute",
        )
        for slug in invalid:
            with self.subTest(slug=slug), self.assertRaises(ExportError):
                validate_slug(slug)

    def test_output_is_limited_to_ignored_export_root(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_novel(root)
            result = export_novel(
                root,
                slug="sample",
                site="kakuyomu",
                taiara=False,
                now=datetime(2026, 1, 2, 3, 4, 5),
            )
            allowed = (
                root / ".novel-editor" / "repost-export" / "sample" / "kakuyomu"
            ).resolve()
            self.assertTrue(result.output_dir.is_relative_to(allowed))

    def test_existing_output_is_not_overwritten(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_novel(root)
            fixed = datetime(2026, 1, 2, 3, 4, 5)
            first = export_novel(
                root, slug="sample", site="pixiv", taiara=True, now=fixed
            )
            marker = first.output_dir / "marker.txt"
            marker.write_text("keep", encoding="utf-8")
            second = export_novel(
                root, slug="sample", site="pixiv", taiara=True, now=fixed
            )
            self.assertNotEqual(first.output_dir, second.output_dir)
            self.assertEqual(first.output_dir.name, "20260102-030405")
            self.assertEqual(second.output_dir.name, "20260102-030405-001")
            self.assertEqual(marker.read_text("utf-8"), "keep")

    def test_failure_leaves_no_partial_final_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_novel(root)
            original = repost_export._write_output_file
            calls = 0

            def fail_on_second(path: Path, content: str) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise ExportError(f"test write failure: {path}")
                original(path, content)

            with patch.object(
                repost_export, "_write_output_file", side_effect=fail_on_second
            ):
                with self.assertRaises(ExportError):
                    export_novel(
                        root,
                        slug="sample",
                        site="pixiv",
                        taiara=False,
                        now=datetime(2026, 1, 2, 3, 4, 5),
                    )

            output_root = root / ".novel-editor" / "repost-export"
            remaining = list(output_root.rglob("*")) if output_root.exists() else []
            self.assertEqual(remaining, [])

    def test_output_is_utf8_with_lf_and_one_final_newline(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_novel(root)
            result = export_novel(
                root,
                slug="sample",
                site="pixiv",
                taiara=True,
                now=datetime(2026, 1, 2, 3, 4, 5),
            )
            data = (result.output_dir / "title-outline.txt").read_bytes()
            text = data.decode("utf-8")
            self.assertNotIn(b"\r", data)
            self.assertTrue(text.endswith("\n"))
            self.assertFalse(text.endswith("\n\n"))

    def test_normal_mode_rejects_novel_without_stories(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_novel(root, stories=())
            with self.assertRaises(ExportError):
                export_novel(
                    root,
                    slug="sample",
                    site="pixiv",
                    taiara=False,
                    now=datetime(2026, 1, 2, 3, 4, 5),
                )
            self.assertFalse((root / ".novel-editor").exists())

    def test_missing_slug_and_missing_index_are_clear_errors(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "private").mkdir()
            with self.assertRaisesRegex(ExportError, "存在しません"):
                repost_export.load_novel(root, "missing")
            (root / "private" / "no-index").mkdir()
            with self.assertRaisesRegex(ExportError, "index.md"):
                repost_export.load_novel(root, "no-index")

    def test_validation_errors_create_no_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "private" / "bad" / "index.md", "# title\n不完全\n")
            with self.assertRaises(repost_export.ValidationError):
                export_novel(
                    root,
                    slug="bad",
                    site="pixiv",
                    taiara=True,
                    now=datetime(2026, 1, 2, 3, 4, 5),
                )
            self.assertFalse((root / ".novel-editor").exists())

    def test_unexpected_site_is_rejected(self):
        with self.assertRaisesRegex(ExportError, "未対応"):
            repost_export.get_site_strategy("unknown")


if __name__ == "__main__":
    unittest.main()
