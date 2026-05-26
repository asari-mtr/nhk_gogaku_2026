# nhk_gogaku_2026

NHKラジオ語学番組の聴き逃し配信を、Mac で自動ダウンロードして iPhone の Podcast アプリで聴けるようにする仕組み。

- ⏰ 毎日朝9:00に新しいエピソードを自動DL（聴き逃し配信は約1週間で消える）
- 🎙 配信形式そのまま (AAC/m4a) で**無劣化保存** (5分番組で約 1.7MB)
- 📱 iPhone から Podcast アプリで購読 → **外出先でもオフライン再生**
- 🌐 ブラウザの**Web UI** で全操作完結（ターミナル不要）

---

## ⚡ ワンライナーでインストール

技術的なことは分からなくても、ターミナルに **以下の1行をコピペするだけ** で完了します:

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/asari-mtr/nhk_gogaku_2026/main/bootstrap.sh)"
```

何が起きるか:

1. OS（macOS / Linux）と必要ツールを **チェック**
2. 不足があれば **OS別のインストールコマンドを画面に表示して終了**（自動インストールはしません）
3. 揃っていればプロジェクトを `~/nhk_gogaku_2026` に配置
4. 対話的に **スケジューラ / 実行時刻 / 保存形式 / mp3ビットレート** を聞かれて、選ぶだけ

### 対応OS

| OS | 状況 |
|---|---|
| **macOS** | ✅ サポート |
| **Linux** (Debian/Ubuntu/Fedora/Arch/openSUSE) | ✅ サポート |
| **WSL** (Windows Subsystem for Linux) | ✅ サポート |
| **Windows ネイティブ** | ❌ 動きません。**WSL** を使ってください（後述） |

### 必要な外部ツール

事前に、または bootstrap.sh が案内した時点で、以下を導入してください。

| ツール | 用途 | 必須 / 任意 |
|---|---|---|
| **git** | このプロジェクトを GitHub から取得 / 更新する | 必須 |
| **curl** | bootstrap.sh の取得と、API/フィードへのアクセス | 必須 |
| **python3** (3.10+) | 各スクリプトの実行 | 必須 |
| **ffmpeg** | NHK の HLS (AES-128暗号化) 復号 + m4a/mp3 変換 | 必須 |
| **uv** | `manage_series.py` (CLIで番組選択) の依存解決 | 任意 (Web UI のみ使うなら不要) |

> Python は標準ライブラリのみで動きます。pip インストールが必要な追加パッケージはありません。

### bootstrap.sh の依存チェックについて

`bootstrap.sh` は **依存ツールのチェック専用** です。不足を検出したら、その OS で使うべきインストールコマンドを画面に表示して終了します。`sudo` や `brew install` を勝手に実行することはありません。

```text
⚠ 以下のコマンドが不足しています:

  ・ffmpeg
      brew install ffmpeg

✗ これらを手動でインストールしてから、もう一度このコマンドを実行してください。
```

表示されたコマンドを自分でコピペ実行 → もう一度 bootstrap.sh のワンライナーを実行、という流れです。

### OS別の参考インストールコマンド

| OS | 必須4つ (git / curl / python3 / ffmpeg) | uv (任意) |
|---|---|---|
| macOS | `brew install git curl python ffmpeg` | `brew install uv` |
| Ubuntu / Debian | `sudo apt install git curl python3 ffmpeg` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Fedora / RHEL | `sudo dnf install git curl python3 ffmpeg` | 同上 |
| Arch | `sudo pacman -S git curl python ffmpeg` | `sudo pacman -S uv` |
| openSUSE | `sudo zypper install git curl python3 ffmpeg` | 同上 |

> **macOSで Homebrew が無い場合**は、まずこちらを実行:
>
> ```sh
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```

### Windows で使いたい場合

PowerShell（管理者）で WSL（Ubuntu）をインストールして、その中で bootstrap.sh を実行します:

```powershell
# 1. WSL + Ubuntu インストール (Windows側で1回)
wsl --install -d Ubuntu
```

WSLのUbuntuが起動したら、依存をUbuntu側に入れて bootstrap を実行:

```sh
# 2. 依存インストール
sudo apt update && sudo apt install -y git curl python3 ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv (任意)

# 3. ワンライナー
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/asari-mtr/nhk_gogaku_2026/main/bootstrap.sh)"
```

WSL から `http://<ホスト名>:8123/` にアクセスする際のネットワーク設定は環境依存。詳しくは Microsoft のWSLネットワークドキュメントを参照。

---

## 1. これは何ができるの？

「忙しくて毎日ラジオの語学番組を聞けない」「外出中の電車で聞きたい」を解決します。

### 主な活用シーン

- **📻 Apple Podcasts で購読** — iPhone のPodcastsアプリにフィードを登録 → 家のWi-Fi圏内で自動DL → 外出先でオフライン再生
- **🎶 Apple Music ライブラリに取り込む** — `downloads/` をライブラリに追加するだけで番組名がアルバム、エピソード名が曲、放送日順のプレイリスト化も可能（メタデータ + 番組ロゴ付き）
- **🌍 Pocket Casts / Overcast / AntennaPod (Android) など他のPodcastアプリ** — 同じRSSフィードを「URL購読」で登録可能
- **🚗 カーオーディオ / Bluetoothスピーカーで流す** — m4a 直接、または mp3 に変換して USB で
- **📚 教材として保管** — 再放送スキップで重複しない、半期分の全エピソードを自動アーカイブ

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

このプロジェクトを好きな場所に配置してください（パスは問いません）。

### ステップ 2: 自動実行を仕掛ける

ターミナルで以下を実行すると、**対話的に設定を聞かれます** (スケジューラ・実行時刻・保存形式・mp3ビットレート)。

```sh
cd <配置したパス>
./scripts/install.sh
```

聞かれる項目:

| 項目 | デフォルト | 説明 |
|---|---|---|
| **スケジューラ** | macOSは `launchd` / Linuxは `cron` | macは launchd 推奨（スリープ復帰後に追いかけ実行） |
| **実行時刻** | `09:00` | `HH:MM` 形式 |
| **保存形式** | `m4a` | mp3 を選ぶこともできる |
| **mp3ビットレート** (mp3選択時) | `128k` | 64k / 128k / 192k |

各選択肢には「★recommend」マークが付くので、迷ったらEnter連打でOK。

#### 非対話モード (スクリプト化用)

```sh
./scripts/install.sh --non-interactive \
  --scheduler launchd --hour 9 --minute 0 --format m4a
# mp3 にする場合
./scripts/install.sh --non-interactive \
  --scheduler launchd --hour 7 --minute 30 --format mp3 --mp3-bitrate 128k
```

#### 確認 / アンインストール

```sh
./scripts/status.sh      # 現在の設定と稼働状況
./scripts/uninstall.sh   # スケジューラから解除（DL済ファイルは残る）
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

## 5. Apple Music で聴く / ライブラリ化する

DLした m4a は **メタデータ（番組名/エピソード名/放送日/番組ロゴ）込み** なので、Apple Music にそのまま放り込めば綺麗にライブラリ化されます。

### 取り込み手順

1. Mac で **Apple Music** アプリを開く
2. メニュー「**ファイル → ライブラリに追加...**」
3. `downloads/` フォルダ全体を選択

### 結果

- **アルバム**: 番組名（例: `[非公式] エンジョイ・シンプル・イングリッシュ`）
- **曲名**: `YYYY-MM-DD(曜) エピソード名`（時系列ソート可能）
- **アーティスト**: `Personal Archive`
- **カバー**: 番組ロゴ画像
- **年**: 放送日

タイトル順でソートすれば自動で時系列に並びます。スマートプレイリスト（「曲名に `(月)` を含む」など）で曜日別の絞り込みも作れます。

### Apple Music サブスク or iTunes Match に入っていれば

iCloud ミュージックライブラリ経由で **iPhone にも自動同期** されます。Podcast購読と二重持ちもアリです。

---

## 6. 他のプラットフォーム / mp3 への変換

### m4a (AAC) の互換性

| 環境 | 状況 |
|---|---|
| Apple Podcasts / Apple Music | ✅ ネイティブ |
| Windows Media Player / Groove / VLC | ✅ |
| Android: Google系 / Pocket Casts / AntennaPod / VLC / Poweramp | ✅ |
| YouTube Music ローカル | ✅ |
| **Spotify ローカルファイル** | ⚠ 不安定（mp3推奨） |
| 古いカーオーディオ・ガラケー | ⚠ mp3 推奨 |

ほぼ全ての現代環境は m4a そのままでOKです。**変換は基本不要**。

### どうしても mp3 にしたいとき

```sh
# 1ファイルだけ
ffmpeg -i input.m4a -c:a libmp3lame -b:a 128k -id3v2_version 3 output.mp3

# downloads/ 全体を一括変換 (元は残したまま downloads_mp3/ に出力)
cd ~/path/to/nhk_gogaku_2026
find downloads -name "*.m4a" | while read f; do
  out="${f/downloads/downloads_mp3}"
  out="${out%.m4a}.mp3"
  mkdir -p "$(dirname "$out")"
  ffmpeg -y -i "$f" -c:a libmp3lame -b:a 128k -id3v2_version 3 "$out"
done
```

⚠ 注意: 元 AAC 48kbps からの再エンコードなので **音質は若干劣化** します（語学番組では実害ほぼなし）。`-b:a 64k` でファイルサイズ抑制 / `-b:a 192k` で念のため余裕、お好みで。

---

## 7. 日常の使い方

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

## 8. 困ったときは

### Q. Web UI に繋がらない

```sh
# サーバが動いてるか確認
./scripts/status.sh

# 再起動
launchctl kickstart -k gui/$(id -u)/local.nhk-gogaku-2026.server

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
./scripts/uninstall.sh
```
再開は `./scripts/install.sh`。

### Q. 全部アンインストールしたい

```sh
./scripts/uninstall.sh
# DL済ファイルや設定も消したい場合
rm -rf <配置したパス>
```

---

## 9. ファイル構成

```
nhk_gogaku_2026/
├── nhk_dl.py                       # 中核: HLSをDLしてm4a保存
├── make_feeds.py                   # RSS (Podcast) XML 生成
├── serve.py                        # ローカルHTTPサーバ + Web UI
├── webui/                          # Web UI (HTML/CSS/JS)
├── manage_series.py                # CLI 版番組選択 (Web UIがあれば不要)
├── series.json                     # 取得対象の番組定義
├── bootstrap.sh                    # ワンライナー用 (curlで取れる)
├── scripts/                        # 対話型インストーラ + 管理ツール
│   ├── install.sh                  #   対話的にスケジューラ/時刻/形式を選択
│   ├── _install_launchd.sh         #   launchd登録の内部スクリプト
│   ├── _install_cron.sh            #   cron登録の内部スクリプト
│   ├── uninstall.sh                #   launchd/cron両方からアンインストール
│   └── status.sh                   #   稼働状況確認
├── config.json                     # install.sh が生成 (format / bitrate / schedule)
├── downloads/                      # DLしたm4a (番組ごとのフォルダ)
├── feeds/                          # 自動生成 RSS XML
├── state/                          # 取得済み状態の保存
└── logs/                           # 実行ログ
```

---

## 10. 動作仕様（詳しく知りたい人向け）

- NHK 公開API `https://api.nhk.jp/r8/l/radioepisode/pl/series-rep-<id>.json` でエピソード一覧取得（認証不要）
- 各エピソードの m3u8 URL を `ffmpeg -c copy` で AES-128 復号しつつ AAC 無変換コピー → `.m4a`
- 聴き逃し配信期間は約1週間、常時5本配信
- 取得済みIDは `state/downloaded.json` で重複DL防止
- **再放送スキップ**: 半期（4-9月 / 10-3月）で同タイトルが再登場した場合は自動スキップ
- **曜日別保存**: `group_by_weekday: true` で `<番組名>/<曜日>/` のサブディレクトリに分割可能（「エンジョイ・シンプル・イングリッシュ」のように曜日でテーマが違う番組向け）
- **RSS自動生成**: DL実行時 / 番組設定保存時に `feeds/<series_id>.xml` を再生成（iTunes拡張対応）

---

## 11. 取得した音声について

- NHK の著作物です。**私的利用の範囲内**でのみ使用してください
- **再配布・公開は不可**。本ツールは家庭内 Wi-Fi に限定する設計です
- NHK の API 仕様は予告なく変わる可能性があります

---

---

## メンテナ・開発者向け

このリポジトリをフォーク/運用する方、コードに貢献する方は [**MAINTAINER.md**](MAINTAINER.md) を参照してください。Public化、GitHub Pages 公開、Analytics トークンの動的注入、Search Console 連携、リリース運用、開発者メモ等をまとめています。
