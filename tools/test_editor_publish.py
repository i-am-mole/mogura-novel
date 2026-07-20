from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from editor.preview import PreviewManager
from publish import _replace_publication, generate_site


class TestPreviewGeneration(unittest.TestCase):
    def test_generation_uses_explicit_destinations(self):
        root = Path(__file__).resolve().parents[1]
        docs_before = {p.relative_to(root / "docs"): p.read_bytes() for p in (root / "docs").rglob("*") if p.is_file()}
        history_before = (root / "data" / "update_history.csv").read_bytes()
        with TemporaryDirectory(dir=root / ".novel-editor" / "test-tmp") as directory:
            target = Path(directory)
            generate_site(
                root,
                target / "first-docs",
                target / "first-history.csv",
                history_seed_path=root / "data" / "update_history.csv",
            )
            generate_site(
                root,
                target / "second-docs",
                target / "second-history.csv",
                history_seed_path=target / "first-history.csv",
            )
            self.assertEqual(
                (target / "first-docs" / "CNAME").read_text(encoding="utf-8").strip(),
                "mogura-novel.com",
            )
            self.assertTrue((target / "first-docs" / "index.html").is_file())
            first_generated = {
                p.relative_to(target / "first-docs"): p.read_bytes()
                for p in (target / "first-docs").rglob("*")
                if p.is_file()
            }
            second_generated = {
                p.relative_to(target / "second-docs"): p.read_bytes()
                for p in (target / "second-docs").rglob("*")
                if p.is_file()
            }
            self.assertEqual(second_generated, first_generated)
            self.assertEqual(
                (target / "second-history.csv").read_bytes(),
                (target / "first-history.csv").read_bytes(),
            )
        docs_after = {p.relative_to(root / "docs"): p.read_bytes() for p in (root / "docs").rglob("*") if p.is_file()}
        self.assertEqual(docs_after, docs_before)
        self.assertEqual((root / "data" / "update_history.csv").read_bytes(), history_before)

    def test_validation_failure_does_not_create_publication(self):
        source_root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(dir=source_root / ".novel-editor" / "test-tmp") as directory:
            root = Path(directory)
            shutil.copytree(source_root / "private", root / "private")
            (root / "private" / "self_intro.md").write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                generate_site(root, root / "out", root / "history.csv")
            self.assertFalse((root / "out").exists())

    def test_preview_server_serves_reload_enabled_html(self):
        root = Path(__file__).resolve().parents[1]
        finished = threading.Event()
        result = []

        def callback(success, message):
            result.append((success, message))
            finished.set()

        manager = PreviewManager(root, callback)
        try:
            manager.build("index.html", open_when_ready=False)
            self.assertTrue(finished.wait(10), "preview generation timed out")
            self.assertTrue(result[-1][0], result[-1][1])
            with urlopen(manager.base_url + "/index.html", timeout=5) as response:
                html = response.read()
            self.assertIn(b"/__novel_editor_revision", html)
        finally:
            manager.close()


class TestPublicationReplacement(unittest.TestCase):
    def test_complete_tree_replaces_stale_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".novel-editor").mkdir()
            (root / "docs" / "work").mkdir(parents=True)
            (root / "docs" / "work" / "3.html").write_text("stale", encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "update_history.csv").write_text("old", encoding="utf-8")
            stage = root / "stage"
            (stage / "docs" / "work").mkdir(parents=True)
            (stage / "docs" / "work" / "1.html").write_text("new", encoding="utf-8")
            (stage / "history.csv").write_text("new-history", encoding="utf-8")
            _replace_publication(root, stage / "docs", stage / "history.csv")
            self.assertFalse((root / "docs" / "work" / "3.html").exists())
            self.assertEqual((root / "docs" / "work" / "1.html").read_text(), "new")
            self.assertEqual((root / "data" / "update_history.csv").read_text(), "new-history")

    def test_failed_install_rolls_back_docs_and_history(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".novel-editor").mkdir()
            (root / "docs").mkdir()
            (root / "docs" / "index.html").write_text("old-docs", encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "update_history.csv").write_text("old-history", encoding="utf-8")
            stage = root / "stage"
            (stage / "docs").mkdir(parents=True)
            (stage / "docs" / "index.html").write_text("new-docs", encoding="utf-8")
            staged_history = stage / "history.csv"
            staged_history.write_text("new-history", encoding="utf-8")

            import publish
            real_replace = publish.os.replace

            def fail_history_install(source, destination):
                if Path(source) == staged_history:
                    raise OSError("simulated install failure")
                return real_replace(source, destination)

            with patch("publish.os.replace", side_effect=fail_history_install):
                with self.assertRaises(OSError):
                    _replace_publication(root, stage / "docs", staged_history)

            self.assertEqual((root / "docs" / "index.html").read_text(), "old-docs")
            self.assertEqual(
                (root / "data" / "update_history.csv").read_text(), "old-history"
            )


if __name__ == "__main__":
    unittest.main()
