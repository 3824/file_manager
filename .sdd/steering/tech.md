## アーキテクチャ
- `run.py` から `src/file_manager/main.py` の `MainWindow` を呼び出し、中心に `FileManagerWidget` を配置する構成です。
- `CustomFileSystemModel` と `FileSortFilterProxyModel` がファイルツリーと詳細リストを管理し、チェックボックス列やカスタムカラムを提供します。
- 機能ごとにダイアログ (`file_search_dialog.py` など) と処理モジュール (`file_search.py` など) を分離し、Qt のシグナルで UI とワーカーを連携させます。
- ディスク分析・検索インデックス・動画処理は `QThread` 派生ワーカーでバックグラウンド実行され、UI の応答性を保ちます。

## 使用技術
- 言語: Python 3.13
- UI: PySide6 (Qt Widgets)
- データ処理: sqlite3 (ファイルインデックス), pathlib / os
- オプション依存: OpenCV + NumPy（動画ダイジェスト）、winshell / send2trash（ゴミ箱移動）
- ビルド: PyInstaller スクリプト (`build_exe.py`)
- パッケージング: `setup.py` で `gui-file-manager` コンソールスクリプトを定義
- テスト: pytest, pytest-qt, pytest-mock, pytest-cov

## 開発環境とコマンド
- 仮想環境作成: `python3 -m venv venv` 後に各 OS に応じてアクティベートします。
- 依存導入: `pip install -r requirements.txt` と `pip install -r requirements-test.txt` を実行します。
- アプリ起動: `python run.py` で GUI を立ち上げられます。
- 静的解析・整形: `flake8`, `black .`, `isort .` をプロジェクト方針として実行します。
- テスト: `pytest` でユニットテストを実行します。
- 配布ビルド: `python build_exe.py` で PyInstaller による単一バイナリを生成します。

## 環境変数
- 機密情報や API キーは `.env` で管理し、コードには直書きしない方針です。
- ヘッドレス環境では `QT_QPA_PLATFORM=offscreen` を自動設定して描画関連のエラーを回避します。
- ファイル検索インデックスは既定で `~/.file_manager_index.db` に保存され、コードの引数で保存先を差し替えられます。
