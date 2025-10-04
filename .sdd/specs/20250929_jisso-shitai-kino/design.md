# 設計

## 1. アーキテクチャ統合方法
- 既存の MainWindow は中央に FileManagerWidget を配置する構成を維持し、FileManagerWidget 内部でドライブショートカットバー・フォルダツリー・詳細リスト・補助パネルを束ねる。
- Qt の signal/slot を用いて UI ➜ ワーカー処理 ➜ UI 更新の非同期パイプラインを統一し、長時間処理（検索・解析・ダイジェスト生成）はすべて QThread 派生ワーカーへ委譲する。
- スタンドアローン配布とマルチ OS 対応を前提に、ファイルパス操作・ゴミ箱操作・OpenCV 等のオプション依存を抽象化クラスで包み、導入有無に応じて機能トグルを行う。
- 共通設定は QSettings と .env を併用し、UI からの変更は即時反映＋永続化、バックエンド設定値はサービス層（検索・ダイジェスト等）へ DI する。

## 2. 主要コンポーネント（責務・I/O・依存）
### FileManagerWidget（中核 UI）
- 責務: レイアウト管理、アクションルーティング、設定の適用。
- I/O: 入力=ユーザー操作（選択・ボタン・検索条件）、出力=シグナル（パス選択、処理依頼、状態更新）。
- 依存: CustomFileSystemModel、FileSortFilterProxyModel、各ダイアログクラス、AppPreferences。

### DriveShortcutBar（新規）
- 責務: 接続ドライブの列挙とショートカットボタン提供、外部ストレージのホットリロード。
- I/O: 入力=OS デバイス列挙、出力= driveSelected(str path) シグナル。
- 依存: pathlib, psutil（存在確認）, FileManagerWidget へ接続。

### FolderTreePanel（QTreeView + CustomFileSystemModel）
- 責務: パスナビゲーション、複数選択・チェック状態の管理。
- I/O: 入力=ルートパス・フィルタ、出力=選択シグナル・チェック済みパス集合。
- 依存: CustomFileSystemModel、QSettings（最終開閉状態）。

### FileListPanel（QListView + FileSortFilterProxyModel）
- 責務: フォルダ内ファイル一覧・ソート・フィルタ。
- I/O: 入力=現在パス、出力=選択ファイル、コンテキストアクション要求。
- 依存: FileActionDispatcher（新規サービス）。

### FileSearchDialog / FileSearchService
- 責務: インデックス作成・検索、範囲切替、結果リスト表示。
- I/O: 入力=検索キーワード・スコープ・インデックスパス、出力=検索結果リスト、ステータスコールバック。
- 依存: sqlite3, pathlib, SearchWorker（QThread）、FileSearchResultModel。

### DiskAnalysisDialog / DiskAnalysisWorker
- 責務: ディスク使用量集計・円グラフ描画・ドリルダウン。
- I/O: 入力=計測ルートパス、出力= DiskUsageNode ツリー・進捗シグナル。
- 依存: pathlib, humanfriendly, matplotlib (QtAgg), QThread。

### VideoDuplicatesDialog / DuplicateVideoWorker
- 責務: 指定フォルダ内の動画重複検出、類似グループ表示、削除操作。
- I/O: 入力=対象フォルダ・判定モード、出力= DuplicateGroup リスト・進捗・ログ。
- 依存: OpenCV + NumPy（利用可否で切替）、hashlib、send2trash。

### VideoDigestDialog / VideoDigestGenerator
- 責務: ダイジェスト生成パラメータ入力、サムネイルプレビュー、生成処理起動。
- I/O: 入力=対象動画パス・サムネイル数・尺、出力=生成済みダイジェストファイル・プレビュー信号。
- 依存: OpenCV、	empfile、QThread。

### AppPreferences（新規ユーティリティ）
- 責務: UI 設定値の一元管理（フォント・色・アイコンサイズ・起動動作・インデックスパス等）。
- I/O: load(), pply(widget), update(key, value)。
- 依存: QSettings, .env 読み込みモジュール。

### FileActionDispatcher（新規サービス）
- 責務: ファイル操作（開く、パスコピー、ゴミ箱移動）、OS 依存差異の吸収。
- I/O: メソッド呼び出しで結果 bool/例外、シグナルでエラー通知。
- 依存: subprocess, send2trash, OS 判定。

## 3. データモデル
- ile_index テーブル（SQLite）: id, path, 
ame, size, modified_at, extension, hash_optional. パスはユニーク、親フォルダ検索用に正規化列 directory を保持。
- SearchQuery（dataclass）: keywords: list[str], scope: Literal['current','all'], case_sensitive: bool, limit: int。
- SearchResultItem（dataclass）: path, 
ame, matched_field, score。
- DuplicateGroup（dataclass）: group_id, iles: list[DuplicateEntry], 
eason: Literal['hash','name','duration']。
- DiskUsageNode（dataclass）: path, display_name, size_bytes, children: list[DiskUsageNode]。
- DigestRequest（dataclass）: source_path, 	humbnail_count, clip_length, output_dir。
- AppPreference（dataclass）: ont_family, ont_size, icon_size, list_palette, startup_mode, startup_folder, index_db_path。

## 4. 処理フロー
### 4.1 ドライブショートカット
1. アプリ起動時に DriveShortcutBar がドライブ一覧を列挙しボタン生成。
2. ボタンクリック ➜ driveSelected シグナル ➜ FileManagerWidget がツリー/リストのルートを更新。
3. デバイス監視タイマーが差分を検知するとバーを再構築。

### 4.2 ファイル検索
1. FileManagerWidget から検索ボタン押下で FileSearchDialog を起動。
2. 検索実行で SearchWorker を QThread へ割当し、SearchQuery と現在スコープを渡す。
3. ワーカーは ile_index を更新（フル/差分）後に SQL で検索、結果をシグナル送信。
4. ダイアログが結果を表示し、ダブルクリックで FileManagerWidget.open_path() を呼び出す。

### 4.3 重複動画検出
1. 対象フォルダ選択後、VideoDuplicatesDialog を開き判定条件を入力。
2. DuplicateVideoWorker が QThread 上でファイル走査 → 特徴量抽出 → グルーピング。
3. 結果が UI に渡り、ユーザーは残す/削除を選択。
4. 削除要求は FileActionDispatcher.move_to_trash() で処理し、結果をトースト通知。

### 4.4 ディスク使用量グラフ
1. DiskAnalysisDialog でルートを選択し解析開始。
2. DiskAnalysisWorker が DFS でサイズ集計し、逐次 DiskUsageNode を送信。
3. ダイアログは受信データで円グラフを再描画、セグメントクリックで子ノードをリクエスト。

### 4.5 設定保存と適用
1. 設定ダイアログで外観・挙動を変更すると AppPreferences.update() を呼ぶ。
2. AppPreferences が QSettings と .env（必要な場合のみ）へ保存し、preferencesChanged シグナルを発火。
3. FileManagerWidget が受信し、フォント・配色・起動モード反映、インデックスパス変更時は検索サービスへ再注入。

### 4.6 動画ダイジェスト生成
1. ファイル一覧で動画選択後、「ダイジェスト」ボタンが VideoDigestDialog を表示。
2. ユーザー設定を DigestRequest にまとめ、VideoDigestGenerator ワーカーを起動。
3. 生成完了でプレビューを描画し、保存先パスを返却。失敗時は例外内容をダイアログに表示。

## 5. エラーハンドリング
- ワーカー例外は errorOccurred(str message, Optional[path]) シグナルでメインスレッドへ伝播し、モーダルダイアログ + ログファイルに記録。
- OpenCV 未導入や GPU 非対応時は対象機能の UI を自動的に無効化し、ダイアログ冒頭で導入手順リンクを表示。
- ファイル操作失敗時（権限・ロック）はリトライ可否を問い合わせ、send2trash 失敗時はフォールバックで直接削除するか再試行を選択できるようにする。
- SQLite インデックス更新失敗時は整合性チェック → 再生成を提案し、再生成中は検索操作をブロック。
- .env 読み書き時のパーミッションエラーは警告ログを残し、UI 上では「環境変数の更新に失敗しました」と通知。

## 6. 既存コード統合（変更/新規ファイル）
- 変更予定
  - src/file_manager/main.py: ドライブバーや設定ダイアログ起動アクションの追加、ステータスバー更新ロジック強化。
  - src/file_manager/file_manager.py: レイアウト再編成、DriveShortcutBar 追加、各機能ダイアログ起動とシグナル配線、設定適用処理の集約。
  - 既存ダイアログ/ワーカー（ile_search*.py, disk_*, ideo_*）: 要件に沿った I/O 拡張とエラーハンドリング統一。
- 新規追加
  - src/file_manager/drive_shortcut_bar.py: ドライブ列挙とシグナル通知を行うウィジェット。
  - src/file_manager/app_preferences.py: QSettings/BOM-less .env ラッパー。
  - src/file_manager/file_action_dispatcher.py: ファイル操作ユーティリティ。
  - src/file_manager/search_worker.py, duplicate_video_worker.py, disk_usage_worker.py, ideo_digest_worker.py: QThread ベースのバックグラウンド処理クラス。
  - src/file_manager/settings_dialog.py: 外観/挙動設定 UI。
  - 	ests/ 配下に各機能のユニット/GUI テスト (	est_file_search.py, 	est_disk_analysis.py, 	est_preferences.py など)。

