# 開発仕様書 (Specification)

## 1. プロジェクト基本情報
* **名称**: GUIファイラー (Cross-Platform File Manager)
* **目的**: Windows / macOS / Linux で動作する、メディア管理・ファイル整理機能に強みを持つ高機能GUIファイルマネージャー。
* **主要技術スタック**:
  * 言語: Python 3.13 (Python 3.9+ 互換)
  * GUIフレームワーク: PySide6 (Qt 6)
  * UIデザイン & アイコン: `qtawesome`, カスタム Fluent / Mica QSS テーマ
  * 動画・画像処理: OpenCV (`opencv-python`), `numpy`
  * メディア再生: PySide6 QtMultimedia (`QMediaPlayer`, `QVideoWidget`)
  * キャッシュ & インデックス: SQLite 3 (`video_cluster.db`, `video_metadata_cache`)
  * ファイル操作: `pathlib`, `shutil`, `send2trash`, `winshell`
  * 翻訳エンジン: `ollama` (ローカルLLM), Google Cloud Translation API

---

## 2. システムアーキテクチャ

```
src/file_manager/
├── main.py                     # エントリーポイント & アプリケーション初期化
├── file_manager.py             # メインコントローラー & FileManagerWidget
├── views.py                    # 表示ビュー (QTreeView, QListView)
├── left_pane.py                # 左ペイン (フォルダツリー, ドライブバー)
├── qt_models.py                # カスタムファイルシステムモデル
├── ui_theme.py                 # テーマエンジン (Light, Dark, Fluent, Mica)
├── ui_icons.py                 # アイコンマネージャー (qtawesome)
├── settings_dialog.py          # 設定ダイアログ & QSettings永続化
├── video_player_widget.py      # 動画プレビュー & ミニプレイヤー
├── video_digest.py             # 動画ダイジェスト抽出エンジン
├── video_cluster_engine.py     # 動画クラスタリング解析
├── video_cluster_db.py         # 動画クラスタSQLite永続化
├── filename_similarity.py      # ファイル名類似度解析
├── filename_translation.py     # ファイル名翻訳サービス
├── disk_analyzer.py            # ディスク使用量解析
└── test_runner_dialog.py       # 内蔵テストランナー
```

### アーキテクチャ原則
- **MVC / モデル・ビュー分離**: Qt の Model/View アーキテクチャをベースに、カスタムデータモデルとビューを分離。
- **非同期処理 (マルチスレッド)**: サムネイル生成、動画特徴量抽出、ファイル名翻訳、ディスクスキャン、テスト実行などの重い処理は `QThread` / `QThreadPool` / `QRunnable` を用いてバックグラウンドで実行し、UIの応答性を維持。
- **フォールバック設計**: OpenCV や send2trash、Ollama 等のオプションライブラリ・サービスが未導入の環境でも、アプリケーション本体は安全にフォールバック動作する。

---

## 3. モジュール仕様詳細

### 3.1 メインウィンドウ & UI
- **`FileManagerWidget`**: アプリケーションの中心となるウィジェット。ツールバー、ドライブバー、スプリッター（左右ペイン）、ステータスバー、プレビューペインを統括。
- **`LeftPaneWidget`**: 左ペイン。システムドライブ一覧および階層フォルダツリーを表示。
- **`Views` & `QtModels`**: 右ペイン。詳細表示（カスタムカラム対応）、アイコン表示、リスト表示を切り替え可能。
- **`UITheme`**: Fluent / One Commander 風のモダンテーマ。ダーク / ライトモード、Mica 効果、システムアクセントカラーに対応。

### 3.2 動画・メディア機能
- **`VideoPlayerWidget` / `VideoPlayerWindow`**: PySide6 QtMultimedia を用いた動画再生コンポーネント。シークバー、音量、再生/一時停止、ポップアップ単体ウィンドウ再生をサポート。
- **`VideoDigestGenerator` / `VideoDigestDialog`**: OpenCV を用いて動画内の代表フレームを抽出・サムネイル化し、ダイアログでダイジェスト一覧表示。
- **`VideoClusterEngine` / `VideoClusterDB`**: 動画の映像特徴量（カラーヒストグラム等）を抽出し、SQLite DB にキャッシュして高速な類似動画クラスタリングを提供。

### 3.3 ファイル整理・検索機能
- **`FilenameSimilarity` / `FilenameSimilarityDialog`**: レーベンシュタイン距離やトークン分割によるファイル名類似度計算を行い、重複・派生ファイルを検出。
- **`SameFilesize` / `SameFilesizeDialog`**: 同一ファイルサイズのアイテムを高速グルーピング。
- **`FileSearch` / `FileSearchDialog`**: SQLite インデックスを用いたキーワード検索。
- **`DiskAnalyzer` / `DiskAnalysisDialog`**: ディスク/フォルダの容量を走査し、円グラフによる階層的視覚化を提供。

### 3.4 翻訳リネーム機能
- **`FilenameTranslationService`**: ローカル LLM (Ollama) または Google Cloud Translation API を介してファイル名を翻訳。
- **`TranslatePreviewDialog`**: 翻訳前後の差分テーブルを表示し、選択したファイルのみを安全にリネーム実行。

---

## 4. 非機能要件
1. **クロスプラットフォーム性**: Windows, macOS, Linux でパス区切り文字やファイルシステム依存を吸収。
2. **パフォーマンス**: 大量ファイル（1万件以上）のディレクトリでもフリーズせず、遅延ロード（FetchMore）および非同期スキャンを実施。
3. **データ永続化**: `QSettings` (レジストリ / plist / ini) によるユーザー設定保持、SQLite によるキャッシュ高速化。
