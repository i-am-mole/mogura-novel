from pathlib import Path
import tempfile
import unittest

from editor.repository import Repository
from editor.search import search_manuscripts


class TestManuscriptSearch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Repository(Path(self.temp.name))
        self.write("alpha/index.md", "# title\n猫\n")
        self.current = self.write("alpha/later.md", "# number\n20\n# content\n猫\n")
        self.write("alpha/earlier.md", "# number\n2\n# content\n猫猫\n")
        self.write("alpha/-draft.md", "猫")
        self.write("-beta/index.md", "猫")
        self.write("-beta/-draft.md", "猫")
        self.write("alpha/_memo.md", "猫")
        self.write("alpha/sub/nested.md", "猫")
        self.write("self_intro.md", "猫")
        self.write("css/ignored.md", "猫")

    def write(self, relative, text):
        path = self.repo.private / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def search(self, query="猫", scope="file", text="猫"):
        return [hit for hit in search_manuscripts(self.repo, self.current, text, query, scope)
                if hit is not None]

    def test_scopes_include_private_drafts_but_exclude_memos_and_other_files(self):
        self.assertEqual(len(self.search()), 1)
        work = self.search(scope="work", text=self.current.read_text(encoding="utf-8"))
        self.assertEqual([hit.path.name for hit in work],
                         ["index.md", "earlier.md", "earlier.md", "later.md", "-draft.md"])
        self.assertEqual(len(self.search(scope="all")), 7)

    def test_buffer_overrides_disk_for_every_scope_without_writing(self):
        before = self.current.read_bytes()
        for scope in ("file", "work", "all"):
            hits = self.search("未保存", scope, "未保存")
            self.assertEqual([hit.path for hit in hits], [self.current])
        self.assertEqual(self.current.read_bytes(), before)

    def test_literal_case_width_spaces_and_overlapping_matches(self):
        text = "AaＡａ .*  aaa\r\n猫猫猫"
        for query, count in (("A", 1), ("a", 4), ("Ａ", 1), (".*", 1), ("  ", 1), ("猫猫", 2)):
            self.assertEqual(len(self.search(query, text=text)), count)
        hits = self.search("猫猫", text=text)
        self.assertEqual([(h.line, h.column) for h in hits], [(2, 1), (2, 2)])
        self.assertEqual(self.search("なし", text=text), [])

    def test_empty_input_and_read_errors_are_reported(self):
        with self.assertRaises(ValueError):
            self.search("")
        (self.repo.private / "alpha" / "-draft.md").write_bytes(b"\xff")
        with self.assertRaisesRegex(ValueError, "-draft.md"):
            self.search(scope="work")
