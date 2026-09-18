# 実装タスク一覧

`docs/refinement_plan_2026.md` の方針に基づく実装チェックリスト。  
優先度: **P1** → **P2** → **P3** → **P4** の順に着手する。

---

## バグ修正（方針書外・完了済み）

- [x] **ツリー同期バグ**: `_sync_left_pane_to_path` が `select_drive` / `_trigger_tree_load_for_path` を呼ぶ前にフラグを立てないため別フォルダへ誤遷移する問題を修正  
  → `file_manager.py`: `_sync_left_pane_to_path` に `_syncing_left_pane = True` を先行設定、`_apply_tree_selection` を save/restore パターンへ変更、`_schedule_tree_sync` リトライにも保護追加
- [x] **クリック判定バグ**: チェックボックスのヒット領域が右方向に +4px 拡張されてアイコン領域（+24px）と重なり、アイコン付近のクリックがチェックボックス扱いになる問題を修正  
  → `views.py`: `adjusted(-4,-4,4,4)` → `adjusted(-2,-3,0,3)`

---

## 1. 高速化

### P1（即効・リスク低）

- [x] **[PERF-1]** `FileListView.__init__` に `self.setUniformRowHeights(True)` を追加  
  対象: `src/file_manager/views.py`  
  確認: 行高が実質固定であることを目視確認。サムネイル行内表示設計へ変える場合は再検討。

- [x] **[PERF-2]** 動画メタデータ取得の重複抑制  
  対象: `src/file_manager/qt_models.py`  
  - [x] `_VIDEO_EXTENSIONS` をモジュール定数化（呼び出しごとの set 生成を排除）
  - [x] 取得失敗ファイルを 60 秒キャッシュ（`metadata_failed: dict[str, float]`）して連続リクエストを防止
  - [x] `update_metadata` で `{"error": "..."}` dict を失敗として正しく判定（レビュー指摘修正済み）
  - [x] `get_video_metadata` の戻り値を `"Loading..."` → `None` に統一（表示列も整合）
  - [ ] `dataChanged` の emit を数十件単位でまとめる（バッチ化）※ P2 以降に先送り

### P2（中期）

- [x] **[PERF-3]** 動画メタデータ永続キャッシュ  
  対象: `src/file_manager/video_metadata_cache.py`（新規）, `src/file_manager/qt_models.py`  
  - [x] SQLite スキーマ（`path`, `mtime_ns`, `size`, `duration`, `width`, `height`, `fps`, `updated_at`）+ WAL モード
  - [x] 既存の `CustomFileSystemModel.metadata_cache` はメモリホットキャッシュとして維持
  - [x] `get_video_metadata` にて: メモリキャッシュ → 失敗キャッシュ → SQLite → worker 投入 の順で照合
  - [x] `update_metadata` 完了時に SQLite へ書き込み（`mtime_ns + size` をキー）
  - [x] DB パスを `%APPDATA%\FileManager\metadata_cache.db` に配置
  - [x] 起動時に 30 日以上古いエントリを `cleanup()` で削除

- [x] **[PERF-4]** ビューポート連動フェッチ（部分完了）  
  対象: `src/file_manager/file_manager.py`  
  - [x] 動画メタデータ用 QThreadPool の同時実行数を 2 本へ制限（`setMaxThreadCount(2)`）
  - [ ] `list_view.viewport().rect()` と `indexAt()` で表示行範囲を取得（P4 後半へ先送り）
  - [ ] 表示範囲 + 先読み 30〜50 行のみを優先投入（P4 後半へ先送り）
  - [ ] スクロール中は 100〜200ms debounce してから投入（P4 後半へ先送り）

- [x] **[PERF-5]** ディスク分析のキャンセルと進捗改善  
  対象: `src/file_manager/disk_analyzer.py`, `src/file_manager/disk_analysis_dialog.py`  
  - [x] `DiskAnalyzer.cancel()` と `_cancelled` フラグを追加（`os.walk` / `os.listdir` ループで確認）
  - [x] `current_path_updated = Signal(str)` を追加、スキャン中パスをダイアログに表示
  - [x] 進捗バーを `setRange(0,0)` の indeterminate 表示に変更
  - [x] 「停止」ボタンを追加（`_cancel_analysis`: cancel() のみ、`wait()` なし）
  - [x] 前回 worker をキャンセルしてから新 worker を開始
  - [x] `_on_worker_finished(worker)` に新旧 worker 識別ロジックを追加（レビュー指摘 C-1/C-2 修正済み）

- [x] **[PERF-6]** 左ペイン FolderSize の応答性改善（部分完了）  
  対象: `src/file_manager/left_pane.py`  
  - [x] `os.scandir()` + `DirEntry.stat()` を使ったスタックベース実装（`os.walk` + `os.path.getsize` を廃止）
  - [x] worker 終了時に `None` マーカーが残っていたら削除して再描画（キャンセル時も "···" が残らない）
  - [ ] 計算中に別フォルダを選んだ場合に古い計算を確実に停止（`start_for` の `wait(400)` 改善は後半へ）
  - [ ] 展開済み / クリック済みフォルダだけを計算（ドライブ直下の大量フォルダ対策は後半へ）

- [x] **[PERF-7]** ソートとフィルタの負荷抑制（部分完了）  
  対象: `src/file_manager/file_manager.py`  
  - [x] 検索ボックスの `textChanged` に 150ms debounce を追加（`QTimer.setSingleShot`）
  - [x] `filter_files` 内の冗長な `set_current_path` を除去（レビュー指摘修正済み）
  - [ ] `lessThan()` に列ごとの sort key キャッシュを検討（サイズ / 日付列）※ P2 後半へ先送り

---

## 2. デザイン改善

### P1（即効）

- [x] **[DESIGN-1]** 現テーマの実画面ポリッシュ（部分完了）  
  対象: `src/file_manager/file_manager.py`, `src/file_manager/left_pane.py`  
  - [x] `nav_bar` の margins を `12,4,12,4`・spacing 6 に更新
  - [x] `drive_frame` の高さを 44px・margins を `12,4,12,4` に縮小
  - [ ] ツールバーをアイコン + tooltip をデフォルトとし、文字付きは設定で切替可能に
  - [ ] コンテキストメニューの全アクションにショートカット表示を統一

- [x] **[DESIGN-2]** 状態表現の統一（部分完了）  
  対象: `src/file_manager/views.py`, `src/file_manager/qt_models.py`  
  - [x] 切り取り中アイテム: `painter.setOpacity(0.4)` による半透明描画（try/finally で restore 保証）
  - [x] 読み込み中: `"Loading..."` 文字を廃止、空欄表示に統一（メタデータ列）
  - [ ] 選択: アクセント背景 + 文字色維持（現状確認・調整）
  - [ ] エラー状態: ステータスバー通知 + 該当列は `-` 表示

### P2

- [x] **[DESIGN-3]** ステータスバーの情報設計（部分完了）  
  対象: `src/file_manager/main.py`, `src/file_manager/file_manager.py`  
  - [x] パスラベルをクリックでクリップボードコピー（`_ClickEventFilter` 経由、PySide6 互換）
  - [x] 選択件数・合計サイズを中央ラベルに表示（選択なし時は「全 N 件」）
  - [x] `FileManagerWidget.selection_changed` シグナルで接続（モデル入れ替えに強い設計）
  - [x] コピー完了は `statusBar().showMessage("パスをコピーしました", 2000)` で通知
  - [ ] ディスク空き容量の 5 秒キャッシュ（後半へ）
  - [ ] 選択合計サイズの右端表示（後半へ）

- [ ] **[DESIGN-4]** ダイアログの標準レイアウト  
  対象: 各 `*_dialog.py`  
  - [ ] フッターのボタン配置: 主要ボタンを右端、キャンセルはその左
  - [ ] 進捗があるダイアログには「停止」ボタンを配置
  - [ ] 結果一覧ダイアログの上部に検索/絞り込み欄を配置
  - [ ] 削除系操作に最終確認ダイアログ + 対象件数の明示

### P3

- [ ] **[DESIGN-5]** インライン F2 リネーム  
  対象: `src/file_manager/views.py`  
  - [ ] 名前列のみ編集可に設定
  - [ ] 初期選択を拡張子前まで（例: `file.txt` → `file` を選択）
  - [ ] `Esc` でキャンセル、`Enter` で確定
  - [ ] 既存の rename テスト（ダイアログ方式）を維持しつつ delegate で実装

- [ ] **[DESIGN-6]** コマンドパレット（Phase A–C 完了後の SHOULD）  
  対象: `src/file_manager/command_palette.py`（新規）  
  - [ ] `Ctrl+K` / `Ctrl+Shift+P` で起動するフローティングダイアログ
  - [ ] 明示的な `Command` データクラスで主要コマンドを登録
  - [ ] difflib ベースのファジー検索（初期版）
  - [ ] メニュー / ツールバー / ショートカットを同じ `Command` 定義から生成する方向へ

---

## 3. 機能整理

### P2

- [ ] **[FEAT-1]** `SameFileSizeDialog` を重複検出に統合  
  対象: `src/file_manager/same_filesize.py`, `src/file_manager/same_filesize_dialog.py`  
  - [ ] メニュー / ツールバーの露出を「重複・類似検出」にまとめる
  - [ ] `same_filesize.py` のロジックを「サイズ一致候補」として重複検出の前処理に再利用
  - [ ] 統合後に単独ダイアログ参照と単独テストのみを削除

- [ ] **[FEAT-2]** 重複・類似検出ダイアログの統合  
  対象: `src/file_manager/duplicate_detection_dialog.py`（新規）  
  - [ ] タブ構成: [動画重複] / [ファイル名類似] / [サイズ一致候補]
  - [ ] 既存ダイアログを最初はラッパーから呼び出す（既存テストを壊さない）
  - [ ] テストが安定したら内部ウィジェット化

- [x] **[FEAT-3]** `video_digest_burst_count` の整理  
  対象: `src/file_manager/video_digest_dialog.py`, `src/file_manager/settings_dialog.py`  
  - [x] 既定値の不一致（dialog 側 = 3、file_manager 側 = 0）を 0 に統一
  - [x] 設定 UI のラベルを「前後フレーム補完（バースト）:」に変更
  - [x] 選択肢 0 を「なし（高速・推奨）」に変更し tooltip で大量動画時の推奨を説明

- [x] **[FEAT-4]** `TestRunnerDialog` を開発専用化  
  対象: `src/file_manager/main.py`  
  - [x] `_DEV_MODE` フラグ（`FILE_MANAGER_DEV_TOOLS=1` 環境変数 or `--dev` 引数）でのみ import
  - [x] メニューの「テストを実行」を `_DEV_MODE` 時のみ表示
  - [x] `--debug` → `--dev` へ変更（pytest --debug フラグとの衝突を回避、レビュー指摘修正済み）

- [ ] **[FEAT-5]** 外国語フィルタの露出調整  
  対象: `src/file_manager/file_manager.py`  
  - [ ] ツールバー設定で表示 / 非表示を選べる現行構造を維持
  - [ ] `FileSearchDialog` の条件にも同じ判定を再利用した選択肢を追加
  - [ ] ラベルを「外国語名」→「日本語を含まない名前」など挙動が伝わる名前に変更
  - [ ] 判定ルールを tooltip に短く記載

### P3

- [x] **[FEAT-6]** VideoCluster 依存ガードの一貫性  
  対象: `src/file_manager/left_pane.py`  
  - [x] `left_pane.py` の `_TAG_FILTER_AVAILABLE` 判定に `video_cluster_db` のインポートを追加し、`file_manager.py` の `VIDEO_CLUSTER_AVAILABLE` と同じ基準に揃えた
  - [x] いずれかの依存が欠けていればタグフィルタパネルも非表示になる

### P4

- [ ] **[FEAT-7]** VideoCluster の ANN 対応（依存追加が重いため後回し）  
  対象: `src/file_manager/video_cluster_db.py`, `src/file_manager/video_cluster_engine.py`  
  - [ ] DB インデックス追加・検索対象の絞り込みを先行実施
  - [ ] その後 faiss-cpu / hnswlib の導入を検討

---

## 4. 追加改善

- [ ] **[QA-1]** パフォーマンス計測の仕組み整備  
  対象: `docs/perf_notes.md`（新規）  
  - [ ] 1,000 / 10,000 件の一時フォルダで初回表示時間を計測
  - [ ] メタデータ列あり / なしでスクロール時間を比較
  - [ ] `setUniformRowHeights` 適用前後の差分を記録

- [ ] **[QA-2]** QSettings キーの棚卸し  
  対象: `docs/settings_keys.md`（新規） または `src/file_manager/constants.py`  
  - [ ] 全設定キーと既定値を一覧化（動画設定 / テーマ設定 / 列設定）
  - [ ] 既定値の不一致を修正
  - [ ] 設定破損時の fallback をテストしやすくする

---

## 優先順位サマリー

| 優先度 | タスク ID | 一言説明 | 工数 |
|--------|-----------|---------|------|
| P1 | PERF-1 | `setUniformRowHeights` 追加 | 小 |
| P1 | PERF-2 | メタデータ重複取得の抑制 | 小〜中 |
| P1 | DESIGN-1 | navBar / driveBar の余白・高さ修正 | 小 |
| P1 | DESIGN-2 | 切り取り中アイテムの半透明表示等 | 小〜中 |
| P2 | PERF-7 | 検索 debounce 150ms | 小 |
| P2 | FEAT-3 | burst_count 初期値統一・ラベル改善 | 小 |
| P2 | FEAT-4 | TestRunnerDialog を開発専用化 | 小 |
| P2 | PERF-3 | メタデータ永続キャッシュ (SQLite) | 中 |
| P2 | PERF-4 | ビューポート連動フェッチ | 中 |
| P2 | PERF-5 | ディスク分析キャンセル / 進捗 | 中 |
| P2 | PERF-6 | FolderSize 応答性改善 | 中 |
| P2 | DESIGN-3 | ステータスバー拡張 | 中 |
| P2 | DESIGN-4 | ダイアログ標準レイアウト | 中 |
| P2 | FEAT-1 | SameFileSize 統合 | 中 |
| P2 | FEAT-2 | 重複検出ダイアログ統合 | 中 |
| P2 | FEAT-5 | 外国語フィルタ露出調整 | 小 |
| P3 | DESIGN-5 | インライン F2 リネーム | 中 |
| P3 | FEAT-6 | VideoCluster ガード統一 | 小 |
| P3 | DESIGN-6 | コマンドパレット | 中 |
| P3 | QA-1 | パフォーマンス計測 | 小 |
| P3 | QA-2 | QSettings 棚卸し | 小 |
| P4 | FEAT-7 | VideoCluster ANN 対応 | 大 |
