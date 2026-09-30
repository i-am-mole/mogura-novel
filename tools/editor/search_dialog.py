from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from editor.search import search_manuscripts


class SearchDialog(tk.Toplevel):
    """Modeless search; bounded idle batches keep close/cancel responsive."""

    def __init__(self, app):
        super().__init__(app.window)
        self.app = app
        self.pending = None
        self.iterator = None
        self.hits = {}
        self.title("文字列検索")
        self.geometry("960x520")
        self.minsize(640, 340)
        self.transient(app.window)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        panel = ttk.Frame(self, padding=10)
        panel.pack(fill="both", expand=True)
        row = ttk.Frame(panel)
        row.pack(fill="x")
        ttk.Label(row, text="検索文字列").pack(side="left")
        self.query = ttk.Entry(row, font=app._content_font())
        self.query.pack(side="left", fill="x", expand=True, padx=8)
        self.query.bind("<Return>", self.start)
        self.search_button = ttk.Button(row, text="検索実行", command=self.start)
        self.search_button.pack(side="left")
        ttk.Button(row, text="閉じる", command=self.close).pack(side="left", padx=(6, 0))
        scopes = ttk.Frame(panel)
        scopes.pack(fill="x", pady=8)
        ttk.Label(scopes, text="検索範囲").pack(side="left")
        self.scope = tk.StringVar(self, value="file")
        for value, label in (("file", "①ファイル内"), ("work", "②当該小説内"),
                             ("all", "③すべての小説内")):
            ttk.Radiobutton(scopes, text=label, variable=self.scope,
                            value=value).pack(side="left", padx=8)
        self.target = tk.StringVar(self)
        ttk.Label(panel, textvariable=self.target).pack(anchor="w")
        ttk.Label(panel, text="完全一致・大小文字／全半角を区別・未保存の編集を含む").pack(anchor="w")
        self.status = tk.StringVar(self, value="検索文字列を入力してください。")
        ttk.Label(panel, textvariable=self.status).pack(anchor="w", pady=6)
        frame = ttk.Frame(panel)
        frame.pack(fill="both", expand=True)
        self.results = ttk.Treeview(frame, columns=("file", "number", "position", "context"),
                                    show="headings", selectmode="browse")
        for key, title, width in (("file", "ファイル", 260), ("number", "話数", 60),
                                  ("position", "行:列", 70), ("context", "該当箇所（【一致文字列】）", 500)):
            self.results.heading(key, text=title)
            self.results.column(key, width=width, minwidth=50, stretch=key == "context")
        vertical = ttk.Scrollbar(frame, command=self.results.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.results.xview)
        self.results.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.results.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.results.bind("<ButtonRelease-1>", self.open_clicked)
        self.results.bind("<Return>", self.open_selected)
        self.update_target()
        self.query.focus_set()

    def update_target(self):
        enabled = self.app.can_search()
        self.search_button.configure(state="normal" if enabled else "disabled")
        path = self.app.current_doc.path.relative_to(self.app.repo.private) if enabled else "作品情報または各話を選択してください"
        self.target.set(f"現在の検索対象: {path}")

    def cancel(self):
        if self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
        self.iterator = None

    def close(self):
        self.cancel()
        self.app.search_dialog = None
        self.destroy()

    def start(self, _event=None):
        self.cancel()
        self.results.delete(*self.results.get_children())
        self.hits.clear()
        if not self.app.can_search():
            self.status.set("作品情報または各話を選択してください。")
            return "break"
        query = self.query.get()
        if not query:
            self.status.set("検索文字列を入力してください。")
            return "break"
        try:
            doc = self.app.current_doc
            text = doc.render(self.app._collect()).decode("utf-8-sig")
            self.iterator = search_manuscripts(self.app.repo, doc.path, text, query, self.scope.get())
            self.status.set(f"検索中… 基準: {doc.path.relative_to(self.app.repo.private)}")
            self.pending = self.after(1, self.step)
        except Exception as exc:
            self.status.set(f"検索できません: {exc}")
        return "break"

    def step(self):
        self.pending = None
        try:
            for _ in range(100):
                hit = next(self.iterator)
                if hit is None:
                    break
                iid = self.results.insert("", "end", values=(
                    hit.path.relative_to(self.app.repo.private), hit.number,
                    f"{hit.line}:{hit.column}", hit.context))
                self.hits[iid] = hit
        except StopIteration:
            self.iterator = None
            self.status.set(f"{len(self.hits):,}件 — クリックでファイルを開きます。再検索で更新します。"
                            if self.hits else "該当箇所はありません。")
            return
        except Exception as exc:
            self.iterator = None
            self.results.delete(*self.results.get_children())
            self.hits.clear()
            self.status.set(f"検索できません: {exc}")
            return
        self.pending = self.after(1, self.step)

    def open_clicked(self, event):
        iid = self.results.identify_row(event.y)
        if self.results.identify_region(event.x, event.y) == "cell" and iid in self.hits:
            self.app.open_search_hit(self.hits[iid].path)

    def open_selected(self, _event=None):
        selected = self.results.selection()
        if selected and selected[0] in self.hits:
            self.app.open_search_hit(self.hits[selected[0]].path)
        return "break"
