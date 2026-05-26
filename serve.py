#!/usr/bin/env python3
"""nhk_gogaku_2026 をローカルWi-Fiに公開する小さなHTTPサーバ + 管理API。

エンドポイント:
  GET  /                    Web UI (index.html)
  GET  /webui/*             静的ファイル (css/js)
  GET  /feeds/*             RSS XML
  GET  /downloads/*         m4a 音声
  GET  /api/status          稼働状況
  GET  /api/series          現在のseries.json (DL数付き)
  POST /api/series          series.json を更新 {series:[...]}
  GET  /api/programs        NHK全番組リスト (10分キャッシュ)
  GET  /api/episodes        DL済みエピソード一覧
  GET  /api/feeds           フィードURL一覧
  POST /api/dl/run          DL実行 (バックグラウンド)
  GET  /api/dl/stream       Server-Sent Events で進捗
  GET  /api/logs/recent     今日の実行ログ末尾
"""
from __future__ import annotations

import http.server
import json
import logging
import os
import queue
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS_DIR = ROOT / "logs"
SERIES_FILE = ROOT / "series.json"
STATE_FILE = ROOT / "state" / "downloaded.json"
SERIES_META_FILE = ROOT / "state" / "series_meta.json"
DOWNLOADS_DIR = ROOT / "downloads"
FEEDS_DIR = ROOT / "feeds"
WEBUI_DIR = ROOT / "webui"

PORT = 8123
BIND = "0.0.0.0"

# 言語別プレイリストID (manage_series.py と同じ)
LANG_PLAYLISTS = {
    "english": ("英語", "gogakuEnglishRadio-CBJZTZ4ATE"),
    "chinese": ("中国語", "gogakuChineseRadio-PPZNQC8STT"),
    "hangeul": ("ハングル", "gogakuHangeulRadio-6R1DDSVHP7"),
    "french": ("フランス語", "gogakuFrenchRadio-FWTUVSSV6V"),
    "german": ("ドイツ語", "gogakuGermanRadio-P9V93PZKBD"),
    "italian": ("イタリア語", "gogakuItalianRadio-JEEVCV5T8J"),
    "spanish": ("スペイン語", "gogakuSpanishRadio-T2DDA9VIBV"),
    "portuguese": ("ポルトガル語", "gogakuPortugueseRadio-DLG5G7E8GT"),
    "russian": ("ロシア語", "gogakuRussianRadio-25N5GJGEYF"),
    "other": ("その他", "gogakuOtherRadio-GG73L1WTSD"),
}

USER_AGENT = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36"


# ─────────────────────────────────────────────────────
# DL ジョブ管理 (同時1本)
# ─────────────────────────────────────────────────────
class DLJob:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.subscribers: list[queue.Queue] = []
        self.last_lines: deque[str] = deque(maxlen=200)
        self.state: str = "idle"  # idle / running / done / failed
        self.started_at: str | None = None
        self.ended_at: str | None = None

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> bool:
        with self.lock:
            if self.is_running():
                return False
            self.last_lines.clear()
            self.state = "running"
            self.started_at = datetime.now().isoformat(timespec="seconds")
            self.ended_at = None
            self.proc = subprocess.Popen(
                [sys.executable, str(ROOT / "nhk_dl.py")],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            threading.Thread(target=self._pump, daemon=True).start()
            return True

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            self.last_lines.append(line)
            for q in list(self.subscribers):
                try:
                    q.put_nowait(line)
                except queue.Full:
                    pass
        rc = self.proc.wait()
        self.state = "done" if rc == 0 else "failed"
        self.ended_at = datetime.now().isoformat(timespec="seconds")
        for q in list(self.subscribers):
            try:
                q.put_nowait("__END__")
            except queue.Full:
                pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        # 既存のログを先に流す
        for ln in list(self.last_lines):
            q.put_nowait(ln)
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        if q in self.subscribers:
            self.subscribers.remove(q)


DL_JOB = DLJob()

# ─────────────────────────────────────────────────────
# 番組リストキャッシュ
# ─────────────────────────────────────────────────────
_programs_cache: dict | None = None
_programs_cached_at: float = 0


def fetch_all_programs(force: bool = False) -> dict:
    """全言語の番組リストを取得 (10分キャッシュ)"""
    global _programs_cache, _programs_cached_at
    if not force and _programs_cache and (time.time() - _programs_cached_at) < 600:
        return _programs_cache
    out: dict[str, list] = {}
    for lang, (label, key) in LANG_PLAYLISTS.items():
        try:
            req = urllib.request.Request(
                f"https://api.nhk.jp/r8/l/nplaylist/dk/series-rep-{key}.json",
                headers={"User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
        except Exception as e:
            logging.warning("programs API %s: %s", lang, e)
            continue
        items = []
        for it in data.get("result", []):
            sid = (it.get("id") or "").replace("series-rep-", "")
            if sid:
                items.append({"id": sid, "name": it.get("name") or "?"})
        out[lang] = {"label": label, "programs": items}
    _programs_cache = out
    _programs_cached_at = time.time()
    return out


# ─────────────────────────────────────────────────────
# JSON ヘルパ
# ─────────────────────────────────────────────────────
def load_series_conf() -> dict:
    if SERIES_FILE.exists():
        return json.loads(SERIES_FILE.read_text("utf-8"))
    return {"series": []}


def save_series_conf(conf: dict) -> None:
    SERIES_FILE.write_text(
        json.dumps(conf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text("utf-8"))
    return {"downloaded": {}}


# ─────────────────────────────────────────────────────
# HTTP Handler
# ─────────────────────────────────────────────────────
class Handler(http.server.SimpleHTTPRequestHandler):
    # Apple Podcasts は HTTP/1.1 + Range を要求するので明示的に1.1を使う
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        logging.info("%s - %s", self.client_address[0], fmt % args)

    def guess_type(self, path):  # type: ignore[override]
        p = str(path).lower()
        if p.endswith(".m4a"):
            return "audio/mp4"
        if p.endswith(".xml"):
            return "application/rss+xml; charset=utf-8"
        return super().guess_type(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    # ── 静的ファイル配信時に Range を扱う ──
    def send_head(self):  # type: ignore[override]
        path = self.translate_path(self.path)
        # URLにクエリやfragmentがあると拡張子判定が壊れることがあるので除去
        if os.path.isdir(path):
            return super().send_head()
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None
        try:
            fs = os.fstat(f.fileno())
            size = fs.st_size
            ctype = self.guess_type(path)
            range_header = self.headers.get("Range", "")
            if range_header.startswith("bytes="):
                start, end = self._parse_range(range_header[6:], size)
                if start is None:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    f.close()
                    return None
                length = end - start + 1
                f.seek(start)
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(length))
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Last-Modified", self.date_time_string(int(fs.st_mtime)))
                self.end_headers()
                self._range_length = length
                return f
            # フルレスポンス
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", self.date_time_string(int(fs.st_mtime)))
            self.end_headers()
            return f
        except Exception:
            f.close()
            raise

    @staticmethod
    def _parse_range(spec: str, size: int) -> tuple[int | None, int | None]:
        """'bytes=' を除いた中身から (start, end) を返す。失敗時 (None, None)。"""
        try:
            # 複数Range (カンマ区切り) は最初の1つだけ対応
            first = spec.split(",")[0].strip()
            start_s, _, end_s = first.partition("-")
            if start_s == "" and end_s != "":
                # suffix range: 末尾Nバイト
                n = int(end_s)
                if n <= 0:
                    return None, None
                start = max(size - n, 0)
                end = size - 1
            else:
                start = int(start_s)
                end = int(end_s) if end_s else size - 1
            if start < 0 or start >= size or end < start:
                return None, None
            end = min(end, size - 1)
            return start, end
        except (ValueError, IndexError):
            return None, None

    def copyfile(self, source, outputfile):  # type: ignore[override]
        """Range 指定時は length 指定で送信。"""
        length = getattr(self, "_range_length", None)
        if length is not None:
            try:
                shutil.copyfileobj(source, outputfile, length=length)
            finally:
                self._range_length = None  # type: ignore[assignment]
        else:
            shutil.copyfileobj(source, outputfile)

    # ── ルーティング ──
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                return self._serve_file(WEBUI_DIR / "index.html", "text/html; charset=utf-8")
            if path == "/api/status":
                return self._json(self._api_status())
            if path == "/api/series":
                return self._json(self._api_series())
            if path == "/api/programs":
                return self._json(self._api_programs(parsed))
            if path == "/api/episodes":
                return self._json(self._api_episodes())
            if path == "/api/feeds":
                return self._json(self._api_feeds())
            if path == "/api/logs/recent":
                return self._json(self._api_logs())
            if path == "/api/dl/stream":
                return self._api_dl_stream()
            # 静的ファイル
            return super().do_GET()
        except Exception as e:
            logging.exception("GET %s failed", path)
            self._send_error(500, str(e))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8") if length else ""
            data = json.loads(body) if body else {}
            if path == "/api/series":
                return self._json(self._api_series_post(data))
            if path == "/api/dl/run":
                return self._json(self._api_dl_run())
            if path == "/api/dl/retry":
                return self._json(self._api_dl_retry(data))
            self._send_error(404, "not found")
        except Exception as e:
            logging.exception("POST %s failed", path)
            self._send_error(500, str(e))

    # ── レスポンスヘルパ ──
    def _send_error(self, code: int, msg: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"error": msg}, ensure_ascii=False).encode())

    def _json(self, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_error(404, f"{path.name} not found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ── API実装 ──
    def _api_status(self) -> dict:
        host = detect_host()
        lan_ip = detect_lan_ip()
        return {
            "host": host,
            "lan_ip": lan_ip,
            "port": PORT,
            "base_url": f"http://{host}:{PORT}",
            "base_url_ip": f"http://{lan_ip}:{PORT}",
            "dl_state": DL_JOB.state,
            "dl_running": DL_JOB.is_running(),
            "dl_started_at": DL_JOB.started_at,
            "dl_ended_at": DL_JOB.ended_at,
        }

    def _api_series(self) -> dict:
        conf = load_series_conf()
        state = load_state()
        out_series = []
        for s in conf.get("series", []):
            sid = s["id"]
            downloaded = state["downloaded"].get(sid, {})
            real = [m for m in downloaded.values() if m.get("path")]
            out_series.append({
                **s,
                "downloaded_count": len(real),
            })
        return {"series": out_series}

    def _api_programs(self, parsed) -> dict:
        force = "force" in urllib.parse.parse_qs(parsed.query)
        return fetch_all_programs(force=force)

    def _api_episodes(self) -> dict:
        state = load_state()
        conf = load_series_conf()
        name_by_id = {s["id"]: s["name"] for s in conf.get("series", [])}
        rows = []
        for sid, eps in state["downloaded"].items():
            for ep_id, m in eps.items():
                if not m.get("path"):
                    continue
                rows.append({
                    "episode_id": ep_id,
                    "series_id": sid,
                    "series_name": name_by_id.get(sid, sid),
                    "title": m.get("title"),
                    "description": m.get("description"),
                    "broadcast_date": m.get("broadcast_date"),
                    "path": m.get("path"),
                    "url": "/" + urllib.parse.quote(m["path"], safe="/"),
                    "expected_duration_s": m.get("expected_duration_s"),
                    "actual_duration_s": m.get("actual_duration_s"),
                    "validation": m.get("validation"),
                    "short_confirmed": m.get("short_confirmed", False),
                })
        rows.sort(key=lambda x: x.get("broadcast_date") or "", reverse=True)
        return {"episodes": rows}

    def _api_feeds(self) -> dict:
        host = detect_host()  # 例: MacBook-Pro.local
        short_host = host[:-6] if host.endswith(".local") else host
        lan_ip = detect_lan_ip()
        # series.json から id→name を取り、表示名を埋める
        conf = load_series_conf()
        name_by_id = {s["id"]: s["name"] for s in conf.get("series", [])}
        items = []
        if FEEDS_DIR.exists():
            for f in sorted(FEEDS_DIR.glob("*.xml")):
                stem = f.stem  # 通常は series id
                rel_quoted = urllib.parse.quote("feeds/" + f.name, safe="/")
                base_local = f"{host}:{PORT}/{rel_quoted}"
                base_short = f"{short_host}:{PORT}/{rel_quoted}"
                base_ip = f"{lan_ip}:{PORT}/{rel_quoted}"
                items.append({
                    "id": stem,
                    "name": name_by_id.get(stem, stem),
                    "filename": f.name,
                    # http:// (確認・コピー用)
                    "url_local": f"http://{base_local}",
                    "url_short": f"http://{base_short}",
                    "url_ip": f"http://{base_ip}",
                    # podcast:// (Apple Podcasts に直接購読リンク)
                    "podcast_local": f"podcast://{base_local}",
                    "podcast_short": f"podcast://{base_short}",
                    "podcast_ip": f"podcast://{base_ip}",
                })
        return {
            "feeds": items,
            "host": host,
            "short_host": short_host,
            "lan_ip": lan_ip,
            "port": PORT,
        }

    def _api_logs(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        log_path = LOGS_DIR / f"run-{today}.log"
        lines: list[str] = []
        if log_path.exists():
            with log_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()[-100:]
        return {"date": today, "lines": [ln.rstrip() for ln in lines]}

    def _api_series_post(self, data: dict) -> dict:
        # 入力を必要なフィールドだけに正規化
        new_series = []
        for s in data.get("series", []):
            if not s.get("id") or not s.get("name"):
                continue
            entry = {
                "id": s["id"],
                "name": s["name"],
                "page_url": s.get("page_url") or f"https://www.nhk.jp/p/rs/{s['id']}/plus/",
                "enabled": bool(s.get("enabled", True)),
            }
            if s.get("group_by_weekday"):
                entry["group_by_weekday"] = True
            new_series.append(entry)
        save_series_conf({"series": new_series})
        # 番組設定変更に合わせてフィードも再生成 (新規追加分の空フィードも作る)
        try:
            import make_feeds

            make_feeds.build_all_feeds()
        except Exception as e:
            logging.warning("series保存後のRSS再生成失敗: %s", e)
        return {"ok": True, "count": len(new_series)}

    def _api_dl_run(self) -> dict:
        started = DL_JOB.start()
        return {"started": started, "state": DL_JOB.state}

    def _api_dl_retry(self, data: dict) -> dict:
        """指定エピソードを state から消し、ファイルも削除して DL ジョブを起動。"""
        ep_id = data.get("episode_id")
        series_id = data.get("series_id")
        if not ep_id or not series_id:
            return {"error": "episode_id と series_id が必須"}
        state = load_state()
        eps = state["downloaded"].get(series_id, {})
        meta = eps.get(ep_id)
        if not meta:
            return {"error": "該当エピソードが state にありません"}
        # 既存ファイル削除
        rel = meta.get("path")
        if rel:
            p = ROOT / rel
            if p.exists():
                p.unlink()
        # state から削除 (+ short_confirmed があってもクリア = 再評価)
        del eps[ep_id]
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # DL ジョブ起動
        started = DL_JOB.start()
        return {"started": started, "state": DL_JOB.state, "episode_id": ep_id}

    def _api_dl_stream(self) -> None:
        """Server-Sent Events"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        q = DL_JOB.subscribe()
        try:
            # 初期メッセージ (現在状態)
            self._sse(json.dumps({
                "type": "status",
                "state": DL_JOB.state,
                "running": DL_JOB.is_running(),
            }))
            heartbeat = time.time()
            while True:
                try:
                    line = q.get(timeout=15)
                except queue.Empty:
                    # heartbeat (SSEのコメント行)
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    continue
                if line == "__END__":
                    self._sse(json.dumps({
                        "type": "end",
                        "state": DL_JOB.state,
                    }))
                    break
                self._sse(json.dumps({"type": "log", "line": line}))
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            DL_JOB.unsubscribe(q)

    def _sse(self, data: str) -> None:
        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
        self.wfile.flush()


def detect_host() -> str:
    try:
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


def detect_lan_ip() -> str:
    """このMacのLAN IP (例: 192.168.1.42)。失敗時は 127.0.0.1。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        # 実際には通信しないが getsockname で経路上のIPが取れる
        s.connect(("8.8.8.8", 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        handlers=[
            logging.FileHandler(LOGS_DIR / "serve.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    with ThreadingTCPServer((BIND, PORT), Handler) as httpd:
        host = detect_host()
        logging.info("serving on %s:%d  (Web UI: http://%s:%d/)", BIND, PORT, host, PORT)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logging.info("shutdown")
    return 0


if __name__ == "__main__":
    sys.exit(main())
