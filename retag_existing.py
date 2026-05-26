#!/usr/bin/env python3
"""既存DL済 m4a に メタデータ + アートワーク を後付けする (ワンショット)。

state/downloaded.json をもとに、各エピソードに対して:
  - title / album / artist / date / genre / description / show
  - 番組ロゴをカバーとして埋め込み
を ffmpeg で再パッケージ (再エンコードなし、-c copy)。
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "state" / "downloaded.json"
SERIES_FILE = ROOT / "series.json"
SERIES_META_FILE = ROOT / "state" / "series_meta.json"
ARTWORK_DIR = ROOT / "state" / "artwork"

USER_AGENT = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36"


def load_json(p: Path, default):
    if p.exists():
        return json.loads(p.read_text("utf-8"))
    return default


def save_json(p: Path, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_artwork(sid: str, logo_url: str | None, log: logging.Logger) -> Path | None:
    if not logo_url:
        return None
    ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
    ext = ".jpg" if ".jpg" in logo_url.lower() else ".png"
    out = ARTWORK_DIR / f"{sid}{ext}"
    if out.exists() and out.stat().st_size > 0:
        return out
    try:
        req = urllib.request.Request(logo_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            out.write_bytes(r.read())
        log.info("artwork: %s", out.name)
        return out
    except Exception as e:
        log.warning("artwork取得失敗 %s: %s", sid, e)
        return None


def ensure_series_meta(sid: str, cache: dict, log: logging.Logger) -> dict:
    if cache.get(sid) and cache[sid].get("logo"):
        return cache[sid]
    url = f"https://api.nhk.jp/r8/l/radioepisode/pl/series-rep-{sid}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        items = d.get("result") or []
        if items:
            pos = items[0].get("partOfSeries") or {}
            cache[sid] = {
                "name": pos.get("name"),
                "description": pos.get("description") or pos.get("detailedCatch"),
                "logo": ((pos.get("logo") or {}).get("main") or {}).get("url"),
                "canonical": pos.get("canonical"),
            }
            save_json(SERIES_META_FILE, cache)
    except Exception as e:
        log.warning("series meta取得失敗 %s: %s", sid, e)
    return cache.get(sid, {})


def retag_file(
    src: Path,
    meta: dict,
    artwork: Path | None,
    log: logging.Logger,
) -> bool:
    """src に metadata と artwork を再パッケージで埋める (再エンコードなし)。"""
    tmp = src.with_suffix(src.suffix + ".retag")
    cmd = [
        "ffmpeg", "-y",
        "-loglevel", "warning",
        "-i", str(src),
    ]
    if artwork and artwork.exists():
        cmd += ["-i", str(artwork)]
        cmd += [
            "-map", "0:a",
            "-map", "1:v",
            "-c:v", "copy",
            "-disposition:v:0", "attached_pic",
        ]
    cmd += [
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-f", "ipod",
    ]
    for k, v in meta.items():
        if v:
            cmd += ["-metadata", f"{k}={v}"]
    cmd += [str(tmp)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        log.error("timeout: %s", src.name)
        tmp.unlink(missing_ok=True)
        return False
    if r.returncode != 0:
        log.error("ffmpeg failed: %s\n%s", src.name, r.stderr.strip()[-400:])
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(src)
    log.info("retagged: %s", src.name)
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    log = logging.getLogger("retag")

    state = load_json(STATE_FILE, {"downloaded": {}})
    series_conf = load_json(SERIES_FILE, {"series": []})
    name_by_id = {s["id"]: s["name"] for s in series_conf.get("series", [])}
    meta_cache = load_json(SERIES_META_FILE, {})

    total, ok_count, fail_count = 0, 0, 0
    for sid, eps in state["downloaded"].items():
        series_meta = ensure_series_meta(sid, meta_cache, log)
        artwork = fetch_artwork(sid, series_meta.get("logo"), log)
        sname = name_by_id.get(sid, series_meta.get("name") or sid)

        for ep_id, m in eps.items():
            if m.get("skipped_as_rerun"):
                continue
            rel = m.get("path")
            if not rel:
                continue
            src = ROOT / rel
            if not src.exists():
                log.warning("missing file: %s", src)
                continue
            total += 1
            bd = m.get("broadcast_date") or ""
            date_str = ""
            wd_label = ""
            try:
                _dt = datetime.fromisoformat(bd)
                date_str = _dt.strftime("%Y-%m-%d")
                wd_label = "月火水木金土日"[_dt.weekday()]
            except Exception:
                pass
            ep_desc = m.get("description") or ""
            unofficial_note = "※NHKの聴き逃し配信を私的利用の範囲でローカル保存したもの。公式配信ではありません。"
            title_prefix = f"{date_str}({wd_label}) " if date_str else ""
            base_title = m.get("title") or src.stem
            ep_meta = {
                "title": f"{title_prefix}{base_title}",
                "album": f"[非公式] {sname}",
                "artist": "Personal Archive",
                "album_artist": "Personal Archive",
                "date": date_str,
                "genre": "Education",
                "comment": (ep_desc + " / " if ep_desc else "") + unofficial_note,
                "description": (ep_desc + "\n\n" if ep_desc else "") + unofficial_note,
                "show": sname,
            }
            if retag_file(src, ep_meta, artwork, log):
                ok_count += 1
            else:
                fail_count += 1

    log.info("=== 完了: %d 件 (成功 %d / 失敗 %d) ===", total, ok_count, fail_count)
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
