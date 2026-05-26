#!/usr/bin/env python3
"""既存DL済ファイル全部にvalidationをかけて state.json に結果を書き込む。"""
from __future__ import annotations

import json
import logging
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nhk_dl import (
    STATE_FILE, ROOT, API_BASE, USER_AGENT,
    parse_iso_duration, probe_duration, validate_duration,
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("validate")
    state = json.loads(STATE_FILE.read_text("utf-8"))

    for sid, eps in state["downloaded"].items():
        # APIから expected_duration を一括取得
        try:
            req = urllib.request.Request(API_BASE.format(sid=sid), headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
        except Exception as e:
            log.warning("API取得失敗 %s: %s", sid, e)
            data = {}
        expected_by_id: dict[str, float | None] = {}
        for it in data.get("result", []):
            audio = (it.get("audio") or [{}])[0]
            expected_by_id[it["id"]] = parse_iso_duration(audio.get("duration"))

        for ep_id, m in eps.items():
            if m.get("skipped_as_rerun"):
                continue
            rel = m.get("path")
            if not rel:
                continue
            src = ROOT / rel
            if not src.exists():
                continue
            actual = probe_duration(src)
            expected = expected_by_id.get(ep_id) or m.get("expected_duration_s")
            v = validate_duration(actual, expected, log, src.name)
            m["actual_duration_s"] = actual
            m["expected_duration_s"] = expected
            m["validation"] = v

    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("state.json 更新完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
