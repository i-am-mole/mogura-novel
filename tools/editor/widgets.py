from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk


class PairListEditor(ttk.Frame):
    """Small two-column editor used for links and chapter boundaries."""

    def __init__(
        self,
        parent,
        *,
        first_label: str,
        second_label: str,
        raw_value: str,
        kind: str,
        on_change,
        register_widget,
    ):
        super().__init__(parent)
        self.kind = kind
        self.raw_value = raw_value
        self.on_change = on_change
        self.register_widget = register_widget
        self.rows: list[tuple[ttk.Frame, ttk.Entry, ttk.Entry]] = []
        self.ruby_widgets: set[tk.Widget] = set()
        ttk.Label(self, text=first_label).grid(row=0, column=0, sticky="w", padx=2)
        ttk.Label(self, text=second_label).grid(row=0, column=1, sticky="w", padx=2)
        self.rows_frame = ttk.Frame(self)
        self.rows_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        self.rows_frame.columnconfigure(0, weight=1)
        ttk.Button(self, text="追加", command=self.add_row).grid(
            row=2, column=0, sticky="w", padx=2, pady=(4, 0)
        )
        self.columnconfigure(0, weight=1)
        parsed = self._parse(raw_value)
        self.initial_pairs = tuple(parsed)
        for first, second in parsed:
            self.add_row(first, second, notify=False)

    def _parse(self, raw: str) -> list[tuple[str, str]]:
        result = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            if self.kind == "links":
                match = re.fullmatch(r"\s*- \[(.*)\]\((.*)\)\s*", line)
                result.append(match.groups() if match else (line, ""))
            else:
                result.append(tuple(part.strip() for part in line.split(":", 1)) if ":" in line else (line, ""))
        return result

    def add_row(self, first: str = "", second: str = "", *, notify: bool = True) -> None:
        row_frame = ttk.Frame(self.rows_frame)
        row_frame.pack(fill="x", pady=2)
        first_entry = ttk.Entry(row_frame)
        second_entry = ttk.Entry(row_frame)
        first_entry.insert(0, first)
        second_entry.insert(0, second)
        first_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        second_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(
            row_frame,
            text="削除",
            command=lambda: self.remove_row(row_frame),
        ).pack(side="left")
        first_entry.bind("<KeyRelease>", self.on_change)
        second_entry.bind("<KeyRelease>", self.on_change)
        self.rows.append((row_frame, first_entry, second_entry))
        first_is_ruby = self.kind == "chapters"
        self.register_widget(first_entry, ruby=first_is_ruby)
        self.register_widget(second_entry, ruby=False)
        if first_is_ruby:
            self.ruby_widgets.add(first_entry)
        if notify:
            self.on_change()

    def remove_row(self, row_frame: ttk.Frame) -> None:
        for index, (frame, first, _second) in enumerate(self.rows):
            if frame == row_frame:
                self.ruby_widgets.discard(first)
                self.rows.pop(index)
                frame.destroy()
                self.on_change()
                return

    def get_value(self) -> str:
        pairs = tuple((first.get(), second.get()) for _frame, first, second in self.rows)
        if pairs == self.initial_pairs:
            return self.raw_value
        lines = []
        for first, second in pairs:
            if not first.strip() and not second.strip():
                continue
            if self.kind == "links":
                lines.append(f"- [{first.strip()}]({second.strip()})")
            else:
                lines.append(f"{first.strip()}: {second.strip()}")
        return "\n".join(lines)
