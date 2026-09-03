from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from editor.repository import Repository, RepositoryError, validate_slug


def _story(title: str, number: int) -> str:
    return f"""# title
{title}
# number
{number}
# content
本文
"""


class TestSlugValidation(unittest.TestCase):
    def test_valid_slugs(self):
        self.assertEqual(validate_slug("episode-01", kind="episode"), "episode-01")
        self.assertEqual(validate_slug("return-of-son", kind="work"), "return-of-son")
        self.assertEqual(validate_slug("-episode-01", kind="episode"), "-episode-01")
        self.assertEqual(validate_slug("-new-work", kind="work"), "-new-work")

    def test_invalid_slugs(self):
        for value in ("日本語", "HasUpper", "two words", "two--hyphens", "-", "--head"):
            with self.assertRaises(RepositoryError):
                validate_slug(value, kind="work")
        with self.assertRaises(RepositoryError):
            validate_slug("css", kind="work")
        with self.assertRaises(RepositoryError):
            validate_slug("index", kind="episode")


class TestHistoryAwareStoryOperations(unittest.TestCase):
    def setUp(self):
        self.context = TemporaryDirectory()
        self.root = Path(self.context.name)
        (self.root / "private" / "work").mkdir(parents=True)
        (self.root / "data").mkdir()
        self.story = self.root / "private" / "work" / "old.md"
        self.story.write_text("story", encoding="utf-8")
        self.history = self.root / "data" / "update_history.csv"
        self.history.write_text(
            "private/work/old.md,hash,2025-01-01T00:00:00+00:00\n",
            encoding="utf-8",
        )
        self.repo = Repository(self.root)

    def tearDown(self):
        self.context.cleanup()

    def test_rename_preserves_hash_and_timestamp(self):
        self.repo.rename_story("work", "old", "new")
        self.assertFalse(self.story.exists())
        self.assertTrue((self.story.parent / "new.md").exists())
        self.assertEqual(
            self.history.read_text(encoding="utf-8"),
            "private/work/new.md,hash,2025-01-01T00:00:00+00:00\n",
        )

    def test_delete_and_restore_include_history(self):
        self.repo.delete_story("work", "old")
        self.assertFalse(self.story.exists())
        self.assertEqual(self.history.read_text(encoding="utf-8"), "")
        restored = self.repo.restore_last_deleted()
        self.assertEqual(restored, self.story)
        self.assertTrue(self.story.exists())
        self.assertIn("private/work/old.md,hash,", self.history.read_text(encoding="utf-8"))

    def test_publishing_draft_rejects_duplicate_story_number(self):
        (self.story.parent / "index.md").write_text(
            "# title\nt\n# tags\n- t\n# status\n連載中\n# outline\no\n",
            encoding="utf-8",
        )
        self.story.write_text(_story("公開済み", 1), encoding="utf-8")
        draft = self.story.parent / "-draft.md"
        draft.write_text(_story("下書き", 1), encoding="utf-8")

        with self.assertRaisesRegex(RepositoryError, "既に使用"):
            self.repo.rename_story("work", "-draft", "draft")

        self.assertTrue(draft.is_file())

    def test_unpublished_story_is_available_to_editor(self):
        draft = self.story.parent / "-draft.md"
        draft.write_text(_story("下書き", 2), encoding="utf-8")

        stories = self.repo.unpublished_stories("work")

        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0].path, draft)


if __name__ == "__main__":
    unittest.main()
