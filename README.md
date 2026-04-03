# YT Downloader - Chrome拡張機能

YouTubeの動画・音楽をローカルにダウンロードするChrome拡張機能。  
Chrome Native Messaging を使ってローカルの `yt-dlp` を呼び出す仕組みだよ。

---

## フォルダ構成

```text
extension/          ← Chrome拡張機能（これをChromeに読み込む）
├── manifest.json
├── panel.html / panel.js
├── background.js
└── ...

host/               ← Native Messaging Host (Python環境)
├── host.py         ← Pythonブリッジ本体
├── ffmpeg.exe      ← 動画・音声変換ツール
├── install.bat     ← セットアップスクリプト起動用
├── install.ps1     ← インストールスクリプト本体
└── (その他UIツール等)
```

---

## セットアップ手順

### 1. Chrome に拡張機能を読み込む

1. Chromeで `chrome://extensions/` を開く
2. 右上の「デベロッパーモード」をONにする
3. 「パッケージ化されていない拡張機能を読み込む」をクリック
4. `extension/` フォルダを選択
5. **表示された「拡張機能ID」（32文字）をコピーしておく**

### 2. Native Host をインストール

1. `host/install.bat` をダブルクリック
2. 青い黒画面(PowerShell)が開いたら、さきほどコピーした拡張機能IDを貼り付けてEnterを押す
    - (※ yt-dlp と Pillow が自動で `pip install` されます)
3. 完了したらChromeを再起動

### 3. 使い方

1. YouTubeの動画ページを開く
2. 拡張機能アイコンをクリック
3. 形式（MP3/MP4など）と品質を選ぶ
4. 保存先フォルダを入力（空欄なら `~/Downloads`）
5. 「ダウンロード」ボタンをクリック！

---

## 依存ツール・環境

| ツール       | 説明                                                                     |
| ------------ | ------------------------------------------------------------------------ |
| Python 3.x   | 事前にPCにインストールし、PATH に通っている必要があります                |
| yt-dlp       | `install.bat` 実行時に `pip` で自動インストールされます                  |
| Pillow       | `install.bat` 実行時に `pip` で自動インストールされます (サムネ処理用)  |
| ffmpeg.exe   | `host/` 直下に配置済みである必要があります                               |