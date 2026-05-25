# nhk_gogaku_2026

NHKラジオ語学番組の聴き逃し配信を、Mac で自動ダウンロードして iPhone の Podcast アプリで聴けるようにする仕組み。

- ⏰ 毎日朝9:00に新しいエピソードを自動DL（聴き逃し配信は約1週間で消える）
- 🎙 配信形式そのまま (AAC/m4a) で**無劣化保存** (5分番組で約 1.7MB)
- 📱 iPhone から Podcast アプリで購読 → **外出先でもオフライン再生**
- 🌐 ブラウザの**Web UI** で全操作完結（ターミナル不要）

---

## 1. これは何ができるの？

「忙しくて毎日ラジオの語学番組を聞けない」「外出中の電車で聞きたい」を解決します。

```
NHKラジオ語学  →  Mac で自動DL  →  自宅Wi-Fiで配信  →  iPhone Podcastで購読
   (HLS)            (m4a保存)        (HTTPサーバ)        (オフライン再生)
```

ファイル形式は Apple Podcasts 標準の m4a なので、Spotify など他の Podcast アプリでも聴けます。

---

## 2. 必要なもの

| 項目 | 内容 |
|---|---|
| Mac | macOS 12 以上（Apple Silicon / Intel どちらでも） |
| ストレージ | 番組5本/週 × 1.7MB = **年間 500MB ほど** |
| ホームWi-Fi | Mac と iPhone を同じWi-Fiに繋ぐ必要あり |

事前にインストールするもの:
- **Homebrew** （未インストールなら [brew.sh](https://brew.sh) 参照）
- **ffmpeg** （音声処理）
- **uv** （対話CLIの依存解決用）

```sh
brew install ffmpeg uv
```

これだけで OK です。

---

## 3. セットアップ（5分）

### ステップ 1: ファイルを配置

このプロジェクトを `~/workspace/nhk_gogaku_2026/` に置いてください。
別のパスに置く場合は、`com.mitsuteru.*.plist` 2ファイルの中の `WorkingDirectory` と `ProgramArguments` を実パスに書き換えてください。

### ステップ 2: 自動実行を仕掛ける

ターミナルで以下を実行。これだけで「毎日朝9:00に自動DL」と「Web UI サーバ常駐」が有効になります。

```sh
cd ~/workspace/nhk_gogaku_2026
cp com.mitsuteru.nhk-gogaku.plist com.mitsuteru.nhk-server.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mitsuteru.nhk-gogaku.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mitsuteru.nhk-server.plist
```

確認:
```sh
launchctl list | grep nhk
# 2行出ていれば成功
```

### ステップ 3: ブラウザで開く

```sh
open http://MacBook-Pro:8123/
```

または直接 Safari / Chrome のアドレス欄に `http://MacBook-Pro:8123/` を貼って開く。
（`MacBook-Pro` はあなたの Mac のホスト名。違うときは `scutil --get LocalHostName` で確認）

→ Web UI が開きます。

### ステップ 4: 取得する番組を選ぶ

1. ブラウザ画面の **「番組」タブ** を開く
2. **「＋ 番組を編集」** ボタンを押す
3. NHK 全番組リスト（10言語・18番組）が出るので、聴きたい番組にチェック
4. **「保存する」** で完了

### ステップ 5: 初回ダウンロードを実行

画面右上の **「▶ DL実行」** ボタンを押す。

進捗バーが下に出て、数秒〜30秒ほどでDLが完了します。「履歴」タブにエピソードが並んだら成功です。

---

## 4. iPhone で聴く

### ステップ 1: 購読URLを取得

Web UI の **「購読URL」タブ** を開く。各番組に **「QRコード」** ボタンがあります。

### ステップ 2: iPhone で QRを読み取る

1. iPhone のカメラで QR を読み取り、表示されたURLを長押し→コピー
2. **Apple Podcasts** アプリを開く
3. 下タブ **「ライブラリ」** → 右上 **「…」** → **「番組をURLから追加」**
4. コピーしたURLを貼り付け → **「登録」**

### ステップ 3: 自動DL設定（任意）

各番組の歯車アイコン → **「エピソード設定」** で:
- **「自動ダウンロード」** ON
- **「エピソードを削除」** お好みで

これで家のWi-Fi圏内に入った時に新エピソードが自動でiPhoneにDLされ、電車などオフラインでも聴けます。

### iPhone で URL が開けないとき

「購読URL」タブの右上ボタンを押すと URL の形式が切り替わります。お使いのネットワーク環境に合わせて選んでください。

- **「URL: ホスト名」**（推奨初手） — `http://MacBook-Pro:8123/...`
- **「URL: .local」** — `http://MacBook-Pro.local:8123/...`
- **「URL: IPアドレス」**（確実） — `http://192.168.x.x:8123/...`

---

## 5. 日常の使い方

ふだんは**何もしなくて良い**です（朝9:00に自動DL、24時間サーバ稼働）。

たまにこんなときに Web UI を開きます:

| やりたいこと | 操作 |
|---|---|
| 今すぐDLしたい | 右上 **「▶ DL実行」** |
| 番組を増やしたい / 減らしたい | **「番組」タブ → 番組を編集」** |
| いま何本DL済みか確認 | **「ホーム」タブ** の KPI |
| 過去のエピソードを聴きたい | **「履歴」タブ** → 各番組 上位5件 + 「その他のエピソード」展開 |
| 動作ログを確認 | **「ホーム」タブ** 下部の「最近のログ」 |

---

## 6. 困ったときは

### Q. Web UI に繋がらない

```sh
# サーバが動いてるか確認
launchctl list | grep nhk-server

# 再起動
launchctl kickstart -k gui/$(id -u)/com.mitsuteru.nhk-server

# ホスト名確認
scutil --get LocalHostName
```

### Q. DLが失敗する

ターミナルで:
```sh
cd ~/workspace/nhk_gogaku_2026
python3 nhk_dl.py
```
を実行して、エラーメッセージを見てください。多くは `ffmpeg` 未インストール、ネットワーク不調、番組の配信終了が原因。

### Q. iPhone から Podcast 購読URLが開けない

「購読URL」タブで右上ボタンを押し、URL形式を **「IPアドレス」** に切替。これでまず確実に繋がります。

### Q. 一時停止したい

```sh
launchctl bootout gui/$(id -u)/com.mitsuteru.nhk-gogaku
launchctl bootout gui/$(id -u)/com.mitsuteru.nhk-server
```
再開はもう一度 `bootstrap` してください。

### Q. 全部アンインストールしたい

```sh
launchctl bootout gui/$(id -u)/com.mitsuteru.nhk-gogaku
launchctl bootout gui/$(id -u)/com.mitsuteru.nhk-server
rm ~/Library/LaunchAgents/com.mitsuteru.nhk-gogaku.plist
rm ~/Library/LaunchAgents/com.mitsuteru.nhk-server.plist
rm -rf ~/workspace/nhk_gogaku_2026
```

---

## 7. ファイル構成

```
nhk_gogaku_2026/
├── nhk_dl.py                       # 中核: HLSをDLしてm4a保存
├── make_feeds.py                   # RSS (Podcast) XML 生成
├── serve.py                        # ローカルHTTPサーバ + Web UI
├── webui/                          # Web UI (HTML/CSS/JS)
├── manage_series.py                # CLI 版番組選択 (Web UIがあれば不要)
├── series.json                     # 取得対象の番組定義
├── com.mitsuteru.nhk-gogaku.plist  # launchd: 毎日朝9:00 にDL
├── com.mitsuteru.nhk-server.plist  # launchd: Web UI サーバ常駐
├── downloads/                      # DLしたm4a (番組ごとのフォルダ)
├── feeds/                          # 自動生成 RSS XML
├── state/                          # 取得済み状態の保存
└── logs/                           # 実行ログ
```

---

## 8. 動作仕様（詳しく知りたい人向け）

- NHK 公開API `https://api.nhk.jp/r8/l/radioepisode/pl/series-rep-<id>.json` でエピソード一覧取得（認証不要）
- 各エピソードの m3u8 URL を `ffmpeg -c copy` で AES-128 復号しつつ AAC 無変換コピー → `.m4a`
- 聴き逃し配信期間は約1週間、常時5本配信
- 取得済みIDは `state/downloaded.json` で重複DL防止
- **再放送スキップ**: 半期（4-9月 / 10-3月）で同タイトルが再登場した場合は自動スキップ
- **曜日別保存**: `group_by_weekday: true` で `<番組名>/<曜日>/` のサブディレクトリに分割可能（「エンジョイ・シンプル・イングリッシュ」のように曜日でテーマが違う番組向け）
- **RSS自動生成**: DL実行時 / 番組設定保存時に `feeds/<series_id>.xml` を再生成（iTunes拡張対応）

---

## 9. 取得した音声について

- NHK の著作物です。**私的利用の範囲内**でのみ使用してください
- **再配布・公開は不可**。本ツールは家庭内 Wi-Fi に限定する設計です
- NHK の API 仕様は予告なく変わる可能性があります

---

## 10. 開発者向けメモ

- 開発言語: Python 3.10+ (標準ライブラリのみ + ffmpeg)
- 起動時依存追加なし。`manage_series.py` のみ `uv run` で questionary を解決
- Web UI: 素のHTML/CSS/JS（フレームワーク非依存）+ qrcode-generator CDN
- API 一覧: `serve.py` の docstring 参照（`/api/status` `/api/series` `/api/programs` `/api/episodes` `/api/feeds` `/api/dl/run` `/api/dl/stream` `/api/logs/recent`）
