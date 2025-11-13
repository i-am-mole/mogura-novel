# tools/test_novel.py
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from novel import Novel


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestNovelValid(unittest.TestCase):
    def test_valid_novel_without_chapters(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            novel_dir = root / "private" / "novel1"
            index = novel_dir / "index.md"

            index_content = """# title
サンプル小説
# tags
- ファンタジー
- 短編
# status
完結済
# outline
これはサンプルのあらすじです。
"""
            _write(index, index_content)

            story1 = novel_dir / "001.md"
            story1_content = """# title
第一話
# number
1
# content
本文その1
"""
            _write(story1, story1_content)

            story2 = novel_dir / "002.md"
            story2_content = """# title
第二話
# number
2
# content
本文その2
"""
            _write(story2, story2_content)

            novel = Novel.load_if_valid(index)
            self.assertIsInstance(novel, Novel)
            self.assertEqual(novel.title, "サンプル小説")
            self.assertEqual(novel.status, "完結済")
            self.assertFalse(novel.has_chapters)
            self.assertEqual(novel.num_stories, 2)
            # 話数番号順になっていること
            self.assertEqual(
                [s.title for s in novel.stories], ["第一話", "第二話"]
            )
            self.assertEqual(
                novel.total_length,
                len("本文その1") + len("本文その2"),
            )

    def test_valid_novel_with_chapters(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            novel_dir = root / "private" / "novel2"
            index = novel_dir / "index.md"

            index_content = """# title
章付き小説
# tags
- 異世界
# status
連載中
# outline
章がある小説です。
# chapters
プロローグ: 1
第一章: 10
第二章: 20
"""
            _write(index, index_content)

            # number と章割り:
            # 1  -> プロローグ
            # 5,10 -> 第一章
            # 15 -> 第二章
            files = {
                "001.md": (1, "プロローグ話"),
                "005.md": (5, "第一章その1"),
                "010.md": (10, "第一章その2"),
                "015.md": (15, "第二章その1"),
            }
            for name, (num, title) in files.items():
                content = f"""# title
{title}
# number
{num}
# content
本文{num}
"""
                _write(novel_dir / name, content)

            novel = Novel.load_if_valid(index)
            self.assertIsInstance(novel, Novel)
            self.assertTrue(novel.has_chapters)

            ordered = novel.get_stories_ordered()
            self.assertIsInstance(ordered, dict)
            # 章順が保持されていること
            self.assertEqual(
                list(ordered.keys()), ["プロローグ", "第一章", "第二章"]
            )
            self.assertEqual(
                [s.number for s in ordered["プロローグ"]], [1]
            )
            self.assertEqual(
                [s.number for s in ordered["第一章"]], [5, 10]
            )
            self.assertEqual(
                [s.number for s in ordered["第二章"]], [15]
            )


class TestNovelIndexValidation(unittest.TestCase):
    def test_unknown_header(self):
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n"
            index = novel_dir / "index.md"
            content = """# title
t
# tags
- t
# status
連載中
# outline
o
# foo
bar
"""
            _write(index, content)
            result = Novel.load_if_valid(index)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("Unexpected header: foo" in m for m in result)
            )

    def test_missing_required_header(self):
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n"
            index = novel_dir / "index.md"
            content = """# title
t
# tags
- t
# outline
o
"""
            _write(index, content)
            result = Novel.load_if_valid(index)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("Missing required header: status" in m for m in result)
            )

    def test_title_multiline(self):
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n"
            index = novel_dir / "index.md"
            content = """# title
t1
t2
# tags
- t
# status
連載中
# outline
o
"""
            _write(index, content)
            result = Novel.load_if_valid(index)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("`title` must be a single line" in m for m in result)
            )

    def test_tags_invalid_list(self):
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n"
            index = novel_dir / "index.md"
            content = """# title
t
# tags
not list
# status
連載中
# outline
o
"""
            _write(index, content)
            result = Novel.load_if_valid(index)
            self.assertIsInstance(result, list)
            self.assertIn(
                "`tags` must be a Markdown list with at least one item",
                " ".join(result),
            )

    def test_status_invalid_value(self):
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n"
            index = novel_dir / "index.md"
            content = """# title
t
# tags
- t
# status
invalid
# outline
o
"""
            _write(index, content)
            result = Novel.load_if_valid(index)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("`status` must be one of" in m for m in result)
            )

#     def test_external_links_invalid(self):
#         with TemporaryDirectory() as d:
#             novel_dir = Path(d) / "n"
#             index = novel_dir / "index.md"
#             content = """# title
# t
# # tags
# - t
# # status
# 連載中
# # outline
# o
# # external links
# - [no quote](https://example.com)
# """
#             _write(index, content)
#             result = Novel.load_if_valid(index)
#             self.assertIsInstance(result, list)
#             self.assertTrue(
#                 any("`external links`" in m for m in result)
#             )

    def test_chapters_invalid_format(self):
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n"
            index = novel_dir / "index.md"
            content = """# title
t
# tags
- t
# status
連載中
# outline
o
# chapters
invalid line
"""
            _write(index, content)
            result = Novel.load_if_valid(index)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("`chapters` must be in" in m for m in result)
            )

    def test_chapters_duplicate_title_or_number(self):
        # duplicate title
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n"
            index = novel_dir / "index.md"
            content = """# title
t
# tags
- t
# status
連載中
# outline
o
# chapters
第一章: 10
第一章: 20
"""
            _write(index, content)
            result = Novel.load_if_valid(index)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("`chapters` titles must be unique" in m for m in result)
            )

        # duplicate number
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n2"
            index = novel_dir / "index.md"
            content = """# title
t
# tags
- t
# status
連載中
# outline
o
# chapters
第一章: 10
第二章: 10
"""
            _write(index, content)
            result = Novel.load_if_valid(index)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("`chapters` numbers must be unique" in m for m in result)
            )


class TestNovelStoriesValidation(unittest.TestCase):
    def test_duplicate_story_number(self):
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n"
            index = novel_dir / "index.md"
            idx_content = """# title
t
# tags
- t
# status
連載中
# outline
o
"""
            _write(index, idx_content)

            s1 = """# title
A
# number
1
# content
c
"""
            s2 = """# title
B
# number
1
# content
c
"""
            _write(novel_dir / "a.md", s1)
            _write(novel_dir / "b.md", s2)

            result = Novel.load_if_valid(index)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("Duplicate story number found: 1" in m for m in result)
            )

    def test_story_without_chapter_is_invalid(self):
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n"
            index = novel_dir / "index.md"
            idx_content = """# title
t
# tags
- t
# status
連載中
# outline
o
# chapters
第一章: 10
"""
            _write(index, idx_content)

            # 章区切り(10)より大きい話数 -> どの章にも属さず不正
            content = """# title
A
# number
20
# content
c
"""
            _write(novel_dir / "a.md", content)

            result = Novel.load_if_valid(index)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("does not belong to any chapter" in m for m in result)
            )


class TestNovelHash(unittest.TestCase):
    def test_hash_changes_when_story_changes(self):
        with TemporaryDirectory() as d:
            novel_dir = Path(d) / "n"
            index = novel_dir / "index.md"
            idx_content = """# title
t
# tags
- t
# status
連載中
# outline
o
"""
            _write(index, idx_content)

            s1 = """# title
A
# number
1
# content
c
"""
            _write(novel_dir / "a.md", s1)
            novel1 = Novel.load_if_valid(index)
            self.assertIsInstance(novel1, Novel)

            s2 = """# title
A
# number
1
# content
cc
"""
            _write(novel_dir / "a.md", s2)
            novel2 = Novel.load_if_valid(index)
            self.assertIsInstance(novel2, Novel)

            self.assertNotEqual(novel1.hash(), novel2.hash())

    def test_hash_same_for_same_data(self):
        with TemporaryDirectory() as d:
            root1 = Path(d) / "r1"
            root2 = Path(d) / "r2"
            novel_dir1 = root1 / "n"
            novel_dir2 = root2 / "n"
            index1 = novel_dir1 / "index.md"
            index2 = novel_dir2 / "index.md"

            idx = """# title
t
# tags
- t
# status
連載中
# outline
o
"""
            _write(index1, idx)
            _write(index2, idx)

            s = """# title
A
# number
1
# content
c
"""
            _write(novel_dir1 / "a.md", s)
            _write(novel_dir2 / "a.md", s)

            n1 = Novel.load_if_valid(index1)
            n2 = Novel.load_if_valid(index2)
            self.assertIsInstance(n1, Novel)
            self.assertIsInstance(n2, Novel)
            self.assertEqual(n1.hash(), n2.hash())


if __name__ == "__main__":
    unittest.main()
