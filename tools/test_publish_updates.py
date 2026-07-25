from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from publish import generate_site, load_history, save_history
from toppage import TopPage


FIRST_RUN = datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
STORY_UPDATE = datetime(2025, 2, 3, 4, 5, 6, tzinfo=timezone.utc)


def _write(path: Path, content: str, *, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline=newline)


def _novel_index(title: str) -> str:
    return f"""# title
{title}
# tags
- テスト
# status
連載中
# outline
あらすじ
"""


def _story(title: str, number: int, content: str) -> str:
    return f"""# title
{title}
# number
{number}
# content
{content}
"""


def _make_site(root: Path) -> None:
    _write(root / "private" / "self_intro.md", "自己紹介\n")
    _write(root / "private" / "css" / "style.css", "body {}\n")
    _write(root / "private" / "CNAME", "example.test\n")

    for slug, title in (
        ("return-of-son", "帰ってきたソン"),
        ("kaminomori", "神の森"),
        ("propeht-philina", "預言者フィリナ"),
    ):
        _write(root / "private" / slug / "index.md", _novel_index(title))
        _write(
            root / "private" / slug / "first.md",
            _story("第一話", 1, f"{title}の本文"),
        )

    _write(
        root / "private" / "return-of-son" / "second.md",
        _story("第二話", 2, "変更しない本文"),
        newline="\r\n",
    )


def _files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


class TestUpdateScope(unittest.TestCase):
    def test_legacy_aggregate_hashes_migrate_without_losing_timestamps(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_site(root)
            first_docs = root / "first-docs"
            history_path = root / "history.csv"
            generate_site(root, first_docs, history_path, now=FIRST_RUN)

            history = load_history(history_path)
            tp = TopPage.load_if_valid(root / "private" / "self_intro.md")
            self.assertIsInstance(tp, TopPage)
            old_timestamps = {key: value[1] for key, value in history.items()}
            history["private/self_intro.md"] = (
                tp.legacy_hash(),
                old_timestamps["private/self_intro.md"],
            )
            for novel in tp.novels:
                key = novel.path.relative_to(root).as_posix()
                history[key] = (novel.legacy_hash(), old_timestamps[key])
            save_history(history_path, history)

            second_docs = root / "second-docs"
            migrated_history = root / "migrated-history.csv"
            generate_site(
                root,
                second_docs,
                migrated_history,
                history_seed_path=history_path,
                newline_reference_dir=first_docs,
                now=STORY_UPDATE,
            )

            migrated = load_history(migrated_history)
            self.assertEqual(
                {key: value[1] for key, value in migrated.items()},
                old_timestamps,
            )
            self.assertEqual(
                migrated["private/self_intro.md"][0],
                tp.hash(),
            )
            for novel in tp.novels:
                key = novel.path.relative_to(root).as_posix()
                self.assertEqual(migrated[key][0], novel.hash())
            self.assertEqual(_files(second_docs), _files(first_docs))

    def test_story_change_updates_site_header_and_declared_content_dependents(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_site(root)
            docs = root / "docs"
            history_path = root / "data" / "update_history.csv"

            generate_site(root, docs, history_path, now=FIRST_RUN)
            before_docs = _files(docs)
            before_history = load_history(history_path)

            changed_story = root / "private" / "return-of-son" / "first.md"
            changed_story.write_text(
                changed_story.read_text(encoding="utf-8").replace("本文", "変更後の本文"),
                encoding="utf-8",
            )

            generate_site(
                root,
                docs,
                history_path,
                history_seed_path=history_path,
                now=STORY_UPDATE,
            )

            after_docs = _files(docs)
            changed_outputs = {
                name for name in before_docs if before_docs[name] != after_docs[name]
            }
            self.assertEqual(
                changed_outputs,
                {name for name in before_docs if name.endswith(".html")},
            )
            after_history = load_history(history_path)
            changed_history = {
                key
                for key in before_history
                if before_history[key] != after_history[key]
            }
            self.assertEqual(
                changed_history,
                {"private/return-of-son/first.md"},
            )
            self.assertEqual(
                after_history["private/self_intro.md"],
                before_history["private/self_intro.md"],
            )
            self.assertEqual(
                after_history["private/return-of-son/index.md"],
                before_history["private/return-of-son/index.md"],
            )
            expected_date = STORY_UPDATE.date().isoformat().encode()
            self.assertIn(expected_date, after_docs["return-of-son/1.html"])
            self.assertIn(expected_date, after_docs["return-of-son/index.html"])
            expected_header = (
                f'<p class="last-update">{STORY_UPDATE.date().isoformat()} 更新</p>'
            ).encode()
            for name, content in after_docs.items():
                if name.endswith(".html"):
                    self.assertIn(expected_header, content, name)

            # The shared header shows the site date, while work/story metadata
            # keeps its own lower-level update date.
            previous_date = FIRST_RUN.date().isoformat().encode()
            self.assertIn(
                b'<p class="metadata">'
                + previous_date
                + " 更新".encode(),
                after_docs["kaminomori/index.html"],
            )
            self.assertIn(
                b'<p class="chapter-metadata-chapter">'
                + previous_date
                + " 更新".encode(),
                after_docs["kaminomori/1.html"],
            )

    def test_second_run_without_changes_is_byte_identical(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _make_site(root)
            first_docs = root / "first-docs"
            first_history = root / "first-history.csv"
            second_docs = root / "second-docs"
            second_history = root / "second-history.csv"

            generate_site(root, first_docs, first_history, now=FIRST_RUN)
            generate_site(
                root,
                second_docs,
                second_history,
                history_seed_path=first_history,
                newline_reference_dir=first_docs,
                now=STORY_UPDATE,
            )

            self.assertEqual(_files(second_docs), _files(first_docs))
            self.assertEqual(second_history.read_bytes(), first_history.read_bytes())


if __name__ == "__main__":
    unittest.main()
