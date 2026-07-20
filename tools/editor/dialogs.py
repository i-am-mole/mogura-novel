from __future__ import annotations

import tkinter as tk
from tkinter import ttk, simpledialog


class FormDialog(simpledialog.Dialog):
    def __init__(self, parent, title: str, fields, *, text_fields=(), defaults=None):
        self.fields = fields
        self.text_fields = set(text_fields)
        self.defaults = defaults or {}
        self.widgets = {}
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        first = None
        for row, (key, label) in enumerate(self.fields):
            ttk.Label(master, text=label).grid(row=row, column=0, sticky="nw", padx=6, pady=5)
            if key in self.text_fields:
                widget = tk.Text(master, width=58, height=5, wrap="word", undo=True)
                widget.insert("1.0", self.defaults.get(key, ""))
            else:
                widget = ttk.Entry(master, width=58)
                widget.insert(0, self.defaults.get(key, ""))
            widget.grid(row=row, column=1, sticky="nsew", padx=6, pady=5)
            self.widgets[key] = widget
            if first is None:
                first = widget
        master.columnconfigure(1, weight=1)
        return first

    def apply(self):
        values = {}
        for key, widget in self.widgets.items():
            if isinstance(widget, tk.Text):
                values[key] = widget.get("1.0", "end-1c")
            else:
                values[key] = widget.get()
        self.result = values


def ask_new_work(parent):
    dialog = FormDialog(
        parent,
        "新しい作品",
        [
            ("slug", "work-slug"),
            ("title", "タイトル"),
            ("tags", "タグ（- タグ名）"),
            ("status", "連載ステータス"),
            ("outline", "あらすじ"),
        ],
        text_fields={"tags", "outline"},
        defaults={"tags": "- 一次創作", "status": "連載中"},
    )
    return dialog.result


def ask_new_story(parent):
    dialog = FormDialog(
        parent,
        "新しい話",
        [
            ("slug", "episode-slug"),
            ("title", "タイトル"),
            ("number", "話数番号"),
            ("content", "本文"),
        ],
        text_fields={"content"},
        defaults={"number": "0"},
    )
    return dialog.result
