from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from editor.document import ConcurrentModificationError, RoundTripDocument


class TestRoundTripDocument(unittest.TestCase):
    def test_no_change_is_byte_identical_for_newline_variants(self):
        variants = [
            "# title\n話\n# number\n1\n# content\n本文\n".encode("utf-8"),
            b"# title\r\nA\r\n# number\r\n1\r\n# content\r\nB",
            b"\xef\xbb\xbf# title\nA\n# number\n1\n# content\nB\n",
        ]
        with TemporaryDirectory() as directory:
            for index, original in enumerate(variants):
                path = Path(directory) / f"{index}.md"
                path.write_bytes(original)
                document = RoundTripDocument.load(path)
                self.assertEqual(document.render(document.values()), original)

    def test_only_changed_section_is_replaced(self):
        original = b"before\r\n# title\r\nOld\r\n# number\r\n1\r\n# content\r\nBody\r\n"
        document = RoundTripDocument(Path("story.md"), original)
        rendered = document.render({"title": "New"})
        self.assertEqual(
            rendered,
            b"before\r\n# title\r\nNew\r\n# number\r\n1\r\n# content\r\nBody\r\n",
        )

    def test_optional_section_can_be_added_and_removed(self):
        original = b"# title\nA\n# tags\n- t\n# status\n\xe9\x80\xa3\xe8\xbc\x89\xe4\xb8\xad\n# outline\nO\n"
        document = RoundTripDocument(Path("index.md"), original)
        with_links = document.render({"external links": "- [x](https://example.com)"})
        self.assertIn(b"# external links\n- [x](https://example.com)\n", with_links)
        second = RoundTripDocument(Path("index.md"), with_links)
        self.assertEqual(second.render({"external links": None}), original)

    def test_character_count_excludes_newlines_but_counts_ruby_markup(self):
        data = "# content\n|漢字<かんじ>\n".encode("utf-8")
        document = RoundTripDocument(Path("x.md"), data)
        self.assertEqual(document.character_count(), len("# content|漢字<かんじ>"))

    def test_plain_document_no_change_preserves_crlf(self):
        original = "一行目\r\n二行目\r\n".encode("utf-8")
        document = RoundTripDocument(Path("self_intro.md"), original)
        self.assertEqual(document.render_raw("一行目\n二行目\n"), original)

    def test_external_change_blocks_save(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "x.md"
            path.write_text("# title\nA\n", encoding="utf-8")
            document = RoundTripDocument.load(path)
            path.write_text("# title\nExternal\n", encoding="utf-8")
            with self.assertRaises(ConcurrentModificationError):
                document.save(root / "state", updates={"title": "Mine"})


if __name__ == "__main__":
    unittest.main()
