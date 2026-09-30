from pathlib import Path
import unittest
from unittest.mock import patch

import tkinter as tk

from editor.app import NovelEditorApp
from editor.widgets import PairListEditor


class TestEditorInteractions(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.app = NovelEditorApp(self.root)
        self.app.window.withdraw()

    def tearDown(self):
        self.app.preview.close()
        self.app.window.destroy()

    def test_ruby_button_uses_last_content_selection_after_focus_moves(self):
        self.app.open_ref(
            ("story", "propeht-philina", "girl-who-was-expected-to-make-miracle")
        )
        content = self.app.field_widgets["content"]
        self.assertIsInstance(content, tk.Text)
        selected = content.get("1.0", "1.2")
        content.tag_add("sel", "1.0", "1.2")
        self.app.last_content_widget = content

        with patch("editor.app.simpledialog.askstring", return_value="よみ"):
            self.app.insert_ruby()

        replacement = f"|{selected}<よみ>"
        self.assertEqual(content.get("1.0", f"1.0+{len(replacement)}c"), replacement)

    def test_content_widgets_default_to_arial_and_can_change(self):
        self.app.open_ref(("work", "kaminomori"))
        title = self.app.field_widgets["title"]
        links = self.app.field_widgets["external links"]
        self.assertIn("Arial", str(title.cget("font")))
        self.assertIsInstance(links, PairListEditor)
        self.assertIn("Arial", str(links.rows[0][1].cget("font")))

        self.app.content_font_var.set("Courier New")
        self.app._apply_content_font()

        self.assertIn("Courier New", str(title.cget("font")))
        self.assertIn("Courier New", str(links.rows[0][1].cget("font")))

    def test_search_activation_and_close(self):
        self.app.show_search()
        self.assertIsNone(self.app.search_dialog)
        self.app.open_ref(("self",))
        self.app.show_search()
        self.assertIsNone(self.app.search_dialog)
        self.app.open_ref(("work", "kaminomori"))
        self.app.show_search()
        dialog = self.app.search_dialog
        self.assertEqual(dialog.scope.get(), "file")
        self.app.show_search()
        self.assertIs(self.app.search_dialog, dialog)
        dialog.query.insert(0, "title")
        dialog.start()
        for _ in range(100):
            if dialog.iterator is None:
                break
            dialog.after_cancel(dialog.pending)
            dialog.step()
        self.assertTrue(dialog.hits)
        dialog.start()
        dialog.close()
        self.assertIsNone(self.app.search_dialog)

    def test_search_navigation_preserves_unsaved_changes_and_honors_cancel(self):
        self.app.open_ref(("work", "kaminomori"))
        title = self.app.field_widgets["title"]
        title.insert(0, "未保存")
        current = self.app.current_doc.path
        self.app.open_search_hit(current)
        self.assertTrue(title.get().startswith("未保存"))
        other = self.app.repo.private / "propeht-philina" / "index.md"
        with patch("editor.app.messagebox.askyesnocancel", return_value=None):
            self.app.open_search_hit(other)
        self.assertEqual(self.app.current_doc.path, current)
        self.assertTrue(title.get().startswith("未保存"))
        with patch("editor.app.messagebox.askyesnocancel", return_value=False):
            self.app.open_search_hit(other)
        self.assertEqual(self.app.current_doc.path, other)

    def test_search_disabled_when_group_selected(self):
        self.app.open_ref(("work", "kaminomori"))
        group = next(iid for iid in self.app.tree.get_children()
                     if iid not in self.app.tree_refs)
        self.app.tree.selection_set(group)
        self.app._tree_selected()
        self.assertFalse(self.app.can_search())
        self.assertIn("disabled", self.app.search_button.state())


if __name__ == "__main__":
    unittest.main()
