# tools/publish.py
from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
import html
from pathlib import Path
from typing import Dict, Iterable, Tuple, Optional, List

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
    *,
    legacy_hashes: Iterable[str] = (),
) -> str:
    key_str = str(key).replace("\\", "/")
    old = history.get(key_str)
    if old is not None and old[0] == new_hash:
        return old[1]
    if old is not None and old[0] in legacy_hashes:
        # The former hashes for an index and self_intro included downstream
        # content. Replace only the hash representation; the input file itself
        # did not change, so retain its historical timestamp.
        history[key_str] = (new_hash, old[1])
        return old[1]
    history[key_str] = (new_hash, now_iso)
    return now_iso


def parse_date_from_iso(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
    except Exception:
        return ""
    return dt.date().isoformat()


def _timestamp_value(ts: str) -> datetime:
    """Parse an ISO timestamp into a comparable UTC datetime."""
    try:
        value = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _latest_timestamp(timestamps: Iterable[str]) -> str:
    values = list(timestamps)
    return max(values, key=_timestamp_value) if values else ""


# ====== HTML 共通 ======
def html_escape(s: str) -> str:
    return html.escape(s, quote=True)


def render_site_header(root_prefix: str) -> str:
    return f"""<header class="site-header">
    <div class="site-header-content">
        <h1 class="site-name"><a href="{root_prefix}index.html">もぐらノベル</a></h1>
        <p class="last-update" data-site-last-updated>更新日を読み込み中</p>
    </div>
</header>"""


def truncate_outline(outline: str, limit: int = 150) -> str:
    s = outline.replace("\n", " ").strip()
    if len(s) <= limit:
        # ルビも含むと厳密には文字数が変わるが、概ね問題ない想定
        return md.to_html(s)
    else:
        # warning: ルビタグを途中で切る可能性あり
        truncated = s[:limit] + "..."
        return md.to_html(truncated)

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


def choose_og_image(static_source: Path, novel_dirname: Optional[str]) -> str:
    """
    /docs をサイトルートとみなし、/ogp/<novel>.png → /ogp/default.png
    → /apple-touch-icon.png → /favicon-32x32.png の順で存在するものを返す。
    返り値は「/」から始まるサイトルート相対パス。
    """
    candidates = []
    if novel_dirname:
        candidates.append(static_source / "ogp" / f"{novel_dirname}.png")
    candidates.extend([
        static_source / "ogp" / "default.png",
        static_source / "apple-touch-icon.png",
        static_source / "favicon-32x32.png",
    ])
    for c in candidates:
        if c.is_file():
            return "/" + c.relative_to(static_source).as_posix()
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
    <script src="{root_prefix}js/apply-update-metadata.js" defer></script>
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


_STATUS_ORDER = {
    "連載中": 0,
    "完結済": 1,
    "更新停止": 2,
}


def _novel_context_sort_key(nc: NovelContext):
    # datetime has no reverse-key helper. A timedelta also works for dates that
    # Windows' platform timestamp conversion cannot represent.
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    updated = (_timestamp_value(nc.last_updated_iso) - epoch).total_seconds()
    return (
        -updated,
        _STATUS_ORDER.get(nc.novel.status, 999),
        nc.novel.title,
        nc.public_dir.name,
    )


def _novel_context_stable_key(nc: NovelContext):
    """Return a date-independent order for the HTML source fallback."""
    return (
        _STATUS_ORDER.get(nc.novel.status, 999),
        nc.novel.title,
        nc.public_dir.name,
    )


def build_update_metadata(
    novel_contexts: List[NovelContext], site_last_date: str
) -> str:
    """Build the small JSON document consumed by every page."""
    works = {}
    for display_order, nc in enumerate(novel_contexts):
        works[nc.public_dir.name] = {
            "character_count": nc.novel.total_length,
            "display_order": display_order,
            "last_updated": parse_date_from_iso(nc.last_updated_iso),
            "story_count": nc.novel.num_stories,
        }
    payload = {
        "site_last_updated": site_last_date,
        "works": works,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _relative_history_key(path: Path, root: Path) -> Path:
    """Return the repository-relative key used by update_history.csv."""
    p = Path(path)
    if p.is_absolute():
        return p.resolve().relative_to(root.resolve())
    return p


def build_top_page(
    root: Path,
    public_dir: Path,
    tp: TopPage,
    history: History,
    now_iso: str,
) -> Tuple[str, List[NovelContext], str]:
    # TopPage（自己紹介）の更新履歴
    top_rel = _relative_history_key(tp.path, root)
    top_hash = tp.hash()
    top_ts_iso = update_history_entry(
        history,
        top_rel,
        top_hash,
        now_iso,
        legacy_hashes=tp.legacy_hash_candidates(),
    )

    novel_contexts: List[NovelContext] = []
    for novel, ndir in zip(tp.novels, tp.novel_directories):
        ndir = Path(ndir)
        n_hash = novel.hash()
        n_key = _relative_history_key(novel.path, root)
        n_ts_iso = update_history_entry(
            history,
            n_key,
            n_hash,
            now_iso,
            legacy_hashes=(novel.legacy_hash(),),
        )

        story_updated_iso: Dict[int, str] = {}
        index_to_story: Dict[int, Story] = {}
        for idx, s in enumerate(novel.stories, start=1):
            s_key = _relative_history_key(s.path, root)
            s_ts_iso = update_history_entry(history, s_key, s.hash(), now_iso)
            story_updated_iso[s.number] = s_ts_iso
            index_to_story[idx] = s

        all_ts = [n_ts_iso] + list(story_updated_iso.values())
        n_last_iso = _latest_timestamp(all_ts) or n_ts_iso

        nc = NovelContext(
            novel=novel,
            private_dir=ndir,
            public_dir=public_dir / ndir.name,
            last_updated_iso=n_last_iso,
            story_updated_iso=story_updated_iso,
            index_to_story=index_to_story,
        )
        novel_contexts.append(nc)

    novel_contexts.sort(key=_novel_context_sort_key)
    site_last_iso = _latest_timestamp(
        [top_ts_iso, *(nc.last_updated_iso for nc in novel_contexts)]
    )
    site_last_date = parse_date_from_iso(site_last_iso) or parse_date_from_iso(now_iso)

    header_html = render_site_header("")

    # ---- head（favicon / OGP / X）----
    og_desc = "『もぐらノベル』は吾輩はもぐらであるが趣味で書いた小説を公開する個人サイトです。"
    og_img = choose_og_image(root / "private", None)
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
    self_intro_html = md.to_html(tp.self_intro)

    # 小説一覧
    novel_items: List[str] = []
    # The HTML itself uses a date-independent order.  JavaScript applies the
    # update-time order from update-metadata.json after the page has loaded.
    for nc in sorted(novel_contexts, key=_novel_context_stable_key):
        n = nc.novel
        n_pub_dir_name = nc.public_dir.name
        title_html = md.to_html_ruby(n.title)
        tags_str = parse_tags(n.tags)
        outline_summary = truncate_outline(n.outline)
        status_html = render_status_badge(n.status)
        # warning: `outline_summary` はエスケープ無しで埋め込まれる
        item_html = f"""<article class="novel-item" data-work-slug="{html_escape(n_pub_dir_name)}">
    <h3 class="novel-title"><a href="{html_escape(n_pub_dir_name)}/index.html">{title_html}</a></h3>
    <div class="novel-details">
        <p class="abstract">{outline_summary}</p>
        <p class="status">{status_html}</p>
        <p class="tags">{html_escape(tags_str)}</p>
        <p class="metadata" data-work-metadata>更新情報を読み込み中</p>
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


def build_novel_top_page(nc: NovelContext) -> str:
    n = nc.novel

    title_html = md.to_html_ruby(n.title)
    tags_str = parse_tags(n.tags)
    last_date = parse_date_from_iso(nc.last_updated_iso)
    header_html = render_site_header("../")
    outline_html = md.to_html(n.outline)

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
    og_img = choose_og_image(nc.private_dir.parent, nc.public_dir.name)
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


def build_story_page(
    nc: NovelContext,
    story_index: int,
) -> str:
    n = nc.novel
    s = nc.index_to_story[story_index]

    title_text = f"{story_index}話 {s.title}"
    title_html = md.to_html_ruby(title_text)

    s_ts_iso = nc.story_updated_iso.get(s.number, nc.last_updated_iso)
    s_date = parse_date_from_iso(s_ts_iso)
    header_html = render_site_header("../")
    body_html = md.to_html(s.content)

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
    og_img = choose_og_image(nc.private_dir.parent, nc.public_dir.name)
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


def copy_static_files(
    root: Path,
    public_dir: Path,
    *,
    newline_reference_dir: Optional[Path],
) -> None:
    """Copy static assets whose canonical source lives under private/."""
    src = root / "private" / "css"/ "style.css"
    if not src.is_file():
        raise FileNotFoundError(f"Style file not found: {src}")
    dst_dir = public_dir / "css"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "style.css"
    _write_generated_html(
        dst,
        src.read_text(encoding="utf-8"),
        public_dir=public_dir,
        newline_reference_dir=newline_reference_dir,
    )

    script_src = root / "private" / "js" / "apply-update-metadata.js"
    if not script_src.is_file():
        raise FileNotFoundError(f"Update metadata script not found: {script_src}")
    script_dst_dir = public_dir / "js"
    script_dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(script_src, script_dst_dir / script_src.name)

    fnames = [
        "CNAME",
        "favicon.ico",
        "favicon-16x16.png",
        "favicon-32x32.png",
        "apple-touch-icon.png",
    ]
    for fname in fnames:
        asset = root / "private" / fname
        if asset.is_file():
            if fname == "CNAME":
                # GitHub Pages accepts a single domain without a terminator;
                # keep the historical tracked bytes stable on regeneration.
                data = asset.read_text(encoding="utf-8").strip().encode("utf-8")
            else:
                data = asset.read_bytes()
            (public_dir / fname).write_bytes(data)

    ogp_source = root / "private" / "ogp"
    if ogp_source.is_dir():
        shutil.copytree(ogp_source, public_dir / "ogp", dirs_exist_ok=True)


def _write_generated_html(
    path: Path,
    content: str,
    *,
    public_dir: Path,
    newline_reference_dir: Optional[Path],
) -> None:
    """Write deterministic HTML while retaining a tracked file's line style."""
    newline = "\n"
    if newline_reference_dir is not None:
        reference = Path(newline_reference_dir) / path.relative_to(public_dir)
        if reference.is_file():
            data = reference.read_bytes()
            crlf = data.count(b"\r\n")
            bare_lf = data.count(b"\n") - crlf
            if crlf > bare_lf:
                newline = "\r\n"
    path.write_text(content, encoding="utf-8", newline=newline)


def generate_site(
    root: Path,
    public_dir: Path,
    history_path: Path,
    *,
    history_seed_path: Optional[Path] = None,
    newline_reference_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> None:
    """Generate the complete site into explicit destinations.

    The caller chooses whether the destinations are the tracked publication
    files or an ignored preview build.  No path is hard-coded to docs/ here.
    """
    root = Path(root).resolve()
    public_dir = Path(public_dir).resolve()
    history_path = Path(history_path).resolve()
    if newline_reference_dir is None:
        candidate_reference = root / "docs"
        newline_reference_dir = candidate_reference if candidate_reference.is_dir() else None
    private_dir = root / "private"
    self_intro = private_dir / "self_intro.md"

    # TopPage 検証
    tp_result = TopPage.load_if_valid(self_intro)
    if isinstance(tp_result, list):
        raise ValueError("\n".join(tp_result))
    tp: TopPage = tp_result

    # 履歴
    seed = Path(history_seed_path) if history_seed_path else history_path
    history = load_history(seed)
    generation_time = now or datetime.now(timezone.utc)
    if generation_time.tzinfo is None:
        raise ValueError("now must include timezone information")
    now_iso = generation_time.astimezone(timezone.utc).isoformat(timespec="seconds")

    # トップページ
    index_html, novel_contexts, site_last_date = build_top_page(
        root, public_dir, tp, history, now_iso
    )
    public_dir.mkdir(parents=True, exist_ok=True)
    _write_generated_html(
        public_dir / "index.html",
        index_html,
        public_dir=public_dir,
        newline_reference_dir=newline_reference_dir,
    )
    (public_dir / "update-metadata.json").write_text(
        build_update_metadata(novel_contexts, site_last_date),
        encoding="utf-8",
        newline="\n",
    )

    # CSS / JavaScript / CNAME / icons / optional OGP assets
    copy_static_files(
        root, public_dir, newline_reference_dir=newline_reference_dir
    )

    # 各小説トップ & 各話
    for nc in novel_contexts:
        nc.public_dir.mkdir(parents=True, exist_ok=True)
        novel_top_html = build_novel_top_page(nc)
        _write_generated_html(
            nc.public_dir / "index.html",
            novel_top_html,
            public_dir=public_dir,
            newline_reference_dir=newline_reference_dir,
        )

        total = len(nc.index_to_story)
        for idx in range(1, total + 1):
            story_html = build_story_page(nc, idx)
            out = nc.public_dir / f"{idx}.html"
            _write_generated_html(
                out,
                story_html,
                public_dir=public_dir,
                newline_reference_dir=newline_reference_dir,
            )

    # 履歴保存
    save_history(history_path, history)


def _replace_publication(root: Path, staged_docs: Path, staged_history: Path) -> None:
    """Replace tracked publication outputs, rolling back on any failure."""
    state_dir = root / ".novel-editor"
    backup_dir = state_dir / f"publish-backup-{uuid.uuid4().hex}"
    backup_docs = backup_dir / "docs"
    backup_history = backup_dir / "update_history.csv"
    docs = root / "docs"
    history = root / "data" / "update_history.csv"
    backup_dir.mkdir(parents=True, exist_ok=False)
    moved_docs = False
    moved_history = False
    installed_docs = False
    installed_history = False
    try:
        if docs.exists():
            os.replace(docs, backup_docs)
            moved_docs = True
        if history.exists():
            os.replace(history, backup_history)
            moved_history = True
        os.replace(staged_docs, docs)
        installed_docs = True
        history.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged_history, history)
        installed_history = True
    except Exception as original_error:
        rollback_errors: List[str] = []
        try:
            if installed_history and history.exists():
                history.unlink()
        except Exception as exc:
            rollback_errors.append(f"新しい更新履歴の除去失敗: {exc}")
        try:
            if installed_docs and docs.exists():
                shutil.rmtree(docs)
        except Exception as exc:
            rollback_errors.append(f"新しいdocsの除去失敗: {exc}")
        try:
            if moved_history and backup_history.exists():
                os.replace(backup_history, history)
        except Exception as exc:
            rollback_errors.append(f"更新履歴の復元失敗: {exc}")
        try:
            if moved_docs and backup_docs.exists():
                os.replace(backup_docs, docs)
        except Exception as exc:
            rollback_errors.append(f"docsの復元失敗: {exc}")
        if rollback_errors:
            detail = " / ".join(rollback_errors)
            raise RuntimeError(f"公開物の置換と復元に失敗しました: {detail}") from original_error
        raise
    finally:
        if installed_docs and installed_history:
            shutil.rmtree(backup_dir, ignore_errors=True)


def main():
    root = Path(__file__).resolve().parents[1]
    state_dir = root / ".novel-editor"
    build_dir = state_dir / f"publish-build-{uuid.uuid4().hex}"
    staged_docs = build_dir / "docs"
    staged_history = build_dir / "update_history.csv"
    try:
        generate_site(
            root,
            staged_docs,
            staged_history,
            history_seed_path=root / "data" / "update_history.csv",
        )
        _replace_publication(root, staged_docs, staged_history)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
