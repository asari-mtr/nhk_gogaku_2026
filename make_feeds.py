#!/usr/bin/env python3
"""state/downloaded.json を読んで、番組ごとに RSS (Podcast) を生成。

各番組につき feeds/<safe-name>.xml を出力。iTunes 拡張対応。
依存: 標準ライブラリのみ。
"""
from __future__ import annotations

import json
import logging
import re
import socket
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
SERIES_FILE = ROOT / "series.json"
STATE_FILE = ROOT / "state" / "downloaded.json"
DOWNLOADS_DIR = ROOT / "downloads"
FEEDS_DIR = ROOT / "feeds"
SERIES_META_FILE = ROOT / "state" / "series_meta.json"

DEFAULT_PORT = 8123
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 非公式・私的利用を明示するマーカー
UNOFFICIAL_PREFIX = "[非公式] "
PERSONAL_AUTHOR = "Personal Archive"
UNOFFICIAL_NOTICE = (
    "※これはNHK公式のPodcast配信ではありません。"
    "NHKラジオの聴き逃し配信を個人が私的利用の範囲でローカルに保存したものです。"
    "公式チャンネルとは無関係です。\n\n"
)

_FNAME_SAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_filename(name: str) -> str:
    cleaned = _FNAME_SAFE.sub("_", name).strip()
    return cleaned[:120] if len(cleaned) > 120 else cleaned


def detect_host() -> str:
    """mDNSの .local 名 (例: MacBook-Pro.local)。失敗時はFQDN/IP。"""
    try:
        import subprocess

        r = subprocess.run(
            ["scutil", "--get", "LocalHostName"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            return f"{r.stdout.strip()}.local"
    except Exception:
        pass
    try:
        return socket.gethostname()
    except Exception:
        return "localhost"


def fetch_series_metadata(series_id: str) -> dict:
    """番組のロゴ・説明をAPIから取得 (キャッシュは呼び出し側で)。"""
    url = f"https://api.nhk.jp/r8/l/radioepisode/pl/series-rep-{series_id}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
    except Exception:
        return {}
    items = data.get("result") or []
    if not items:
        return {}
    pos = (items[0].get("partOfSeries") or {})
    logo = ((pos.get("logo") or {}).get("main") or {}).get("url")
    return {
        "name": pos.get("name"),
        "description": pos.get("description") or pos.get("detailedCatch"),
        "catch": pos.get("detailedCatch"),
        "logo": logo,
        "canonical": pos.get("canonical"),
    }


def load_series_meta_cache() -> dict:
    if SERIES_META_FILE.exists():
        return json.loads(SERIES_META_FILE.read_text("utf-8"))
    return {}


def save_series_meta_cache(cache: dict) -> None:
    SERIES_META_FILE.parent.mkdir(parents=True, exist_ok=True)
    SERIES_META_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def url_for_file(host: str, port: int, rel_path: str) -> str:
    """ローカルファイルパス (downloads/foo/bar.m4a) を HTTP URL に。"""
    parts = [urllib.parse.quote(p, safe="") for p in rel_path.split("/")]
    return f"http://{host}:{port}/" + "/".join(parts)


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def build_feed_xml(
    series: dict,
    episodes: list[dict],
    series_meta: dict,
    host: str,
    port: int,
) -> str:
    """1番組分のRSS XMLを組み立てる (非公式マーカー込み)。"""
    raw_sname = series["name"]
    sname = UNOFFICIAL_PREFIX + raw_sname
    sid = series["id"]
    feed_self_url = url_for_file(host, port, f"feeds/{sid}.xml")
    site_url = series_meta.get("canonical") or series.get("page_url") or "https://www.nhk.jp/p/rs/"
    raw_description = series_meta.get("description") or series_meta.get("catch") or raw_sname
    description = UNOFFICIAL_NOTICE + raw_description
    logo = series_meta.get("logo") or ""

    now_rfc2822 = format_datetime(datetime.now(timezone.utc))

    head = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{escape(sname)}</title>
    <link>{escape(site_url)}</link>
    <language>ja</language>
    <description>{escape(description)}</description>
    <itunes:author>{escape(PERSONAL_AUTHOR)}</itunes:author>
    <itunes:owner><itunes:name>{escape(PERSONAL_AUTHOR)}</itunes:name></itunes:owner>
    <itunes:summary>{escape(description)}</itunes:summary>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="Education"/>
    <itunes:type>episodic</itunes:type>
    <copyright>Personal Archive (Unofficial). Source content owned by NHK.</copyright>
    <atom:link href="{escape(feed_self_url)}" rel="self" type="application/rss+xml"/>
    <lastBuildDate>{now_rfc2822}</lastBuildDate>
"""
    if logo:
        head += f'    <itunes:image href="{escape(logo)}"/>\n'
        head += (
            f"    <image><url>{escape(logo)}</url>"
            f"<title>{escape(sname)}</title>"
            f"<link>{escape(site_url)}</link></image>\n"
        )

    items_xml = []
    # 新しい順
    for ep in sorted(episodes, key=lambda e: e.get("broadcast_date") or "", reverse=True):
        rel_path = ep.get("path")
        if not rel_path:
            continue
        abs_path = ROOT / rel_path
        if not abs_path.exists():
            continue
        size = file_size(abs_path)
        enc_url = url_for_file(host, port, rel_path)
        try:
            bd = datetime.fromisoformat(ep["broadcast_date"])
            pub = format_datetime(bd.astimezone(timezone.utc))
        except Exception:
            pub = now_rfc2822
        title = ep.get("title") or abs_path.stem
        guid = ep.get("episode_id") or rel_path
        ep_desc = ep.get("description") or ""
        full_desc = (ep_desc + "\n\n" if ep_desc else "") + UNOFFICIAL_NOTICE.rstrip()
        items_xml.append(
            f"""    <item>
      <title>{escape(title)}</title>
      <description>{escape(full_desc)}</description>
      <pubDate>{pub}</pubDate>
      <enclosure url="{escape(enc_url)}" length="{size}" type="audio/mp4"/>
      <guid isPermaLink="false">{escape(guid)}</guid>
      <itunes:author>{escape(PERSONAL_AUTHOR)}</itunes:author>
      <itunes:explicit>false</itunes:explicit>
    </item>"""
        )

    tail = "\n  </channel>\n</rss>\n"
    return head + "\n".join(items_xml) + tail


def build_all_feeds(
    host: str | None = None,
    port: int = DEFAULT_PORT,
    logger: logging.Logger | None = None,
) -> list[Path]:
    """全番組分のRSSを生成して feeds/ に書き出す。生成したパスを返す。"""
    if logger is None:
        logger = logging.getLogger("make_feeds")
    if host is None:
        host = detect_host()

    if not SERIES_FILE.exists():
        logger.error("series.json が見つかりません")
        return []
    series_conf = json.loads(SERIES_FILE.read_text("utf-8"))

    state = {"downloaded": {}}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text("utf-8"))

    meta_cache = load_series_meta_cache()
    FEEDS_DIR.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for series in series_conf.get("series", []):
        sid = series["id"]
        if not series.get("enabled", True):
            continue

        downloaded = state["downloaded"].get(sid, {})
        # 再放送スキップ分は除外
        episodes = []
        for ep_id, meta in downloaded.items():
            if meta.get("skipped_as_rerun"):
                continue
            if not meta.get("path"):
                continue
            episodes.append({"episode_id": ep_id, **meta})

        # series メタを取得 (キャッシュ優先、なければAPI)
        if sid not in meta_cache:
            logger.info("series メタを取得: %s", series["name"])
            meta_cache[sid] = fetch_series_metadata(sid)
            save_series_meta_cache(meta_cache)

        xml = build_feed_xml(series, episodes, meta_cache.get(sid, {}), host, port)
        out = FEEDS_DIR / f"{sid}.xml"
        out.write_text(xml, encoding="utf-8")
        logger.info("RSS 生成: %s [%s] (%d エピソード)", series["name"], out.name, len(episodes))
        written.append(out)
    return written


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="RSS (Podcast) フィード生成")
    p.add_argument("--host", help="フィードURLに使うホスト名 (デフォルト: <Mac>.local)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    paths = build_all_feeds(args.host, args.port)
    host = args.host or detect_host()
    print()
    print(f"フィードURL (Apple Podcasts に「URLから追加」で登録):")
    for p in paths:
        feed_url = url_for_file(host, args.port, f"feeds/{p.name}")
        print(f"  {feed_url}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
