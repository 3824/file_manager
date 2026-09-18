# GUIファイラー (Cross-Platform File Manager)

Python 3.13 と PySide6 (Qt 6) で構築された、モダンで高機能なクロスプラットフォーム対応のファイルマネージャー（GUIファイラー）です。
エクスプローラーライクな直感的操作感に加え、**動画サムネイル・ダイジェスト表示**、**動画クラスタリング**、**ファイル名類似度・重複検出**、**ファイル名多言語翻訳**、**ディスク使用量分析** など、メディア管理やファイル整理に特化した強力な機能を備えています。

---

## 主な特徴

### 1. モダン＆洗練されたUI
- **テーマ対応**: Fluent / Mica（Windows 11）対応、ライト / ダークテーマの自動追従および手動切り替え
- **統一アイコン**: `qtawesome` による高解像度ベクターアイコン
- **2ペイン構成**:
  - **左ペイン**: ドライブバー、ディレクトリツリー、クイックアクセス
  - **右ペイン**: ファイル一覧（詳細 / リスト / アイコン表示切替）、列の表示・非表示・ソートカスタマイズ
- **視認性向上**: ファイル種類・属性別のカラーリング、フォントサイズ変更

### 2. 強力な動画・メディア管理
- **動画ダイジェスト**: 複数フレームを自動抽出してダイジェスト（サムネイル一覧）をポップアップ表示
- **動画プレビュー & プレイヤー**: 組み込みのミニプレイヤーおよび専用ウィンドウで動画をスムーズに再生
- **動画クラスタリング**: 映像特徴量（カラーヒストグラムやCLIP等）とSQLiteキャッシュを活用した類似動画の自動分類・グループ化
- **高速メタデータ取得**: 再生時間（Duration）、解像度、FPS などを非同期で取得して一覧に表示

### 3. ファイル整理・重複検出
- **ファイル名類似度検出**: レーベンシュタイン距離やトークン類似度に基づき、似た名前のファイルをグルーピングして一括整理
- **同一サイズ検出**: ファイルサイズ一致による重複候補の高速検出
- **安全なゴミ箱移動**: `send2trash` / `winshell` を用いたOS標準のゴミ箱への安全な移動

### 4. ファイル名多言語翻訳（リネーム）
- **多言語対応**: 外国語のファイル名を日本語などに自動翻訳してリネーム
- **柔軟なバックエンド**:
  - **Ollama (ローカルLLM)**: 完全無料・オフライン・プライベートに翻訳（推奨モデル: `gemma2:2b` など）
  - **Google Cloud Translation API**: クラウドAPIによる高精度翻訳
- **プレビュー画面**: リネーム実行前に変更前後のファイル名一覧を確認・個別選択可能

### 5. ディスク使用量分析 & 高速検索
- **ディスク分析**: ドライブやフォルダの容量を円グラフで可視化、階層ごとのドリルダウン探索が可能
- **インデックス検索**: SQLite を用いた高速ファイル検索ダイアログ

---

## 画面構成・機能一覧

```
file_manager/
├── ツールバー       # ナビゲーション(↑/↻)、表示モード切替、ソート、検索、テーマ、各機能ランチャー
├── ドライブバー     # ドライブ(Windows) / マウントポイントのワンクリック切替
├── 左ペイン         # フォルダツリー（展開・折りたたみ）
├── 右ペイン         # ファイル一覧テーブル / グリッド、右クリックコンテキストメニュー
├── プレビュー領域   # 選択ファイルのサムネイル・動画シークバー・ミニプレイヤー
└── ステータスバー   # 選択アイテム数、合計サイズ、バックグラウンド処理状況
```

---

## クイックスタート

### 動作要件
- **OS**: Windows 10/11, macOS 13+, Linux
- **Python**: Python 3.13 (推奨) または Python 3.9 以上

### ワンクリック起動（推奨）

リポジトリをクローン後、OSに合わせて以下のスクリプトを実行してください。仮想環境の作成から依存ライブラリのインストール、起動までが自動で行われます。

- **Windows**:
  ```cmd
  start.bat
  ```
- **macOS / Linux**:
  ```bash
  chmod +x start.sh  # 初回のみ
  ./start.sh
  ```

---

### 手動セットアップ手順

1. **仮想環境の作成と有効化**:
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **依存パッケージのインストール**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **アプリケーションの起動**:
   ```bash
   python run.py
   ```

---

## 翻訳機能の設定 (.env)

ファイル名翻訳機能を利用する場合は、プロジェクトルートに `.env` ファイルを作成して設定を行います。

### A. Ollama（ローカルLLM・無料・推奨）
1. [Ollama 公式サイト](https://ollama.com/) からインストールし、モデルを取得します。
   ```bash
   ollama run gemma2:2b
   ```
2. `.env` に以下を記述します:
   ```env
   TRANSLATION_BACKEND=ollama
   OLLAMA_MODEL=gemma2:2b
   ```

### B. Google Cloud Translation API
Google Cloud Console で Translation API を有効化し、APIキーを取得して記述します:
```env
TRANSLATION_BACKEND=google
TRANSLATION_API_KEY=your_api_key_here
```

---

## スタンドアロン EXE の作成 (Windows)

PyInstaller を用いて単一の実行可能ファイル (.exe) をビルドできます。

```bash
# EXEのビルド
python build_exe.py

# ビルド成果物 (build, dist) のクリーンアップ
python build_exe.py clean
```
※ ビルドされた実行ファイルは `dist/GUIファイラー.exe` に出力されます。

---

## テストの実行

```bash
# 全体テストの実行
pytest

# 特定モジュールのテスト
pytest tests/test_features.py
pytest tests/test_ui_theme.py
pytest tests/test_filename_translation.py
```

---

## プロジェクト構造

```
file_manager/
├── src/file_manager/              # アプリケーションソースコード
│   ├── main.py                    # アプリケーション初期化・メインウィンドウ生成
│   ├── file_manager.py            # メインファイラーウィジェット・UIロジック
│   ├── left_pane.py               # 左ペイン（フォルダツリー・ドライブバー）
│   ├── views.py                   # ファイル一覧ビュー（詳細・アイコン・リスト）
│   ├── qt_models.py               # カスタムQFileSystemModel・データモデル
│   ├── ui_theme.py                # Fluent / Mica テーマ・QSS・カラートークン
│   ├── ui_icons.py                # qtawesome アイコン管理
│   ├── settings_dialog.py         # 設定ダイアログ（一般・外観・検索・動画等）
│   ├── video_player_widget.py     # 動画プレビュー・ミニプレイヤー
│   ├── video_digest.py            # 動画ダイジェスト抽出エンジン (OpenCV)
│   ├── video_cluster_*.py         # 動画クラスタリングエンジン・ワーカー・DB
│   ├── filename_similarity*.py    # ファイル名類似度検出ダイアログ & ロジック
│   ├── same_filesize*.py          # 同一サイズファイル検出ダイアログ
│   ├── filename_translation.py    # ファイル名多言語翻訳サービス (Ollama/Google)
│   ├── translate_preview_dialog.py # 翻訳結果プレビュー・リネームダイアログ
│   ├── disk_analyzer.py           # ディスク使用量分析ロジック
│   ├── disk_analysis_dialog.py    # ディスク使用量円グラフダイアログ
│   └── test_runner_dialog.py      # アプリ内テストランナーダイアログ
├── tests/                         # 単体テスト・UIテスト
├── docs/                          # 設計書・仕様書・改善タスク
├── requirements.txt               # 依存ライブラリ一覧
├── build_exe.py                   # PyInstaller ビルドスクリプト
├── run.py                         # 起動スクリプト
├── start.bat / start.sh           # 自動環境構築＆起動スクリプト
└── README.md                      # 本ドキュメント
```

---

## ライセンス

本プロジェクトは MIT ライセンスの下で公開されています。
