# Maintainer Guide

このプロジェクトを **公開リポジトリとして運用するメンテナ向け** のドキュメント。
利用者向け情報は [README.md](README.md) に集約しています。

---

## 目次

1. [公開状態 (Public 化) の手順](#1-公開状態-public-化-の手順)
2. [GitHub Pages の有効化](#2-github-pages-の有効化)
3. [LP の Analytics トークン動的注入](#3-lp-の-analytics-トークン動的注入)
4. [Search Console / リッチリザルト確認](#4-search-console--リッチリザルト確認)
5. [リリース運用](#5-リリース運用)

---

## 1. 公開状態 (Public 化) の手順

GitHub Free プランでは **Public リポジトリのみ Pages が利用できる** ため、Pages を使うには Public 化が必須。

```sh
gh repo edit asari-mtr/nhk_gogaku_2026 \
  --visibility public \
  --accept-visibility-change-consequences
```

公開すると bootstrap.sh のワンライナー (`raw.githubusercontent.com/...` で取得) もそのまま動くようになります。

---

## 2. GitHub Pages の有効化

Public 化が済んだら:

```sh
gh api -X POST repos/asari-mtr/nhk_gogaku_2026/pages \
  -f "source[branch]=main" \
  -f "source[path]=/docs"
```

公開URL（Pages が立ち上がってから数分後にアクセス可）:

```
https://asari-mtr.github.io/nhk_gogaku_2026/
```

リポジトリ Settings → Pages の GUI からも同じ設定が可能 (Source: Deploy from a branch, Branch: main /docs)。

---

## 3. LP の Analytics トークン動的注入

`docs/` のランディングページに **Cloudflare Web Analytics / Google Analytics 4 / GoatCounter** のいずれか (または複数併用) を入れる場合、**ソースコードにトークンを書かず、GitHub Secrets から自動注入** できます。

### セットアップ

リポジトリ Settings → Secrets and variables → Actions → New repository secret で必要なものだけ登録:

| Secret 名 | 取得元 |
|---|---|
| `CF_ANALYTICS_TOKEN` | Cloudflare → Web Analytics → 新規サイト追加で発行される token |
| `GA_MEASUREMENT_ID` | GA4 → 管理 → データストリーム → 測定ID (`G-XXXXXXXXXX`) |
| `GOATCOUNTER_URL` | `https://<your-code>.goatcounter.com/count` |

3つとも登録不要、1つだけでも複数併用でも可。**Secrets はリポジトリにコミットされず、Actions の実行時にしか参照できない** ので公開リポジトリでも安全です。

### 動作

- main ブランチに `docs/` への変更を push すると `.github/workflows/pages.yml` が起動
- Secret の値を `docs/index.html` のプレースホルダー (`__CF_ANALYTICS_TOKEN__` 等) に置換
- Pages へデプロイ
- Secret が未設定なら、本体 JS がプレースホルダーを検知してスクリプトを読み込まない (=何も入らない)

ローカルで開いている分にはプレースホルダーのままなのでトラッキングは動作せず、開発時に余計な計測を出さずに済みます。

### Analytics を後から差し替えるとき

- CF → GA に変えたい: `CF_ANALYTICS_TOKEN` を削除 + `GA_MEASUREMENT_ID` を追加 → push（or workflow_dispatch）
- 全部止めたい: 全 Secret を削除 + 再デプロイ

コードは触らず、Secret の差し替えだけで切替可能。

---

## 4. Search Console / リッチリザルト確認

### Google Search Console

1. [https://search.google.com/search-console/](https://search.google.com/search-console/) でプロパティ追加 (`https://asari-mtr.github.io/nhk_gogaku_2026/`)
2. URL プレフィックスを選択 → 所有権確認は HTML タグ方式が楽
   - 表示された `<meta name="google-site-verification" content="...">` を Secret `GSC_VERIFICATION` 経由で `docs/index.html` に注入する形にしてもよい (現状は未対応、必要なら同様の仕組みで追加可能)
3. サイトマップ送信: `https://asari-mtr.github.io/nhk_gogaku_2026/sitemap.xml`
4. 「検索パフォーマンス」で表示クエリ / クリック率 / 平均掲載順位を確認

### リッチリザルトテスト

LP の構造化データ (SoftwareApplication / FAQPage / HowTo / BreadcrumbList) が認識されているかチェック:

- [https://search.google.com/test/rich-results](https://search.google.com/test/rich-results)
- URL を入れて「URL をテスト」

### Open Graph / Twitter Card プレビュー

- Facebook: [Sharing Debugger](https://developers.facebook.com/tools/debug/)
- Twitter / X: [Card Validator](https://cards-dev.twitter.com/validator) (廃止傾向のため URL直貼りでDM等にプレビューが出るか確認)

---

## 5. リリース運用

タグでリリースする場合の参考フロー（必須ではない）:

```sh
git tag -a v1.0.0 -m "Initial public release"
git push origin v1.0.0
gh release create v1.0.0 --title "v1.0.0" --notes "初回公開リリース。bootstrap.sh、Web UI、launchd/cron対応。"
```

`bootstrap.sh` の `NHK_REPO_BRANCH` を `main` ではなく `vX.Y.Z` に切り替えれば、安定バージョン固定インストールも可能。

---

## 開発者向けメモ

- 開発言語: Python 3.10+ (標準ライブラリのみ + ffmpeg)
- 起動時依存追加なし。`manage_series.py` のみ `uv run` で questionary を解決
- Web UI: 素のHTML/CSS/JS（フレームワーク非依存）+ qrcode-generator CDN
- API 一覧: `serve.py` の docstring 参照 (`/api/status` `/api/series` `/api/programs` `/api/episodes` `/api/feeds` `/api/dl/run` `/api/dl/stream` `/api/logs/recent`)
- LP の構造化データ: `docs/index.html` の `<script type="application/ld+json">` ブロックを編集
- 配色変数は `webui/style.css` および `docs/style.css` の `:root` ブロックに集約 (両者で同一パレットを使用)
