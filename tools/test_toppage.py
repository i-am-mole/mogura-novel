import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from toppage import TopPage


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestTopPageValidation(unittest.TestCase):
    def test_unpublished_work_is_not_loaded_or_validated(self):
        with TemporaryDirectory() as d:
            private_dir = Path(d) / "private"
            self_intro = _write(private_dir / "self_intro.md", "自己紹介")
            _write(private_dir / "-draft-work" / "index.md", "書きかけ")

            result = TopPage.load_if_valid(self_intro)

            self.assertIsInstance(result, TopPage)
            self.assertEqual(result.novels, ())
            self.assertEqual(result.novel_directories, ())

    def test_missing_self_intro(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            result = TopPage.load_if_valid(root / "private" / "self_intro.md")
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("Self intro file not found" in m for m in result)
            )

    def test_blank_self_intro(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            self_intro = root / "private" / "self_intro.md"
            _write(self_intro, "   \n\n")
            result = TopPage.load_if_valid(self_intro)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("Self intro must not be empty" in m for m in result)
            )

    def test_invalid_novel_is_reported(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            private_dir = root / "private"
            self_intro = private_dir / "self_intro.md"
            _write(self_intro, "自己紹介テキスト")

            # 不正な小説: 必須ヘッダ不足
            bad_novel_dir = private_dir / "bad_novel"
            idx = """# title
タイトルだけ
"""
            _write(bad_novel_dir / "index.md", idx)

            result = TopPage.load_if_valid(self_intro)
            self.assertIsInstance(result, list)
            self.assertTrue(
                any("Missing required header: tags" in m for m in result)
            )

    def test_valid_top_page_collects_novels(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            private_dir = root / "private"
            self_intro = private_dir / "self_intro.md"
            _write(self_intro, "自己紹介テキスト")

            # novel1: 完結済
            n1 = private_dir / "novel1"
            idx1 = """# title
小説A
# tags
- ファンタジー
# status
完結済
# outline
あらすじA
"""
            _write(n1 / "index.md", idx1)
            s1 = """# title
A-1
# number
1
# content
AAA
"""
            _write(n1 / "001.md", s1)

            # novel2: 連載中
            n2 = private_dir / "novel2"
            idx2 = """# title
小説B
# tags
- バトル
# status
連載中
# outline
あらすじB
"""
            _write(n2 / "index.md", idx2)
            s2 = """# title
B-1
# number
1
# content
BBB
"""
            _write(n2 / "001.md", s2)

            tp = TopPage.load_if_valid(self_intro)
            self.assertIsInstance(tp, TopPage)

            # タイトル / URL
            self.assertEqual(tp.title, "もぐらノベル")
            self.assertTrue(tp.url.startswith("https://"))

            # 小説ディレクトリが検出されている
            dir_names = {p.name for p in tp.novel_directories}
            self.assertEqual(dir_names, {"novel1", "novel2"})

            # Novel インスタンスも2件
            self.assertEqual(len(tp.novels), 2)
            titles = {n.title for n in tp.novels}
            self.assertEqual(titles, {"小説A", "小説B"})

    def test_novel_discovery_is_independent_of_filesystem_mtime(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            private_dir = root / "private"
            self_intro = private_dir / "self_intro.md"
            _write(self_intro, "自己紹介テキスト")

            n_old = private_dir / "z-novel"
            idx_old = """# title
アルファ
# tags
- t
# status
連載中
# outline
o
"""
            _write(n_old / "index.md", idx_old)
            _write(n_old / "001.md", """# title
a
# number
1
# content
old
""")

            n_new = private_dir / "a-novel"
            idx_new = """# title
ベータ
# tags
- t
# status
完結済
# outline
o
"""
            _write(n_new / "index.md", idx_new)
            _write(n_new / "001.md", """# title
b
# number
1
# content
new
""")

            tp = TopPage.load_if_valid(self_intro)
            self.assertIsInstance(tp, TopPage)

            self.assertEqual(
                [path.name for path in tp.novel_directories],
                ["a-novel", "z-novel"],
            )

    def test_hash_does_not_reflect_novel_change(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            private_dir = root / "private"
            self_intro = private_dir / "self_intro.md"
            _write(self_intro, "自己紹介テキスト")

            n = private_dir / "novel"
            idx = """# title
t
# tags
- t
# status
連載中
# outline
o
"""
            _write(n / "index.md", idx)

            body = """# title
A
# number
1
# content
c
"""
            story = n / "001.md"
            _write(story, body)

            tp1 = TopPage.load_if_valid(self_intro)
            self.assertIsInstance(tp1, TopPage)
            h1 = tp1.hash()

            # 自己紹介ファイルは変えていないので、その履歴用hashも変わらない。
            body2 = """# title
A
# number
1
# content
cc
"""
            _write(story, body2)

            tp2 = TopPage.load_if_valid(self_intro)
            self.assertIsInstance(tp2, TopPage)
            h2 = tp2.hash()

            self.assertEqual(h1, h2)
            self.assertNotEqual(tp1.legacy_hash(), tp2.legacy_hash())

if __name__ == "__main__":
    unittest.main()
