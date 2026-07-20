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


if __name__ == "__main__":
    unittest.main()
