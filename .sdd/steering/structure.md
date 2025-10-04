## ルートディレクトリ構成
- `src/` : アプリ本体。`file_manager/` 配下に UI ウィジェットと各機能モジュールがまとまっています。
- `tests/` : pytest ベースの自動テストを格納しています。
- `docs/` : 利用ガイドや設定手順などの日本語ドキュメントを格納しています。
- `assets/` : アイコンやスクリーンショット等のリソース配置用ディレクトリです。
- `.sdd/` : Spec Driven Development 用のメタドキュメント一式です。
- ルート直下には `run.py` (起動スクリプト), `build_exe.py` (PyInstaller 用), `setup.py` (配布設定) などの補助スクリプトがあります。

## コード構成パターン
- UI のエントリポイントは `main.py` の `MainWindow` と `FileManagerWidget` で、左右分割レイアウトによりファイルツリーと詳細ビューを提供します。
- 共通ロジックは `file_manager.py` に集約し、カスタムモデル (`CustomFileSystemModel`) やデリゲートで列表示や選択状態を管理します。
- 機能単位でモジュールを分割し、UI ダイアログ (`*_dialog.py`) と処理ロジック (`file_search.py`, `disk_analyzer.py`, `video_digest.py`, `video_duplicates.py`) を対で実装しています。
- 処理負荷の高いタスクは `VideoDigestWorker` や `DiskAnalysisWorker` などのワーカークラスでバックグラウンド実行し、Qt のシグナルで結果を UI に通知します。

## ファイル命名規則
- Python ファイルはスネークケースで命名され、機能を表す語を組み合わせています。
- ダイアログを提供するファイルは `*_dialog.py`、ワーカーや生成ロジックは `*_worker` / `*_generator` クラス名で表現します。
- テストコードは `tests/` 配下で `test_*.py` 形式を採用し、共通フィクスチャは `conftest.py` にまとまっています。

## 主要な設計原則
- UI と重い処理を分離し、シグナル/スロットで疎結合に連携させて応答性を維持します。
- オプショナルな依存関係は import 成否で機能フラグを切り替え、未導入環境でも安全に動作させます。
- `QSettings` を用いて表示設定やユーザー選択を永続化し、再起動時の状態復元を行います。
- Windows と macOS の両方で同等機能を提供できるよう、パス操作やゴミ箱処理を抽象化しています。
