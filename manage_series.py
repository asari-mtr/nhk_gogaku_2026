#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["questionary>=2.0"]
# ///
"""series.json を対話的に編集するCLI。

NHKの語学番組リストをAPIから取得し、チェックボックスUIで
- 有効にする番組を選択
- 「曜日別ディレクトリに分ける」番組を選択
してから series.json に書き出す。

使い方:
    uv run manage_series.py
    # または
    chmod +x manage_series.py && ./manage_series.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import questionary

ROOT = Path(__file__).resolve().parent
SERIES_FILE = ROOT / "series.json"

# 言語ごとの集約APIキー (NHKの内部ID)
LANG_PLAYLISTS: dict[str, str] = {
    "english": "gogakuEnglishRadio-CBJZTZ4ATE",
    "chinese": "gogakuChineseRadio-PPZNQC8STT",
    "hangeul": "gogakuHangeulRadio-6R1DDSVHP7",
    "french": "gogakuFrenchRadio-FWTUVSSV6V",
    "german": "gogakuGermanRadio-P9V93PZKBD",
    "italian": "gogakuItalianRadio-JEEVCV5T8J",
    "spanish": "gogakuSpanishRadio-T2DDA9VIBV",
    "portuguese": "gogakuPortugueseRadio-DLG5G7E8GT",
    "russian": "gogakuRussianRadio-25N5GJGEYF",
    "other": "gogakuOtherRadio-GG73L1WTSD",
}
LANG_LABEL_JA: dict[str, str] = {
    "english": "英語",
    "chinese": "中国語",
    "hangeul": "ハングル",
    "french": "フランス語",
    "german": "ドイツ語",
    "italian": "イタリア語",
    "spanish": "スペイン語",
    "portuguese": "ポルトガル語",
    "russian": "ロシア語",
    "other": "その他",
}

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_all_programs() -> list[dict]:
    """全言語の番組を {lang, id, name} のリストで返す。"""
    out: list[dict] = []
    for lang, key in LANG_PLAYLISTS.items():
        try:
            data = fetch_json(
                f"https://api.nhk.jp/r8/l/nplaylist/dk/series-rep-{key}.json"
            )
        except Exception as e:
            print(f"[warn] {lang} の取得失敗: {e}", file=sys.stderr)
            continue
        for it in data.get("result", []):
            sid = (it.get("id") or "").replace("series-rep-", "")
            name = it.get("name") or "?"
            if sid:
                out.append({"lang": lang, "id": sid, "name": name})
    return out


def load_series() -> dict:
    if SERIES_FILE.exists():
        return json.loads(SERIES_FILE.read_text("utf-8"))
    return {"series": []}


def save_series(conf: dict) -> None:
    SERIES_FILE.write_text(
        json.dumps(conf, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    print("NHK 語学番組リストを取得しています...")
    programs = fetch_all_programs()
    if not programs:
        print("番組リストを取得できませんでした。")
        return 1
    print(f"  {len(programs)} 番組を取得しました\n")

    conf = load_series()
    existing = {s["id"]: s for s in conf.get("series", [])}

    # 番組チェックボックス選択肢を構築 (言語ごとにグループ化、現在ONのものはchecked)
    choices = []
    for lang in LANG_PLAYLISTS.keys():
        lang_progs = [p for p in programs if p["lang"] == lang]
        if not lang_progs:
            continue
        # 言語見出し (非選択ダミー)
        choices.append(
            questionary.Separator(f"── {LANG_LABEL_JA.get(lang, lang)} ──")
        )
        for p in lang_progs:
            cur = existing.get(p["id"])
            is_on = bool(cur and cur.get("enabled", True))
            title = f"{p['name']}  [{p['id']}]"
            choices.append(questionary.Choice(title, value=p["id"], checked=is_on))

    selected_ids: list[str] | None = questionary.checkbox(
        "ダウンロード対象にする番組を選択 (スペースで切替、Enterで確定):",
        choices=choices,
    ).ask()
    if selected_ids is None:
        print("中断しました。")
        return 1

    if not selected_ids:
        confirm = questionary.confirm(
            "1つも選択されていません。series.json を空にしてよいですか?",
            default=False,
        ).ask()
        if not confirm:
            print("中断しました。")
            return 1

    # 曜日別ディレクトリ対象を選ぶ (選択した番組の中から)
    weekday_choices = []
    for sid in selected_ids:
        p = next((x for x in programs if x["id"] == sid), None)
        if not p:
            continue
        cur = existing.get(sid)
        is_weekday = bool(cur and cur.get("group_by_weekday", False))
        weekday_choices.append(
            questionary.Choice(
                f"{p['name']}  [{sid}]",
                value=sid,
                checked=is_weekday,
            )
        )

    weekday_ids: list[str] = []
    if weekday_choices:
        result = questionary.checkbox(
            "曜日別サブディレクトリに分ける番組を選択 (曜日でテーマが違う番組向け):",
            choices=weekday_choices,
        ).ask()
        if result is None:
            print("中断しました。")
            return 1
        weekday_ids = result

    # series.json を組み立て
    prog_by_id = {p["id"]: p for p in programs}
    new_series = []
    for sid in selected_ids:
        p = prog_by_id.get(sid)
        if not p:
            # ありえないが、既存の不明IDは保持
            old = existing.get(sid)
            if old:
                new_series.append(old)
            continue
        entry: dict = {
            "id": sid,
            "name": p["name"],
            "page_url": f"https://www.nhk.jp/p/rs/{sid}/plus/",
            "enabled": True,
        }
        if sid in weekday_ids:
            entry["group_by_weekday"] = True
        new_series.append(entry)

    new_conf = {"series": new_series}

    # 変更内容のプレビュー
    print("\n=== 新しい series.json ===")
    print(json.dumps(new_conf, ensure_ascii=False, indent=2))
    print()

    confirm = questionary.confirm("この内容で保存しますか?", default=True).ask()
    if not confirm:
        print("保存をキャンセルしました。")
        return 0

    save_series(new_conf)
    print(f"\n保存しました: {SERIES_FILE}")
    print(f"対象番組: {len(new_series)} 件  (曜日別: {len(weekday_ids)} 件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
