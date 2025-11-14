# tools/publish.py
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
import html
from pathlib import Path
from typing import Dict, Tuple, Optional, List

from markdown import markdown as md_to_html

import md
from story import Story
from novel import Novel
from toppage import TopPage

# ====== 設定 ======
# 公開ドメイン（絶対URLが必要な OGP 用）。未設定でも動くが、SNSカード検証には設定推奨。
SITE_ORIGIN = "https://www.mogura-novel.com"  # 例: "https://novel.example.com"
# X (Twitter) アカウント
TWITTER_HANDLE = "@I_am_a_mole1"


# ====== 更新履歴 (CSV) ======
History = Dict[str, Tuple[str, str]]  # path -> (hash, iso_timestamp)


def load_history(path: Path) -> History:
    if not path.is_file():
        return {}
    hist: History = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) != 3:
                continue
            filename, h, ts = row
            hist[filename] = (h, ts)
    return hist


def save_history(path: Path, history: History) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    items = sorted(history.items(), key=lambda x: x[0])
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for filename, (h, ts) in items:
            writer.writerow([filename, h, ts])


def update_history_entry(
    history: History,
    key: Path,
    new_hash: str,
    now_iso: str,
) -> str:
    key_str = str(key).replace("\\", "/")
    old = history.get(key_str)
    if old is None or old[0] != new_hash:
        history[key_str] = (new_hash, now_iso)
        return now_iso
    else:
        return old[1]


def parse_date_from_iso(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return ""
    return dt.date().isoformat()


# ====== HTML 共通 ======
def html_escape(s: str) -> str:
    return html.escape(s, quote=True)


def render_site_header(root_prefix: str, last_updated_date: str) -> str:
    return f"""<header class="site-header">
    <div class="site-header-content">
        <h1 class="site-name"><a href="{root_prefix}index.html">もぐらノベル</a></h1>
        <p class="last-update">{html_escape(last_updated_date)} 更新</p>
    </div>
</header>"""


def apply_ruby_and_markdown(text: str) -> str:
    return md_to_html(md.to_html_ruby(text))


def truncate_outline(outline: str, limit: int = 150) -> str:
    s = outline.replace("\n", " ").strip()
    if len(s) <= limit:
        # ルビも含むと厳密には文字数が変わるが、概ね問題ない想定
        return apply_ruby_and_markdown(s)
    else:
        # warning: ルビタグを途中で切る可能性あり
        truncated = s[:limit] + "..."
        return apply_ruby_and_markdown(truncated)

def parse_tags(tags_md: str) -> str:
    tags: List[str] = []
    for line in tags_md.splitlines():
        line = line.strip()
        if line.startswith("- "):
            tag = line[2:].strip()
            if tag:
                tags.append(tag)
    return " | ".join(tags)


# ====== ステータス・バッジ（楕円囲みテキスト） ======
def render_status_badge(status: str) -> str:
    status = status.strip()
    cls = "status-other"
    if status == "連載中":
        cls = "status-ongoing"
    elif status == "完結済":
        cls = "status-complete"
    elif status == "更新停止":
        cls = "status-paused"
    return f'<span class="status-badge {cls}">{html_escape(status)}</span>'


# ====== OGP / favicon 用ユーティリティ ======
def absolute_url(path_from_root: str) -> Optional[str]:
    if SITE_ORIGIN:
        return SITE_ORIGIN.rstrip("/") + path_from_root
    return None


def choose_og_image(novel_dirname: Optional[str]) -> str:
    """
    /public をサイトルートとみなし、/ogp/<novel>.png → /ogp/default.png
    → /apple-touch-icon.png → /favicon-32x32.png の順で存在するものを返す。
    返り値は「/」から始まるサイトルート相対パス。
    """
    root = Path(__file__).resolve().parents[1]
    public = root / "public"
    candidates = []
    if novel_dirname:
        candidates.append(public / "ogp" / f"{novel_dirname}.png")
    candidates.extend([
        public / "ogp" / "default.png",
        public / "apple-touch-icon.png",
        public / "favicon-32x32.png",
    ])
    for c in candidates:
        if c.is_file():
            return "/" + c.relative_to(public).as_posix()
    return "/favicon-32x32.png"


def build_head(
    title_text: str,
    root_prefix: str,
    *,
    og_title: str,
    og_desc: str,
    og_type: str,
    og_image_path_from_root: str,
    og_url_path_from_root: Optional[str] = None
) -> str:
    """
    すべてのページの <head> を統一生成。
    - favicon
    - OGP + Twitter (X)
    - CSS（root_prefix で相対制御）
    """
    title_html = html_escape(title_text)

    og_url_abs = absolute_url(og_url_path_from_root) if og_url_path_from_root else None
    og_image_abs = absolute_url(og_image_path_from_root) or og_image_path_from_root
    meta_og_url = f'\n    <meta property="og:url" content="{html_escape(og_url_abs)}">' if og_url_abs else ""

    return f"""<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_html}</title>

    <!-- favicon -->
    <link rel="icon" href="/favicon.ico" sizes="any">
    <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png">
    <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">

    <!-- OGP -->
    <meta property="og:site_name" content="もぐらノベル">
    <meta property="og:title" content="{html_escape(og_title)}">
    <meta property="og:description" content="{html_escape(og_desc)}">
    <meta property="og:type" content="{html_escape(og_type)}">
    <meta property="og:image" content="{html_escape(og_image_abs)}">{meta_og_url}
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:site" content="{html_escape(TWITTER_HANDLE)}">

    <link rel="stylesheet" href="{root_prefix}css/style.css">
</head>"""


# ====== SSG 本体 ======
@dataclass
class NovelContext:
    novel: Novel
    private_dir: Path
    public_dir: Path
    last_updated_iso: str
    story_updated_iso: Dict[int, str]  # story.number -> ts
    index_to_story: Dict[int, Story]   # 1-origin 表示順 -> Story


def build_top_page(
    root: Path,
    tp: TopPage,
    history: History,
    now_iso: str,
) -> Tuple[str, List[NovelContext], str]:
    # TopPage（自己紹介）の更新履歴
    top_rel = tp.path
    top_hash = tp.hash()
    top_ts_iso = update_history_entry(history, top_rel, top_hash, now_iso)

    novel_contexts: List[NovelContext] = []
    for novel, ndir in zip(tp.novels, tp.novel_directories):
        ndir = Path(ndir)
        n_hash = novel.hash()
        n_ts_iso = update_history_entry(history, novel.path, n_hash, now_iso)

        story_updated_iso: Dict[int, str] = {}
        index_to_story: Dict[int, Story] = {}
        for idx, s in enumerate(novel.stories, start=1):
            s_ts_iso = update_history_entry(history, s.path, s.hash(), now_iso)
            story_updated_iso[s.number] = s_ts_iso
            index_to_story[idx] = s

        all_ts = [n_ts_iso] + list(story_updated_iso.values())
        n_last_iso = max(all_ts) if all_ts else n_ts_iso

        nc = NovelContext(
            novel=novel,
            private_dir=ndir,
            public_dir=root / "public" / ndir.name,
            last_updated_iso=n_last_iso,
            story_updated_iso=story_updated_iso,
            index_to_story=index_to_story,
        )
        novel_contexts.append(nc)

    site_last_date = parse_date_from_iso(top_ts_iso) or datetime.now().date().isoformat()

    header_html = render_site_header("", site_last_date)

    # ---- head（favicon / OGP / X）----
    og_desc = "オリジナル小説を公開する個人サイト。連載中・完結済の作品を掲載。"
    og_img = choose_og_image(None)
    head_html = build_head(
        title_text="もぐらノベル",
        root_prefix="",
        og_title="もぐらノベル",
        og_desc=og_desc,
        og_type="website",
        og_image_path_from_root=og_img,
        og_url_path_from_root="/",
    )

    # 自己紹介
    self_intro_html = apply_ruby_and_markdown(tp.self_intro)

    # 小説一覧
    novel_items: List[str] = []
    for nc in novel_contexts:
        n = nc.novel
        n_pub_dir_name = nc.public_dir.name
        title_html = md.to_html_ruby(n.title)
        tags_str = parse_tags(n.tags)
        outline_summary = truncate_outline(n.outline)
        last_date = parse_date_from_iso(nc.last_updated_iso) or site_last_date
        status_html = render_status_badge(n.status)
        # warning: `outline_summary` はエスケープ無しで埋め込まれる
        item_html = f"""<article class="novel-item">
    <h3 class="novel-title"><a href="{html_escape(n_pub_dir_name)}/index.html">{title_html}</a></h3>
    <div class="novel-details">
        <p class="abstract">{outline_summary}</p>
        <p class="status">{status_html}</p>
        <p class="tags">{html_escape(tags_str)}</p>
        <p class="metadata">{last_date} 更新 | 全{n.num_stories}話 | 合計{n.total_length}文字</p>
    </div>
</article>"""
        novel_items.append(item_html)

    novel_list_html = ""
    if novel_items:
        sep = '\n<hr class="separator">\n'
        novel_list_html = f"""
<section class="novel-list">
    <h2 class="section-title">小説一覧</h2>
    {sep.join(novel_items)}
</section>
"""

    index_html = f"""<!DOCTYPE html>
<html lang="ja">
{head_html}
<body>
{header_html}
<main class="content-wrapper">
    <section class="self-introduction">
        <h2 class="section-title">自己紹介</h2>
        <div class="intro-body">
            {self_intro_html}
        </div>
    </section>
    {novel_list_html}
</main>
</body>
</html>
"""
    return index_html, novel_contexts, site_last_date


def build_novel_top_page(site_last_date: str, nc: NovelContext) -> str:
    n = nc.novel
    header_html = render_site_header("../", site_last_date)

    title_html = md.to_html_ruby(n.title)
    tags_str = parse_tags(n.tags)
    last_date = parse_date_from_iso(nc.last_updated_iso) or site_last_date
    outline_html = apply_ruby_and_markdown(n.outline)

    # 他公開サイト
    if n.has_external_links and n.external_links:
        ext_html = md_to_html(n.external_links)
        external_html = f"""
<section class="external-sites-section">
    <h2 class="section-title">他公開サイト</h2>
    {ext_html}
</section>
"""
    else:
        external_html = """
<section class="external-sites-section">
    <h2 class="section-title">他公開サイト</h2>
    <p>もぐらノベル限定公開作品です。</p>
</section>
"""

    # 目次
    toc_body = []
    ordered = n.get_stories_ordered()
    if n.has_chapters and isinstance(ordered, dict):
        rev_index = {v: k for k, v in nc.index_to_story.items()}
        for idx_ch, (chap_title, stories) in enumerate(ordered.items(), start=1):
            chap_title_html = md.to_html_ruby(chap_title)
            toc_body.append(f'<h3 class="chapter-title">{idx_ch}章: {chap_title_html}</h3>')
            toc_body.append("<ul>")
            for s in stories:
                disp_index = rev_index[s]
                file_name = f"{disp_index}.html"
                s_title_html = md.to_html_ruby(s.title)
                s_ts_iso = nc.story_updated_iso.get(s.number, nc.last_updated_iso)
                s_date = parse_date_from_iso(s_ts_iso) or last_date
                toc_body.append(
                    f'<li><a href="{file_name}" class="chapter-link">{disp_index}話 {s_title_html}</a>'
                    f'<span class="metadata">{s_date} 更新 | {s.length}文字</span></li>'
                )
            toc_body.append("</ul>")
    else:
        toc_body.append("<ul>")
        for idx, s in nc.index_to_story.items():
            file_name = f"{idx}.html"
            s_title_html = md.to_html_ruby(s.title)
            s_ts_iso = nc.story_updated_iso.get(s.number, nc.last_updated_iso)
            s_date = parse_date_from_iso(s_ts_iso) or last_date
            toc_body.append(
                f'<li><a href="{file_name}" class="chapter-link">{idx}話 {s_title_html}</a>'
                f'<span class="metadata">{s_date} 更新 | {s.length}文字</span></li>'
            )
        toc_body.append("</ul>")

    toc_html = "\n".join(toc_body)

    # ---- head（favicon / OGP / X）----
    og_desc = truncate_outline(n.outline, 120)
    og_img = choose_og_image(nc.public_dir.name)
    head_html = build_head(
        title_text=f"{n.title} - もぐらノベル",
        root_prefix="../",
        og_title=n.title,
        og_desc=og_desc,
        og_type="article",
        og_image_path_from_root=og_img,
        og_url_path_from_root=f"/{nc.public_dir.name}/",
    )

    novel_top_html = f"""<!DOCTYPE html>
<html lang="ja">
{head_html}
<body>
{header_html}
<main class="content-wrapper">
    <section class="novel-info-header">
        <div class="novel-info-content">
            <h2 class="novel-title-main">{title_html}</h2>
            <p class="status">{render_status_badge(n.status)}</p>
            <p class="tags">{html_escape(tags_str)}</p>
            <p class="metadata">{last_date} 更新 | 全{n.num_stories}話 | 合計{n.total_length}文字</p>
        </div>
    </section>

    <section class="abstract-section">
        <h2 class="section-title">あらすじ</h2>
        <div class="abstract-body">
            {outline_html}
        </div>
    </section>

    {external_html}

    <section class="table-of-contents">
        <h2 class="section-title">目次</h2>
        <div class="toc-body">
            {toc_html}
        </div>
    </section>
</main>
</body>
</html>
"""
    return novel_top_html


def build_story_page(site_last_date: str, nc: NovelContext, story_index: int) -> str:
    n = nc.novel
    s = nc.index_to_story[story_index]
    header_html = render_site_header("../", site_last_date)

    title_text = f"{story_index}話 {s.title}"
    title_html = md.to_html_ruby(title_text)

    s_ts_iso = nc.story_updated_iso.get(s.number, nc.last_updated_iso)
    s_date = parse_date_from_iso(s_ts_iso) or site_last_date
    # 本文に全角スペースを表示する
    body_html = apply_ruby_and_markdown(s.content.replace("　", "&#x3000;"))

    prev_html = ""
    next_html = ""
    if story_index > 1:
        prev_html = f'<a href="{story_index - 1}.html">前の話</a>'
    if story_index < len(nc.index_to_story):
        next_html = f'<a href="{story_index + 1}.html">次の話</a>'

    nav_html = f"""<nav class="chapter-navigation">
    <ul class="nav-list">
        <li class="prev-chapter">{prev_html}</li>
        <li class="novel-top-link"><a href="index.html">作品トップへ</a></li>
        <li class="next-chapter">{next_html}</li>
    </ul>
</nav>"""

    # ---- head（favicon / OGP / X）----
    og_title = f"{title_text} - {n.title}"
    og_desc = truncate_outline(s.content, 110)
    og_img = choose_og_image(nc.public_dir.name)
    head_html = build_head(
        title_text=f"{title_text} - {n.title}",
        root_prefix="../",
        og_title=og_title,
        og_desc=og_desc,
        og_type="article",
        og_image_path_from_root=og_img,
        og_url_path_from_root=f"/{nc.public_dir.name}/{story_index}.html",
    )

    page_html = f"""<!DOCTYPE html>
<html lang="ja">
{head_html}
<body>
{header_html}
<main class="content-wrapper chapter-page">
    <section class="chapter-info-header">
        <div class="chapter-info-content">
            <h3 class="chapter-title-main">{title_html}</h3>
            <p class="chapter-metadata-chapter">{s_date} 更新 | {s.length}文字</p>
            {nav_html}
        </div>
    </section>
    <article class="novel-body">
        {body_html}
    </article>
</main>
</body>
</html>
"""
    return page_html


def copy_style(root: Path):
    src = root / "private" / "css"/ "style.css"
    if not src.is_file():
        raise FileNotFoundError(f"Style file not found: {src}")
    dst_dir = root / "public" / "css"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "style.css"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def main():
    root = Path(__file__).resolve().parents[1]  # tools/ の一つ上=プロジェクトルート
    private_dir = root / "private"
    self_intro = private_dir / "self_intro.md"
    public_dir = root / "public"
    history_path = root / "data" / "update_history.csv"

    # TopPage 検証
    tp_result = TopPage.load_if_valid(self_intro.relative_to(root))
    if isinstance(tp_result, list):
        for m in tp_result:
            print(m, file=sys.stderr)
        sys.exit(1)
    tp: TopPage = tp_result

    # 履歴
    history = load_history(history_path)
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # トップページ
    index_html, novel_contexts, site_last_date = build_top_page(root, tp, history, now_iso)
    public_dir.mkdir(parents=True, exist_ok=True)
    (public_dir / "index.html").write_text(index_html, encoding="utf-8")

    # CSS
    copy_style(root)

    # 各小説トップ & 各話
    for nc in novel_contexts:
        nc.public_dir.mkdir(parents=True, exist_ok=True)
        novel_top_html = build_novel_top_page(site_last_date, nc)
        (nc.public_dir / "index.html").write_text(novel_top_html, encoding="utf-8")

        total = len(nc.index_to_story)
        for idx in range(1, total + 1):
            story_html = build_story_page(site_last_date, nc, idx)
            out = nc.public_dir / f"{idx}.html"
            out.write_text(story_html, encoding="utf-8")

    # Favicon コピー
    fnames = [
        "favicon.ico",
        "favicon-16x16.png",
        "favicon-32x32.png",
        "apple-touch-icon.png",
    ]
    for fname in fnames:
        src = root / "private" / fname
        if src.is_file():
            dst = public_dir / fname
            dst.write_bytes(src.read_bytes())

    # 履歴保存
    save_history(history_path, history)


if __name__ == "__main__":
    main()
