#!/usr/bin/env python3
"""NHKラジオ語学番組の聴き逃し配信を m4a でダウンロード。

依存: Python 3.10+ (標準ライブラリのみ), ffmpeg
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERIES_FILE = ROOT / "series.json"
CONFIG_FILE = ROOT / "config.json"
STATE_FILE = ROOT / "state" / "downloaded.json"
SERIES_META_FILE = ROOT / "state" / "series_meta.json"
ARTWORK_DIR = ROOT / "state" / "artwork"
DOWNLOADS_DIR = ROOT / "downloads"
LOGS_DIR = ROOT / "logs"

API_BASE = "https://api.nhk.jp/r8/l/radioepisode/pl/series-rep-{sid}.json"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

DEFAULT_CONFIG = {
    "format": "m4a",         # "m4a" or "mp3"
    "mp3_bitrate": "128k",   # mp3時のみ使用
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            d = json.loads(CONFIG_FILE.read_text("utf-8"))
            return {**DEFAULT_CONFIG, **d}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def setup_logging() -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"run-{datetime.now():%Y-%m-%d}.log"
    logger = logging.getLogger("nhk_dl")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.handlers = [fh, sh]
    return logger


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text("utf-8"))
    return {"downloaded": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


_ISO_DUR_RE = re.compile(
    r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$"
)


def parse_iso_duration(s: str | None) -> float | None:
    """ISO 8601 duration (例: PT4M57S) を秒数で返す。失敗時 None。"""
    if not s:
        return None
    m = _ISO_DUR_RE.match(s)
    if not m:
        return None
    h, mn, sec = m.groups()
    return int(h or 0) * 3600 + int(mn or 0) * 60 + float(sec or 0)


def validate_duration(
    actual: float | None,
    expected: float | None,
    logger: logging.Logger,
    name: str,
) -> str:
    """DL結果の妥当性を判定。"ok"/"short"/"long"/"unknown" を返す。"""
    if actual is None:
        logger.warning("[VALIDATE] %s: 実duration不明", name)
        return "unknown"
    if expected is None or expected <= 0:
        logger.info("[VALIDATE] %s: 期待duration不明 (実 %.1fs)", name, actual)
        return "unknown"
    ratio = actual / expected
    if ratio < 0.5:
        logger.warning(
            "[VALIDATE] ⚠ %s: 実 %.1fs / 期待 %.1fs (%.0f%%) — DL不完全か元データ短縮の可能性",
            name, actual, expected, ratio * 100,
        )
        return "short"
    if ratio > 1.2:
        logger.info(
            "[VALIDATE] %s: 実 %.1fs > 期待 %.1fs", name, actual, expected,
        )
        return "long"
    logger.info(
        "[VALIDATE] ✓ %s: 実 %.1fs / 期待 %.1fs (%.0f%%)",
        name, actual, expected, ratio * 100,
    )
    return "ok"


def probe_duration(path: Path) -> float | None:
    """ffprobe でファイルの長さ(秒)を取得。"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet",
             "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception:
        pass
    return None


def fetch_episodes(series_id: str) -> list[dict]:
    """配信中のエピソードのみ返す (m3u8 URLが取れるもの)"""
    data = fetch_json(API_BASE.format(sid=series_id))
    episodes = []
    for it in data.get("result", []):
        audio_list = it.get("audio") or []
        if not audio_list:
            continue
        audio = audio_list[0]
        m3u8_url = None
        for c in audio.get("detailedContent") or []:
            url = c.get("contentUrl")
            if url and url.endswith(".m3u8"):
                m3u8_url = url
                break
        if not m3u8_url:
            continue
        episodes.append(
            {
                "episode_id": it["id"],
                "title": it["name"],
                "description": (it.get("description") or "").strip(),
                "broadcast_date": (it.get("detailedRecentEvent") or {}).get("startDate"),
                "expires": audio.get("expires"),
                "m3u8_url": m3u8_url,
                "expected_duration": parse_iso_duration(audio.get("duration")),
            }
        )
    return episodes


_FNAME_SAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def safe_filename(name: str) -> str:
    """macOS/一般FSで安全な名前にする。"""
    cleaned = _FNAME_SAFE.sub("_", name).strip()
    return cleaned[:120] if len(cleaned) > 120 else cleaned


WEEKDAY_JA = ["月曜", "火曜", "水曜", "木曜", "金曜", "土曜", "日曜"]


def build_output_path(
    series_name: str,
    broadcast_date: str | None,
    title: str,
    group_by_weekday: bool = False,
    fmt: str = "m4a",
) -> Path:
    date_part = "0000-00-00"
    weekday_dir: str | None = None
    if broadcast_date:
        try:
            dt = datetime.fromisoformat(broadcast_date)
            date_part = dt.strftime("%Y-%m-%d")
            if group_by_weekday:
                weekday_dir = WEEKDAY_JA[dt.weekday()]
        except ValueError:
            pass
    dirpath = DOWNLOADS_DIR / safe_filename(series_name)
    if weekday_dir:
        dirpath = dirpath / weekday_dir
    ext = "mp3" if fmt == "mp3" else "m4a"
    return dirpath / f"{date_part}_{safe_filename(title)}.{ext}"


def fetch_artwork(series_id: str, logo_url: str | None, logger: logging.Logger) -> Path | None:
    """番組ロゴをローカルキャッシュ。返り値: ローカルパス or None。"""
    if not logo_url:
        return None
    ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
    # 拡張子推定 (NHK は jpg)
    ext = ".jpg" if ".jpg" in logo_url.lower() else ".png"
    out = ARTWORK_DIR / f"{series_id}{ext}"
    if out.exists() and out.stat().st_size > 0:
        return out
    try:
        req = urllib.request.Request(logo_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        out.write_bytes(data)
        logger.info("artwork cached: %s (%d KB)", out.name, len(data) // 1024)
        return out
    except Exception as e:
        logger.warning("artwork取得失敗 %s: %s", series_id, e)
        return None


def build_ffmpeg_metadata(meta: dict) -> list[str]:
    """ffmpeg の -metadata key=value 引数列を組み立てる。"""
    args: list[str] = []
    for k, v in meta.items():
        if v:
            args.extend(["-metadata", f"{k}={v}"])
    return args


def download_episode(
    m3u8_url: str,
    out_path: Path,
    metadata: dict,
    artwork_path: Path | None,
    logger: logging.Logger,
    fmt: str = "m4a",
    mp3_bitrate: str = "128k",
) -> bool:
    """ffmpegでHLSを取得して m4a (無変換) または mp3 (再エンコード) に保存。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")

    cmd: list[str] = [
        "ffmpeg", "-y",
        "-loglevel", "warning",
        "-user_agent", USER_AGENT,
        # NHK akamai CDN との相性問題回避: HTTP Range を使わず全体GETで取る
        # (これが無いと一部エピソードで途中で打ち切られる)
        "-http_seekable", "0",
        "-i", m3u8_url,
    ]
    has_artwork = artwork_path is not None and artwork_path.exists()
    if has_artwork:
        cmd += ["-i", str(artwork_path)]
        cmd += [
            "-map", "0:a",
            "-map", "1:v",
            "-c:v", "copy",
            "-disposition:v:0", "attached_pic",
        ]

    if fmt == "mp3":
        # mp3再エンコード
        cmd += [
            "-c:a", "libmp3lame",
            "-b:a", mp3_bitrate,
            "-id3v2_version", "3",
            "-f", "mp3",
        ]
    else:
        # m4a (AAC無変換コピー)
        cmd += [
            "-c:a", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-movflags", "+faststart",
            "-f", "ipod",
        ]
    cmd += build_ffmpeg_metadata(metadata)
    cmd += [str(tmp_path)]

    logger.info("ffmpeg start: %s", out_path.name)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg timeout")
        tmp_path.unlink(missing_ok=True)
        return False
    if result.returncode != 0:
        logger.error("ffmpeg failed (rc=%d): %s", result.returncode, result.stderr.strip()[-500:])
        tmp_path.unlink(missing_ok=True)
        return False
    tmp_path.rename(out_path)
    size_kb = out_path.stat().st_size / 1024
    logger.info("saved: %s (%.0f KB)", out_path.name, size_kb)
    return True


def load_series_meta_cache() -> dict:
    if SERIES_META_FILE.exists():
        return json.loads(SERIES_META_FILE.read_text("utf-8"))
    return {}


def save_series_meta_cache(cache: dict) -> None:
    SERIES_META_FILE.parent.mkdir(parents=True, exist_ok=True)
    SERIES_META_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def process_series(series: dict, state: dict, logger: logging.Logger, dry_run: bool, config: dict | None = None) -> int:
    if config is None:
        config = load_config()
    fmt = config.get("format", "m4a")
    mp3_bitrate = config.get("mp3_bitrate", "128k")
    sid = series["id"]
    sname = series["name"]
    group_by_weekday = bool(series.get("group_by_weekday", False))
    fmt_label = f"[{fmt}{(' ' + mp3_bitrate) if fmt == 'mp3' else ''}]"
    logger.info("series: %s (%s)%s %s", sname, sid, " [曜日別]" if group_by_weekday else "", fmt_label)

    # アートワークキャッシュ取得 (make_feeds の series_meta.json を再利用)
    meta_cache = load_series_meta_cache()
    series_meta = meta_cache.get(sid) or {}
    if not series_meta.get("logo"):
        # メタが未取得なら API から取って保存 (make_feeds も同じキャッシュを使う)
        try:
            url = API_BASE.format(sid=sid)
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read())
            items = d.get("result") or []
            if items:
                pos = items[0].get("partOfSeries") or {}
                series_meta = {
                    "name": pos.get("name"),
                    "description": pos.get("description") or pos.get("detailedCatch"),
                    "logo": ((pos.get("logo") or {}).get("main") or {}).get("url"),
                    "canonical": pos.get("canonical"),
                }
                meta_cache[sid] = series_meta
                save_series_meta_cache(meta_cache)
        except Exception as e:
            logger.warning("series meta取得失敗: %s", e)

    artwork = fetch_artwork(sid, series_meta.get("logo"), logger) if not dry_run else None

    try:
        episodes = fetch_episodes(sid)
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        logger.error("API取得失敗: %s", e)
        return 0

    logger.info("配信中エピソード: %d 件", len(episodes))

    done = state["downloaded"].setdefault(sid, {})
    # 過去にDL済み（再放送スキップは除く）のタイトル集合
    seen_titles = {
        m["title"]
        for m in done.values()
        if not m.get("skipped_as_rerun")
    }
    new_count = 0
    for ep in episodes:
        ep_id = ep["episode_id"]
        is_retry = False
        if ep_id in done:
            prev = done[ep_id]
            # 自動再DL: validation==short かつ まだconfirmedでない場合のみ1回再試行
            if (
                prev.get("validation") == "short"
                and not prev.get("short_confirmed")
            ):
                logger.info(
                    "retry (前回 short=%.0f%%): %s %s",
                    (prev.get("actual_duration_s") or 0)
                    / (prev.get("expected_duration_s") or 1) * 100,
                    ep_id, ep["title"],
                )
                # 既存ファイル削除して再DLフローへフォールスルー
                old_rel = prev.get("path")
                if old_rel:
                    old_abs = ROOT / old_rel
                    if old_abs.exists():
                        old_abs.unlink()
                is_retry = True
                # done から一旦削除しない (短い→確定フラグ判定のためprevを残す)
                # 下のDL処理で done[ep_id] が上書きされる
            else:
                logger.info("skip (取得済): %s %s", ep_id, ep["title"])
                continue
        # 再放送スキップ (※リトライ中の自身は除外)
        if not is_retry and ep["title"] in seen_titles:
            logger.info("skip (再放送 / タイトル一致): %s %s", ep_id, ep["title"])
            done[ep_id] = {
                "title": ep["title"],
                "broadcast_date": ep["broadcast_date"],
                "skipped_as_rerun": True,
                "logged_at": datetime.now().isoformat(timespec="seconds"),
            }
            save_state(state)
            continue
        out_path = build_output_path(sname, ep["broadcast_date"], ep["title"], group_by_weekday, fmt)
        if out_path.exists():
            logger.info("skip (ファイル既存): %s", out_path.name)
            done[ep_id] = {
                "title": ep["title"],
                "broadcast_date": ep["broadcast_date"],
                "path": str(out_path.relative_to(ROOT)),
                "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            }
            continue
        if dry_run:
            logger.info("[dry-run] would download: %s -> %s", ep_id, out_path)
            continue
        # メタデータを組み立て
        bd = ep.get("broadcast_date") or ""
        date_str = ""
        wd_label = ""
        try:
            _dt = datetime.fromisoformat(bd)
            date_str = _dt.strftime("%Y-%m-%d")
            wd_label = "月火水木金土日"[_dt.weekday()]
        except Exception:
            pass
        ep_desc = ep.get("description") or ""
        unofficial_note = "※NHKの聴き逃し配信を私的利用の範囲でローカル保存したもの。公式配信ではありません。"
        title_prefix = f"{date_str}({wd_label}) " if date_str else ""
        m4a_meta = {
            "title": f"{title_prefix}{ep['title']}",
            "album": f"[非公式] {sname}",
            "artist": "Personal Archive",
            "album_artist": "Personal Archive",
            "date": date_str,
            "genre": "Education",
            "comment": (ep_desc + " / " if ep_desc else "") + unofficial_note,
            "description": (ep_desc + "\n\n" if ep_desc else "") + unofficial_note,
            "show": sname,
        }
        ok = download_episode(ep["m3u8_url"], out_path, m4a_meta, artwork, logger, fmt, mp3_bitrate)
        if ok:
            actual = probe_duration(out_path)
            expected = ep.get("expected_duration")
            validation = validate_duration(actual, expected, logger, out_path.name)
            # 同じエピソードを連続でshortと判定したら「元データが本当に短い」と確定
            prev_meta = done.get(ep_id, {})
            short_confirmed = (
                validation == "short"
                and prev_meta.get("validation") == "short"
            )
            if short_confirmed:
                logger.info(
                    "[VALIDATE] %s: 再DLしても短い → short_confirmed (以後スキップ)",
                    out_path.name,
                )
            done[ep_id] = {
                "title": ep["title"],
                "description": ep.get("description", ""),
                "broadcast_date": ep["broadcast_date"],
                "path": str(out_path.relative_to(ROOT)),
                "downloaded_at": datetime.now().isoformat(timespec="seconds"),
                "expected_duration_s": expected,
                "actual_duration_s": actual,
                "validation": validation,
                "short_confirmed": short_confirmed,
            }
            new_count += 1
            save_state(state)
    return new_count


def main() -> int:
    parser = argparse.ArgumentParser(description="NHK語学番組ダウンローダ")
    parser.add_argument("--dry-run", action="store_true", help="DLせず予定のみ表示")
    parser.add_argument("--series-id", help="特定の series id だけ処理")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=== nhk_dl start ===")

    if not SERIES_FILE.exists():
        logger.error("series.json が見つかりません: %s", SERIES_FILE)
        return 1
    series_conf = json.loads(SERIES_FILE.read_text("utf-8"))

    state = load_state()
    config = load_config()
    logger.info("config: format=%s%s",
                config.get("format"),
                f", bitrate={config.get('mp3_bitrate')}" if config.get("format") == "mp3" else "")
    total_new = 0
    for s in series_conf.get("series", []):
        if not s.get("enabled", True):
            continue
        if args.series_id and s["id"] != args.series_id:
            continue
        total_new += process_series(s, state, logger, args.dry_run, config)

    save_state(state)
    # 新規DLの有無にかかわらず、毎回フィードを最新化する
    try:
        import make_feeds

        make_feeds.build_all_feeds(logger=logger)
    except Exception as e:
        logger.error("RSS生成失敗: %s", e)
    logger.info("=== done. 新規ダウンロード: %d 件 ===", total_new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
