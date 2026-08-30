from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import tkinter as tk

from editor.dialogs import FormDialog


class TestFormDialog(unittest.TestCase):
    def test_return_in_multiline_field_does_not_submit_dialog(self):
        dialog = Mock()
        event = SimpleNamespace(widget=Mock(spec=tk.Text))

        result = FormDialog._return_pressed(dialog, event)

        self.assertEqual(result, "break")
        dialog.ok.assert_not_called()

    def test_return_in_single_line_field_submits_dialog(self):
        dialog = Mock()
        event = SimpleNamespace(widget=Mock(spec=tk.Entry))

        result = FormDialog._return_pressed(dialog, event)

        self.assertEqual(result, "break")
        dialog.ok.assert_called_once_with(event)


if __name__ == "__main__":
    unittest.main()
