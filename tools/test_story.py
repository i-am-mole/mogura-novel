# tools/test_story.py
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from story import Story


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestStoryLoadIfValid(unittest.TestCase):
    def test_valid_story(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "novel" / "001.md"
            content = """# title
プロローグ
# number
1
# content
ここから物語が始まる。
"""
            _write(p, content)
            result = Story.load_if_valid(p)

            self.assertIsInstance(result, Story)
            self.assertEqual(result.path, p)
            self.assertEqual(result.title, "プロローグ")
            self.assertEqual(result.number, 1)
            self.assertEqual(result.content.strip(), "ここから物語が始まる。")
            # length は改行を除いた本文の文字数
            self.assertEqual(result.length, len("ここから物語が始まる。"))

    def test_unknown_header(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "1.md"
            content = """# title
タイトル
# number
1
# content
本文
# extra
不要なヘッダ
"""
            _write(p, content)
            result = Story.load_if_valid(p)

            self.assertIsInstance(result, list)
            self.assertTrue(any("Unexpected header: extra" in msg for msg in result))

    def test_missing_required_headers(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "1.md"
            content = """# title
タイトル
# content
本文
"""
            _write(p, content)
            result = Story.load_if_valid(p)

            self.assertIsInstance(result, list)
            self.assertTrue(any("Missing required header: number" in msg for msg in result))

    def test_empty_values(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "1.md"
            content = """# title
タイトル
# number

# content

"""
            _write(p, content)
            result = Story.load_if_valid(p)

            self.assertIsInstance(result, list)
            joined = "\n".join(result)
            self.assertIn("`number` must not be empty", joined)
            self.assertIn("`content` must not be empty", joined)

    def test_title_multiline_invalid(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "1.md"
            content = """# title
タイトル1行目
タイトル2行目
# number
1
# content
本文
"""
            _write(p, content)
            result = Story.load_if_valid(p)

            self.assertIsInstance(result, list)
            self.assertTrue(any("`title` must be a single line" in msg for msg in result))

    def test_number_must_be_integer(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "1.md"
            content = """# title
タイトル
# number
not-int
# content
本文
"""
            _write(p, content)
            result = Story.load_if_valid(p)

            self.assertIsInstance(result, list)
            self.assertTrue(any("`number` must be an integer" in msg for msg in result))

    def test_duplicate_headers(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "1.md"
            content = """# title
タイトル
# number
1
# content
本文
# title
もう一つのタイトル
"""
            _write(p, content)
            result = Story.load_if_valid(p)

            self.assertIsInstance(result, list)
            self.assertTrue(any("Duplicate header" in msg for msg in result))

    def test_no_h1_headers(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "1.md"
            content = "これは h1 ヘッダの無い本文です。"
            _write(p, content)
            result = Story.load_if_valid(p)

            self.assertIsInstance(result, list)
            self.assertTrue(any("No H1 headers found" in msg for msg in result))


class TestStoryHash(unittest.TestCase):
    def test_hash_changes_when_content_changes(self):
        with TemporaryDirectory() as d:
            p1 = Path(d) / "1.md"
            content1 = """# title
タイトル
# number
1
# content
本文A
"""
            _write(p1, content1)
            story1 = Story.load_if_valid(p1)
            self.assertIsInstance(story1, Story)

            p2 = Path(d) / "2.md"
            content2 = """# title
タイトル
# number
1
# content
本文B
"""
            _write(p2, content2)
            story2 = Story.load_if_valid(p2)
            self.assertIsInstance(story2, Story)

            self.assertNotEqual(story1.hash(), story2.hash())

    def test_hash_same_for_same_data(self):
        with TemporaryDirectory() as d:
            p1 = Path(d) / "1.md"
            content = """# title
タイトル
# number
1
# content
本文
"""
            _write(p1, content)
            story1 = Story.load_if_valid(p1)
            self.assertIsInstance(story1, Story)

            p2 = Path(d) / "2.md"
            _write(p2, content)
            story2 = Story.load_if_valid(p2)
            self.assertIsInstance(story2, Story)

            self.assertEqual(story1.hash(), story2.hash())


if __name__ == "__main__":
    unittest.main()
