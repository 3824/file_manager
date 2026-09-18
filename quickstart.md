# クイックスタートガイド

このドキュメントでは、GUIファイラーのセットアップから起動、基本的な使い方までを素早く解説します。

---

## 1. 動作環境

* **OS**: Windows 10/11, macOS 13+, Linux
* **Python**: 3.13 (推奨) または 3.9 以上

---

## 2. セットアップ & 起動（推奨）

リポジトリをクローンした後、OSに合わせて以下の起動スクリプトを実行してください。仮想環境の構築、パッケージのインストール、アプリケーションの起動が自動で行われます。

### Windows
```cmd
start.bat
```

### macOS / Linux
```bash
chmod +x start.sh  # 初回のみ実行権限を付与
./start.sh
```

---

## 3. 手動セットアップ

手動で環境を構築する場合は以下の手順で行います。

1. **仮想環境の作成と有効化**:
   - Windows: `python -m venv .venv` → `.\.venv\Scripts\Activate.ps1`
   - macOS/Linux: `python3 -m venv .venv` → `source .venv/bin/activate`

2. **依存パッケージのインストール**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **起動**:
   ```bash
   python run.py
   ```

---

## 4. ファイル名翻訳機能の設定（オプション）

外国語のファイル名を日本語等に一括翻訳・リネームする機能を利用する場合、プロジェクト直下に `.env` を作成します。

### Ollama（ローカルLLM・無料・推奨）
```ini
TRANSLATION_BACKEND=ollama
OLLAMA_MODEL=gemma2:2b
```
※ 事前に [Ollama](https://ollama.com/) を起動し、`ollama run gemma2:2b` を実行しておきます。

### Google Cloud Translation API
```ini
TRANSLATION_BACKEND=google
TRANSLATION_API_KEY=your_api_key_here
```

---

## 5. 基本的な使い方

* **フォルダ移動**: 左ペインのツリーまたは右ペインのフォルダをダブルクリックします。
* **表示切替**: ツールバーで「詳細」「リスト」「アイコン」表示を切り替えられます。
* **ファイル操作**: 右クリックメニューから開く、コピー、切り取り、貼り付け、名前変更、ゴミ箱移動が可能です。
* **検索・絞り込み**: ツールバーの検索バーでリアルタイム絞り込み、詳細検索ダイアログ（🔍）でインデックス検索が可能です。
* **動画プレビュー & プレイヤー**: 動画選択時にサムネイル・シークバー付きプレビューが表示され、ダブルクリックで専用プレイヤーを起動できます。
* **重複・類似ファイル整理**: ツールバーのボタンから「ファイル名類似度」「同一サイズ」「動画クラスタリング」のダイアログを開き、重複ファイルを一括検出・整理できます。
* **ディスク分析**: ツールバーの「📊」ボタンからフォルダやドライブの容量を円グラフで可視化できます。

---

詳細な操作方法や設定は [howtouse.md](./howtouse.md) および [README.md](./README.md) を参照してください。
