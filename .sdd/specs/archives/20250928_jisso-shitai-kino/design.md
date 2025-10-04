# 設計

## アーキテクチャ統合方法
- 既存の `run.py` → `MainWindow` → `FileManagerWidget` というブートストラップを維持し、各機能を `FileManagerWidget` 内のタブ・ダイアログとして提供します。
- ファイル一覧は `CustomFileSystemModel` と `FileSortFilterProxyModel` を継続利用し、検索結果や重複検出結果を反映する際はプロキシモデル経由で選択状態を更新します。
- 検索・重複検出・ディスク分析など重たい処理は既存の `QThread` ベースワーカーを起動し、Signal/Slot で UI に進捗と結果を通知します。
- オプショナル依存（OpenCV、winshell/send2trash）が読み込めない場合はフラグを OFF にし、UI では警告ラベルと無効化されたボタンでフェールセーフを行います。

## 主要コンポーネント
### MainWindow
- 責務: メニュー・ツールバーを統括し `FileManagerWidget` を中央に配置する。
- I/O: アプリケーションイベント（起動、終了）と `FileManagerWidget` の公開メソッド。
- 依存: PySide6 `QMainWindow`, `FileManagerWidget`。

### FileManagerWidget (`src/file_manager/file_manager.py`)
- 責務: ドライブボタン、フォルダツリー、ファイル一覧を制御し、各機能ダイアログを呼び出す中心コンポーネント。
- I/O: フォルダ選択シグナル、コンテキストメニュー、ツールバーアクション、各ダイアログからのコールバック。
- 依存: `CustomFileSystemModel`, `FileSortFilterProxyModel`, `FileSearchDialog`, `DiskAnalysisDialog`, `VideoDigestDialog`, `VideoDuplicatesDialog`, `QSettings`。

### FileSearchDialog / FileSearchIndex / FileSearchWorker
- 責務: SQLite インデックスの構築・更新とキーワード検索 UI を提供する。
- I/O: 検索条件入力、結果テーブル（ファイルパス・サイズ・更新日時）、`index_updated`, `progress_updated`, `error_occurred` シグナル。
- 依存: `sqlite3`, `Pathlib`, `QThread`, `FileManagerWidget` の `open_path` API。

### VideoDuplicatesDialog / find_duplicate_videos
- 責務: 動画ファイルの重複グループ化、チェック付きリスト表示、ゴミ箱移動。
- I/O: フォルダ選択、`DuplicateGroup` データ、削除要求シグナル、進捗バー。
- 依存: `pathlib`, `hashlib`/`os`, `winshell`/`send2trash`（オプション）、`VideoDuplicatesWorker`。

### DiskAnalysisDialog / DiskAnalyzer / DiskAnalysisWorker
- 責務: フォルダ内サイズ集計と円グラフ描画、ドリルダウン。
- I/O: 対象パス、集計結果辞書（パス・サイズ）、進捗・エラーシグナル。
- 依存: `os`, `Pathlib`, `QThread`, `PieChartWidget`。

### VideoDigestDialog / VideoDigestGenerator / VideoDigestWorker
- 責務: 動画サムネイル生成、設定タブからのパラメータ反映、自動ポップアップ表示。
- I/O: 動画パス、生成済みサムネイル `QPixmap` リスト、エラー通知。
- 依存: OpenCV + NumPy（任意導入）、`QThread`, `QSettings`。

### QSettings ストレージ
- 責務: レイアウト・検索条件・ダイジェスト設定などユーザー設定の永続化。
- I/O: キー/値の読み書き、アプリ終了時の save フック。
- 依存: プラットフォーム標準の設定ストア。

## データモデル
- **ファイルインデックス** (`file_search`): SQLite `files` テーブル（path, name, size, modified_time, is_directory, extension, indexed_time）。プライマリキーは `id`、`path` は UNIQUE。
- **重複動画グループ** (`DuplicateGroup`): `group_id`, `files`（パス・サイズ・類似度）、`score`。UI ではリスト＋チェックボックスで表現。
- **ディスク分析結果**: 辞書 `{path: {"size": int, "children": {...}}}` をワーカーが構築し、ダイアログで円グラフセグメントに変換。
- **動画ダイジェスト設定**: QSettings キー `VideoDigest/thumbnail_count`, `thumbnail_size`, `auto_show`. 生成結果は一時フォルダに PNG として保存し、必要に応じてキャッシュします。
- **UI 状態**: `QSettings` `FileManager/Settings` セクションにカラム可視状態、ソート順、最近開いたパスを保持。

## 処理フロー
1. **起動と基本レイアウト**
   1. `MainWindow` が初期化され `FileManagerWidget` をセット。
   2. `FileManagerWidget` が `CustomFileSystemModel` を初期化し、起動時ドライブ一覧をロード（3秒以内）。
   3. ユーザーがフォルダを選択すると `tree_view.selectionChanged` → `update_file_list` が発火し、右ペインモデルを更新。
2. **ファイル検索**
   1. ユーザーがツールバーまたはメニューから検索を起動し `FileSearchDialog` が表示される。
   2. `FileSearchDialog.start_search` が `FileSearchWorker` を `QThread` に移動し、入力条件（パス範囲・検索種別・上限）を渡す。
   3. ワーカーが SQLite をクエリし `progress_updated` で UI に進捗を通知、完了後 `results_ready` で行データを渡しテーブルに反映。
   4. 結果行をダブルクリックすると `FileManagerWidget.open_path` を呼び、対象フォルダを右ペインに表示。
3. **同一動画ファイル検出**
   1. ユーザーが対象フォルダを指定し `VideoDuplicatesDialog` を表示。
   2. `VideoDuplicatesWorker` がバックグラウンドでファイル一覧を走査し、サイズ一致・ファイル名類似スコアを計算しつつ `progress_signal` を送信。
   3. 完了後 `DuplicateGroup` リストを UI が受け取り、各グループのチェック状態に応じて削除候補を集約。
   4. 「ゴミ箱に移動」実行時、winshell/send2trash が利用可能なら呼び出し、不可なら `QMessageBox` で案内。
4. **フォルダ・ファイルサイズのグラフ表示**
   1. `DiskAnalysisDialog` が対象パスを受け取り `DiskAnalysisWorker` を起動。
   2. ワーカーがディレクトリを再帰走査し、サイズ集計結果を `result_ready` シグナルで返却。
   3. UI は `PieChartWidget` を再レンダリングし、セグメントクリックで詳細表示を更新。切り替え応答は 2 秒以内。
5. **動画ダイジェスト表示**
   1. 動画ファイル選択時に `FileManagerWidget.show_video_digest` を呼び、OpenCV 利用可否を確認。
   2. `VideoDigestWorker` がフレーム抽出・サムネイル保存を実施し、完了時に `VideoDigestDialog` へ結果リストを送信。
   3. `auto_show_digest` が ON の場合はポップアップを即表示し、OFF の場合はコンテキストメニューから手動起動。

## エラーハンドリング
- ワーカーは例外発生時に `error_occurred(str)` を発火し、呼び出し元ダイアログが `QMessageBox` で詳細を通知します。
- OpenCV や winshell 等が未導入の場合は機能フラグを False に設定し、関連ボタンを無効化して警告ラベルを表示します。
- SQLite アクセスエラー時はトランザクションをロールバックし、再試行を促すメッセージを表示。インデックスファイルが破損した場合はバックアップ削除の案内を行います。
- ファイル I/O 例外（アクセス拒否、削除不能）はログ出力後、対象パスをエラーダイアログで提示し処理を中断します。
- 長時間処理中にウィンドウが閉じられた場合はワーカーの `requestInterruption()` を呼び、終了を待ってからスレッドを破棄します。

## 既存コード統合
- 既存ファイルを再利用: `src/file_manager/file_manager.py`, `file_search*.py`, `video_digest*.py`, `video_duplicates*.py`, `disk_*` 系ファイルは要件達成のための主要改修対象。
- 変更想定箇所:
  - `FileManagerWidget` の初期化ロジックでドライブ取得時間短縮と UI 応答性向上を確認。
  - 各ダイアログ呼び出し部で要件の受入基準（進捗表示、エラーメッセージ、操作ガード）を満たすための UI 改修。
  - QSettings キーの整理と defaults の明示化。
- 新規ファイルは不要と想定。追加が必要になった場合は `src/file_manager/` 配下にサブモジュールを作成し、命名規則（スネークケース）に合わせます。
- テストは既存の `tests/` 配下にシナリオテストを追加し、`pytest-qt` を用いてダイアログ挙動を検証します。
