from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlsplit
import mimetypes
import threading
import traceback
import uuid
import webbrowser

from publish import generate_site


RELOAD_SCRIPT = b"""<script>
(function () {
  let revision = null;
  async function checkRevision() {
    try {
      const response = await fetch('/__novel_editor_revision', {cache: 'no-store'});
      const current = await response.text();
      if (revision === null) revision = current;
      else if (current !== revision) location.reload();
    } catch (_) {}
  }
  setInterval(checkRevision, 750);
  checkRevision();
})();
</script>"""


class PreviewManager:
    def __init__(
        self,
        root: Path,
        callback: Callable[[bool, str], None],
    ) -> None:
        self.root = Path(root).resolve()
        self.state = self.root / ".novel-editor"
        self.callback = callback
        self.current_dir: Optional[Path] = None
        self.revision = 0
        self.server: Optional[ThreadingHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.build_lock = threading.Lock()
        self.browser_opened = False

    def start_server(self) -> None:
        if self.server is not None:
            return
        manager = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *args) -> None:
                return

            def do_GET(self) -> None:
                if self.path.startswith("/__novel_editor_revision"):
                    data = str(manager.revision).encode("ascii")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=ascii")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                current = manager.current_dir
                if current is None:
                    self.send_error(503, "Preview is not ready")
                    return
                relative = unquote(urlsplit(self.path).path).lstrip("/") or "index.html"
                candidate = (current / relative).resolve()
                if current.resolve() not in candidate.parents and candidate != current.resolve():
                    self.send_error(403)
                    return
                if candidate.is_dir():
                    candidate = candidate / "index.html"
                if not candidate.is_file():
                    self.send_error(404)
                    return
                data = candidate.read_bytes()
                mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                if candidate.suffix.lower() == ".html":
                    marker = b"</body>"
                    data = data.replace(marker, RELOAD_SCRIPT + marker, 1)
                    mime = "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server_thread = threading.Thread(
            target=self.server.serve_forever, name="novel-preview-server", daemon=True
        )
        self.server_thread.start()

    @property
    def base_url(self) -> str:
        self.start_server()
        assert self.server is not None
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def build(self, relative_page: str = "index.html", *, open_when_ready: bool = True) -> None:
        thread = threading.Thread(
            target=self._build_worker,
            args=(relative_page, open_when_ready),
            name="novel-preview-builder",
            daemon=True,
        )
        thread.start()

    def _build_worker(self, relative_page: str, open_when_ready: bool) -> None:
        if not self.build_lock.acquire(blocking=False):
            self.callback(False, "プレビュー生成は既に実行中です。")
            return
        try:
            build_root = self.state / "preview-builds" / uuid.uuid4().hex
            public = build_root / "docs"
            history = build_root / "update_history.csv"
            generate_site(
                self.root,
                public,
                history,
                history_seed_path=self.root / "data" / "update_history.csv",
            )
            self.current_dir = public
            self.revision += 1
            self.start_server()
            page = relative_page.replace("\\", "/").lstrip("/")
            if open_when_ready and not self.browser_opened:
                webbrowser.open(f"{self.base_url}/{page}")
                self.browser_opened = True
            self.callback(True, "プレビューを更新しました。")
        except Exception:
            self.callback(False, traceback.format_exc())
        finally:
            self.build_lock.release()

    def open_page(self, relative_page: str) -> None:
        if self.current_dir is None:
            self.build(relative_page, open_when_ready=True)
            return
        page = relative_page.replace("\\", "/").lstrip("/")
        webbrowser.open(f"{self.base_url}/{page}")
        self.browser_opened = True

    def close(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
