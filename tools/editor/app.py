from __future__ import annotations

from pathlib import Path
from typing import Optional
import re
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from editor.dialogs import ask_new_story, ask_new_work
from editor.document import DocumentError, RoundTripDocument
from editor.preview import PreviewManager
from editor.repository import (
    Repository,
    RepositoryError,
    validate_story_fields,
    validate_work_fields,
)
from editor.widgets import PairListEditor


class NovelEditorApp:
    def __init__(self, root: Path):
        self.repo = Repository(root)
        self.window = tk.Tk()
        self.window.title("もぐらノベル エディタ")
        self.window.geometry("1180x780")
        self.window.minsize(840, 560)
        self.current_ref: Optional[tuple[str, ...]] = None
        self.current_iid: Optional[str] = None
        self.current_doc: Optional[RoundTripDocument] = None
        self.field_widgets: dict[str, tk.Widget] = {}
        self.ruby_widgets: set[tk.Widget] = set()
        self.tree_refs: dict[str, tuple[str, ...]] = {}
        self.suppress_tree_event = False
        self.status_var = tk.StringVar(value="準備完了")
        self.count_var = tk.StringVar(value="文字数: —")
        self.preview = PreviewManager(self.repo.root, self._preview_callback)
        self._build_ui()
        self.refresh_tree()
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)
        self.window.bind_all("<Control-s>", lambda _event: self.save_current())
        self.window.bind_all("<Control-Shift-R>", lambda _event: self.insert_ruby())

    def run(self) -> None:
        self.window.mainloop()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.window, padding=(6, 5))
        toolbar.pack(fill="x")
        buttons = [
            ("新しい作品", self.new_work),
            ("新しい話", self.new_story),
            ("名前変更", self.rename_story),
            ("削除", self.delete_story),
            ("削除を元に戻す", self.restore_story),
            ("ルビ", self.insert_ruby),
            ("保存", self.save_current),
            ("プレビュー", self.open_preview),
        ]
        for label, command in buttons:
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=2)

        paned = ttk.Panedwindow(self.window, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned, width=240, padding=(6, 0, 3, 3))
        right = ttk.Frame(paned, padding=(8, 0, 8, 3))
        paned.add(left, weight=0)
        paned.add(right, weight=1)

        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._tree_selected)

        self.editor = ttk.Frame(right)
        self.editor.pack(fill="both", expand=True)
        self.editor.columnconfigure(1, weight=1)
        self.editor.rowconfigure(99, weight=1)

        status = ttk.Frame(self.window, padding=(7, 4))
        status.pack(fill="x")
        ttk.Label(status, textvariable=self.status_var).pack(side="left")
        ttk.Label(status, textvariable=self.count_var).pack(side="right")

    def refresh_tree(self, select_ref: Optional[tuple[str, ...]] = None) -> None:
        self.suppress_tree_event = True
        self.tree.delete(*self.tree.get_children())
        self.tree_refs.clear()
        self._insert_tree("", "self", "自己紹介", ("self",))
        novels_root = self.tree.insert("", "end", text="小説一覧", open=True)
        for slug in self.repo.work_slugs():
            try:
                document = self.repo.load_work(slug)
                title = document.values().get("title", slug).strip() or slug
            except Exception:
                title = slug
            work_iid = self.tree.insert(
                novels_root, "end", text=f"{title} [{slug}]", open=True
            )
            self._insert_tree(work_iid, f"work:{slug}", "作品情報", ("work", slug))
            novel = self.repo.load_novel(slug)
            if isinstance(novel, list):
                for path in sorted((self.repo.private / slug).glob("*.md")):
                    if path.name != "index.md" and not path.name.startswith("_"):
                        self._insert_tree(
                            work_iid,
                            f"story:{slug}:{path.stem}",
                            path.stem,
                            ("story", slug, path.stem),
                        )
                continue
            ordered = novel.get_stories_ordered()
            if isinstance(ordered, dict):
                for chapter, stories in ordered.items():
                    boundary = novel.chapters[chapter] if novel.chapters else ""
                    chapter_iid = self.tree.insert(
                        work_iid, "end", text=f"{chapter}（～{boundary}）", open=True
                    )
                    for story in stories:
                        self._insert_story_node(chapter_iid, slug, story)
            else:
                for story in novel.stories:
                    self._insert_story_node(work_iid, slug, story)

        if select_ref:
            for iid, ref in self.tree_refs.items():
                if ref == select_ref:
                    self.tree.selection_set(iid)
                    self.tree.focus(iid)
                    self.tree.see(iid)
                    self.current_iid = iid
                    break
        self.suppress_tree_event = False

    def _insert_story_node(self, parent: str, work_slug: str, story) -> None:
        self._insert_tree(
            parent,
            f"story:{work_slug}:{story.path.stem}",
            f"{story.number}: {story.title}",
            ("story", work_slug, story.path.stem),
        )

    def _insert_tree(self, parent: str, iid: str, text: str, ref: tuple[str, ...]) -> None:
        inserted = self.tree.insert(parent, "end", iid=iid, text=text)
        self.tree_refs[inserted] = ref

    def _tree_selected(self, _event=None) -> None:
        if self.suppress_tree_event:
            return
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        ref = self.tree_refs.get(iid)
        if ref is None:
            return
        if self.current_ref and ref != self.current_ref and not self._confirm_abandon():
            if self.current_iid:
                self.suppress_tree_event = True
                self.tree.selection_set(self.current_iid)
                self.suppress_tree_event = False
            return
        self.current_iid = iid
        self.open_ref(ref)

    def open_ref(self, ref: tuple[str, ...]) -> None:
        try:
            if ref[0] == "self":
                document = self.repo.load_self_intro()
                self._show_self_intro(document)
            elif ref[0] == "work":
                document = self.repo.load_work(ref[1])
                self._show_work(document, ref[1])
            else:
                document = self.repo.load_story(ref[1], ref[2])
                self._show_story(document, ref[1], ref[2])
            self.current_ref = ref
            self.current_doc = document
            self.status_var.set(str(document.path.relative_to(self.repo.root)))
            self._content_changed()
        except Exception as exc:
            messagebox.showerror("読み込みエラー", str(exc), parent=self.window)

    def _clear_editor(self) -> None:
        for child in self.editor.winfo_children():
            child.destroy()
        self.field_widgets.clear()
        self.ruby_widgets.clear()

    def _add_entry(self, row: int, key: str, label: str, value: str, *, ruby=False) -> int:
        ttk.Label(self.editor, text=label).grid(row=row, column=0, sticky="nw", padx=4, pady=5)
        widget = ttk.Entry(self.editor)
        widget.insert(0, value)
        widget.grid(row=row, column=1, sticky="ew", padx=4, pady=5)
        widget.bind("<KeyRelease>", self._content_changed)
        self.field_widgets[key] = widget
        if ruby:
            self.ruby_widgets.add(widget)
        return row + 1

    def _add_text(
        self, row: int, key: str, label: str, value: str, *, height=6, ruby=False, expand=False
    ) -> int:
        ttk.Label(self.editor, text=label).grid(row=row, column=0, sticky="nw", padx=4, pady=5)
        frame = ttk.Frame(self.editor)
        frame.grid(row=row, column=1, sticky="nsew", padx=4, pady=5)
        text = tk.Text(frame, height=height, wrap="word", undo=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.insert("1.0", value)
        text.edit_modified(False)
        text.bind("<KeyRelease>", self._content_changed)
        def modified(_event, target=text):
            if target.edit_modified():
                target.edit_modified(False)
                self._content_changed()
        text.bind("<<Modified>>", modified)
        text.bind("<<Paste>>", lambda _e: self.window.after_idle(self._content_changed))
        text.bind("<<Cut>>", lambda _e: self.window.after_idle(self._content_changed))
        self.field_widgets[key] = text
        if ruby:
            self.ruby_widgets.add(text)
        if expand:
            self.editor.rowconfigure(row, weight=1)
        return row + 1

    def _add_pair_table(
        self,
        row: int,
        key: str,
        label: str,
        value: str,
        *,
        kind: str,
        first_label: str,
        second_label: str,
    ) -> int:
        ttk.Label(self.editor, text=label).grid(
            row=row, column=0, sticky="nw", padx=4, pady=5
        )
        widget = PairListEditor(
            self.editor,
            first_label=first_label,
            second_label=second_label,
            raw_value=value,
            kind=kind,
            on_change=self._content_changed,
        )
        widget.grid(row=row, column=1, sticky="ew", padx=4, pady=5)
        self.field_widgets[key] = widget
        self.ruby_widgets.update(widget.ruby_widgets)
        return row + 1

    def _show_self_intro(self, document: RoundTripDocument) -> None:
        self._clear_editor()
        ttk.Label(self.editor, text="自己紹介", font=("Yu Gothic UI", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(2, 8)
        )
        self._add_text(1, "__raw__", "Markdown", document.text, height=28, ruby=True, expand=True)

    def _show_work(self, document: RoundTripDocument, slug: str) -> None:
        self._clear_editor()
        values = document.values()
        ttk.Label(
            self.editor, text=f"作品情報 [{slug}]", font=("Yu Gothic UI", 14, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(2, 8))
        row = self._add_entry(1, "title", "タイトル", values.get("title", ""), ruby=True)
        row = self._add_text(row, "tags", "タグ（1行1件）", values.get("tags", ""), height=4)
        ttk.Label(self.editor, text="連載ステータス").grid(
            row=row, column=0, sticky="nw", padx=4, pady=5
        )
        status = ttk.Combobox(
            self.editor, values=("連載中", "完結済", "更新停止"), state="readonly"
        )
        status.set(values.get("status", ""))
        status.grid(row=row, column=1, sticky="ew", padx=4, pady=5)
        status.bind("<<ComboboxSelected>>", self._content_changed)
        self.field_widgets["status"] = status
        row += 1
        row = self._add_text(row, "outline", "あらすじ", values.get("outline", ""), height=8, ruby=True)
        row = self._add_pair_table(
            row,
            "external links",
            "外部リンク",
            values.get("external links", ""),
            kind="links",
            first_label="表示名",
            second_label="URL",
        )
        self._add_pair_table(
            row,
            "chapters",
            "章構成",
            values.get("chapters", ""),
            kind="chapters",
            first_label="章タイトル",
            second_label="境界番号",
        )

    def _show_story(
        self, document: RoundTripDocument, work_slug: str, episode_slug: str
    ) -> None:
        self._clear_editor()
        values = document.values()
        ttk.Label(
            self.editor,
            text=f"各話 [{work_slug}/{episode_slug}.md]",
            font=("Yu Gothic UI", 14, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(2, 8))
        row = self._add_entry(1, "title", "タイトル", values.get("title", ""), ruby=True)
        row = self._add_entry(row, "number", "話数番号", values.get("number", ""))
        self._add_text(
            row, "content", "本文", values.get("content", ""), height=28, ruby=True, expand=True
        )

    def _widget_value(self, widget: tk.Widget) -> str:
        if hasattr(widget, "get_value"):
            return widget.get_value()
        if isinstance(widget, tk.Text):
            return widget.get("1.0", "end-1c")
        return widget.get()

    def _collect(self) -> dict[str, Optional[str]]:
        values: dict[str, Optional[str]] = {
            key: self._widget_value(widget) for key, widget in self.field_widgets.items()
        }
        if self.current_ref and self.current_ref[0] == "work":
            for optional in ("external links", "chapters"):
                if not (values.get(optional) or "").strip():
                    values[optional] = None
        return values

    def _content_changed(self, _event=None) -> None:
        if not self.current_doc:
            self.count_var.set("文字数: —")
            return
        try:
            values = self._collect()
            if self.current_ref and self.current_ref[0] == "self":
                raw = str(values.get("__raw__") or "")
                count = self.current_doc.character_count(raw_text=raw)
                dirty = self.current_doc.render_raw(raw) != self.current_doc.original_bytes
            else:
                count = self.current_doc.character_count(updates=values)
                dirty = self.current_doc.render(values) != self.current_doc.original_bytes
            self.count_var.set(f"文字数: {count:,}（改行を除く・ファイル全体）")
            suffix = " *" if dirty else ""
            self.window.title(f"もぐらノベル エディタ{suffix}")
        except Exception:
            self.count_var.set("文字数: 計算できません")

    def is_dirty(self) -> bool:
        if not self.current_doc or not self.current_ref:
            return False
        values = self._collect()
        if self.current_ref[0] == "self":
            return self.current_doc.render_raw(str(values.get("__raw__") or "")) != self.current_doc.original_bytes
        return self.current_doc.render(values) != self.current_doc.original_bytes

    def _validate_current(self, values: dict[str, Optional[str]]) -> None:
        assert self.current_ref is not None
        clean = {key: value for key, value in values.items() if value is not None}
        if self.current_ref[0] == "self":
            raw = str(values.get("__raw__") or "")
            if not raw.strip():
                raise RepositoryError("自己紹介は空にできません。")
            if re.search(r"(?m)^\s*# ", raw):
                raise RepositoryError("自己紹介ではH1見出しを使用できません。")
        elif self.current_ref[0] == "work":
            validate_work_fields(clean)
        else:
            validate_story_fields(clean)
            self.repo.validate_story_update(
                self.current_ref[1], self.current_ref[2], clean
            )

    def save_current(self) -> bool:
        if not self.current_doc or not self.current_ref:
            return True
        try:
            values = self._collect()
            self._validate_current(values)
            if self.current_ref[0] == "self":
                changed, _backup = self.current_doc.save(
                    self.repo.state, raw_text=str(values.get("__raw__") or "")
                )
            else:
                changed, _backup = self.current_doc.save(self.repo.state, updates=values)
            ref = self.current_ref
            self.refresh_tree(select_ref=ref)
            self.open_ref(ref)
            self.status_var.set("保存しました。プレビューを生成しています…" if changed else "変更はありません。プレビューを確認します…")
            self.preview.build(self._preview_page(ref), open_when_ready=True)
            return True
        except Exception as exc:
            messagebox.showerror("保存できません", str(exc), parent=self.window)
            self.status_var.set("保存エラー")
            return False

    def _confirm_abandon(self) -> bool:
        if not self.is_dirty():
            return True
        answer = messagebox.askyesnocancel(
            "未保存の変更",
            "変更が保存されていません。保存しますか？",
            parent=self.window,
        )
        if answer is None:
            return False
        if answer:
            return self.save_current()
        return True

    def new_work(self) -> None:
        if not self._confirm_abandon():
            return
        values = ask_new_work(self.window)
        if not values:
            return
        try:
            document = self.repo.new_work_document(
                values["slug"],
                title=values["title"],
                tags=values["tags"],
                status=values["status"],
                outline=values["outline"],
            )
            document.save(self.repo.state, updates={})
            ref = ("work", values["slug"].strip())
            self.refresh_tree(select_ref=ref)
            self.open_ref(ref)
            self.preview.build(self._preview_page(ref), open_when_ready=True)
        except Exception as exc:
            messagebox.showerror("作品を作成できません", str(exc), parent=self.window)

    def new_story(self) -> None:
        if not self.current_ref or self.current_ref[0] == "self":
            messagebox.showinfo("新しい話", "先に対象作品を選択してください。", parent=self.window)
            return
        if not self._confirm_abandon():
            return
        work_slug = self.current_ref[1]
        values = ask_new_story(self.window)
        if not values:
            return
        try:
            document = self.repo.new_story_document(
                work_slug,
                values["slug"],
                title=values["title"],
                number=values["number"],
                content=values["content"],
            )
            document.save(self.repo.state, updates={})
            ref = ("story", work_slug, values["slug"].strip())
            self.refresh_tree(select_ref=ref)
            self.open_ref(ref)
            self.preview.build(self._preview_page(ref), open_when_ready=True)
        except Exception as exc:
            messagebox.showerror("話を作成できません", str(exc), parent=self.window)

    def rename_story(self) -> None:
        if not self.current_ref or self.current_ref[0] != "story":
            messagebox.showinfo("名前変更", "名前を変更する話を選択してください。", parent=self.window)
            return
        if not self._confirm_abandon():
            return
        work, old = self.current_ref[1], self.current_ref[2]
        new = simpledialog.askstring(
            "episode-slugの変更", "新しいepisode-slug", initialvalue=old, parent=self.window
        )
        if not new or new.strip() == old:
            return
        try:
            self.repo.rename_story(work, old, new)
            ref = ("story", work, new.strip())
            self.refresh_tree(select_ref=ref)
            self.open_ref(ref)
            self.status_var.set("話の名前と更新履歴キーを変更しました。")
            self.preview.build(self._preview_page(ref), open_when_ready=True)
        except Exception as exc:
            messagebox.showerror("名前変更できません", str(exc), parent=self.window)

    def delete_story(self) -> None:
        if not self.current_ref or self.current_ref[0] != "story":
            messagebox.showinfo("削除", "削除する話を選択してください。", parent=self.window)
            return
        if not self._confirm_abandon():
            return
        work, episode = self.current_ref[1], self.current_ref[2]
        path = self.repo.private / work / f"{episode}.md"
        if not messagebox.askyesno(
            "話を削除",
            f"次の話をごみ箱へ移動します。\n\n作品: {work}\n話: {episode}\n対象: {path}\n\n続行しますか？",
            parent=self.window,
        ):
            return
        try:
            self.repo.delete_story(work, episode)
            ref = ("work", work)
            self.current_doc = None
            self.current_ref = None
            self.refresh_tree(select_ref=ref)
            self.open_ref(ref)
            self.status_var.set("話を削除しました。「削除を元に戻す」で復元できます。")
            self.preview.build(self._preview_page(ref), open_when_ready=True)
        except Exception as exc:
            messagebox.showerror("削除できません", str(exc), parent=self.window)

    def restore_story(self) -> None:
        try:
            restored = self.repo.restore_last_deleted()
            ref = ("story", restored.parent.name, restored.stem)
            self.refresh_tree(select_ref=ref)
            self.open_ref(ref)
            self.status_var.set("削除した話と更新履歴を復元しました。")
            self.preview.build(self._preview_page(ref), open_when_ready=True)
        except Exception as exc:
            messagebox.showerror("復元できません", str(exc), parent=self.window)

    def insert_ruby(self) -> None:
        widget = self.window.focus_get()
        pair_ruby = any(
            isinstance(editor, PairListEditor) and widget in editor.ruby_widgets
            for editor in self.field_widgets.values()
        )
        if widget not in self.ruby_widgets and not pair_ruby:
            self.status_var.set("この項目ではルビ入力を使用できません。")
            self.window.bell()
            return
        try:
            if isinstance(widget, tk.Text):
                ranges = widget.tag_ranges("sel")
                if not ranges:
                    raise ValueError
                start, end = ranges
                selected = widget.get(start, end)
            else:
                if not widget.selection_present():
                    raise ValueError
                start, end = widget.index("sel.first"), widget.index("sel.last")
                selected = widget.get()[start:end]
        except (tk.TclError, ValueError):
            self.status_var.set("ルビを振る対象文字列を選択してください。")
            self.window.bell()
            return
        if any(char in selected for char in ("\n", "\r", "|", "<")):
            messagebox.showerror("ルビ入力", "選択範囲に改行、|、< は使用できません。", parent=self.window)
            return
        ruby = simpledialog.askstring("ルビ入力", f"「{selected}」のルビ", parent=self.window)
        if ruby is None:
            return
        if not ruby or any(char in ruby for char in ("\n", "\r", ">")):
            messagebox.showerror("ルビ入力", "ルビは空にできず、改行と > は使用できません。", parent=self.window)
            return
        replacement = f"|{selected}<{ruby}>"
        if isinstance(widget, tk.Text):
            widget.delete(start, end)
            widget.insert(start, replacement)
        else:
            widget.delete(start, end)
            widget.insert(start, replacement)
        self._content_changed()

    def _preview_page(self, ref: tuple[str, ...]) -> str:
        if ref[0] == "self":
            return "index.html"
        if ref[0] == "work":
            return f"{ref[1]}/index.html"
        novel = self.repo.load_novel(ref[1])
        if not isinstance(novel, list):
            for index, story in enumerate(novel.stories, start=1):
                if story.path.stem == ref[2]:
                    return f"{ref[1]}/{index}.html"
        return f"{ref[1]}/index.html"

    def open_preview(self) -> None:
        if not self.current_ref:
            self.preview.open_page("index.html")
            return
        if self.is_dirty():
            self.save_current()
            return
        self.preview.open_page(self._preview_page(self.current_ref))

    def _preview_callback(self, success: bool, message: str) -> None:
        def update():
            if success:
                self.status_var.set(message)
            else:
                self.status_var.set("プレビュー更新に失敗しました。直前の表示を維持します。")
                messagebox.showerror("プレビューエラー", message, parent=self.window)
        self.window.after(0, update)

    def _on_close(self) -> None:
        if not self._confirm_abandon():
            return
        self.preview.close()
        self.window.destroy()
