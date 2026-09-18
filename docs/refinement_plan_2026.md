# 改善・洗練化方針書 2026

最終更新: 2026-06-02

## 0. 本書の目的

既存の `ui_modernization_plan.md`（外観刷新 Phase 1-5）と `file_manager_redesign_*`（機能・操作性再設計 Phase A-F）を補完し、次の三軸で改善方針を整理する。

1. **高速化**: 大量ファイル表示、動画メタデータ取得、ディスク分析、左ペインの応答性を改善する
2. **デザイン改善**: 既存の Fluent 化をさらに実用画面として磨き、密度・可読性・状態表現を揃える
3. **機能整理**: 重複・低価値・開発専用機能を段階的に統合または非表示化する

既存の redesign Phase A-C（同期、コピー/貼り付け、ショートカット、ステータスバー）は引き続き最優先。本書の P1 施策は並走可能だが、既存要件と衝突する削除は避け、テストで保護された段階移行を前提にする。

---

## 1. 現状評価と訂正

### 1.1 確認済みの実態

| 項目 | 実態 | 訂正ポイント |
| --- | --- | --- |
| `FileListView` の `setUniformRowHeights` | 未設定 | P1 の即効改善として妥当 |
| 動画メタデータ | `CustomFileSystemModel.metadata_cache` はメモリ内のみ | 永続キャッシュ追加は妥当。ただし既存のメモリキャッシュを生かして二層化する |
| `video_digest_burst_count` | 設定ダイアログに UI があり、`file_manager.py` / `video_digest_dialog.py` / テストで参照 | 「UIなし」は誤り。削除ではなく、まず初期値不一致と設定経路の整理を行う |
| `FolderSizeWorker` | 単一 `QThread` を再利用し、クリックしたフォルダのみ計算 | 「複数並走」は誤り。改善対象はキャンセル応答性、進捗、展開時/要求時のみ計算 |
| 外国語フィルタ | ツールバーに存在し、要件定義では維持 MUST | いきなり移管/削除は既存要件と衝突。設定でツールバー表示を制御しつつ検索条件にも再利用する |
| `TestRunnerDialog` | メニューに常時表示、`main.py` が常時 import | 開発専用化は妥当。完全削除より `--debug` / 環境変数時のみ表示が低リスク |
| VideoCluster | import 失敗時は大枠でガード済み。ただし `left_pane.py` の `TagFilterPanel` は別判定 | ガード強化と UX 非表示の一貫性が必要 |

### 1.2 既存計画との関係

- `ui_modernization_plan.md` Phase 1-5 は多くが完了済み。追加のデザイン改善は「新テーマを作る」より、実画面の密度・状態表示・メニュー/ダイアログの一貫性を詰める段階。
- `file_manager_redesign_implementation_plan.md` Phase A-C は MUST。大規模な新機能（タブ、コマンドパレット、ANN 検索）は Phase A-C の後に回す。
- 既存要件で維持対象になっている機能（外国語フィルタ等）は、削除ではなく配置・露出の改善に留める。

---

## 2. 高速化 改善案

### 2.1 P1: QTreeView 行高の統一

**対象**: `src/file_manager/views.py`

`FileListView.__init__` に以下を追加する。

```python
self.setUniformRowHeights(True)
```

本アプリは行ごとの高さが実質固定のためリスクは低い。サムネイルを行内表示する設計に変える場合だけ再検討する。

あわせて左ペイン `FolderTreeView` でもフォルダサイズバッジが行高を変えない前提なら `setUniformRowHeights(True)` を検討する。

### 2.2 P1: 動画メタデータ取得の重複抑制

**対象**: `src/file_manager/qt_models.py`, `src/file_manager/file_manager.py`

現状はメモリ内の `metadata_cache` と `metadata_loading` で最低限の重複は防いでいるが、ディレクトリ再訪問やアプリ再起動で再取得になる。

短期対応:

- `metadata_loading` に入れる前に `os.path.exists` と動画拡張子判定を済ませる
- 取得失敗も短時間キャッシュし、失敗ファイルへ連続リクエストしない
- `dataChanged` は 1 ファイルごとでなく、可能なら数十件単位でまとめる

### 2.3 P2: 動画メタデータ永続キャッシュ

**新規候補**: `src/file_manager/video_metadata_cache.py`

SQLite に以下を保存する。

| key | value |
| --- | --- |
| `path` | 正規化した絶対パス |
| `mtime_ns` | `os.stat().st_mtime_ns` |
| `size` | `os.stat().st_size` |
| `duration` / `width` / `height` / `fps` | 表示列用メタデータ |
| `updated_at` | キャッシュ掃除用 |

方針:

- 既存の `CustomFileSystemModel.metadata_cache` はホットキャッシュとして残す
- 永続キャッシュはワーカー投入前に確認する
- DB は `%APPDATA%\FileManager\metadata_cache.db` 相当のユーザー領域に置く
- 最大サイズまたは最終参照日時で古いレコードを掃除する

### 2.4 P2: ビューポート連動フェッチ

現状は表示列にアクセスされたタイミングでメタデータ取得が走る。大量ファイルではスクロールやソート時にリクエストが増えやすい。

改善案:

- `list_view.viewport().rect()` と `indexAt()` で見えている行範囲を取得する
- 表示範囲 + 先読み 30-50 行だけを優先投入する
- スクロール中は 100-200ms debounce し、停止後に投入する
- QThreadPool の同時実行数を動画メタデータ用に 1-2 本へ制限する

### 2.5 P2: ディスク分析のキャンセルと進捗

**対象**: `src/file_manager/disk_analyzer.py`, `src/file_manager/disk_analysis_dialog.py`

現状の `DiskAnalyzer` / `DiskAnalysisWorker` には明示的なキャンセルがない。大きなフォルダでは戻れない操作になりやすい。

改善案:

- `DiskAnalyzer.cancel()` と `_cancelled` を追加し、`os.walk`、`os.listdir`、サイズ計算ループで頻繁に確認する
- `current_path_updated = Signal(str)` を追加し、現在スキャン中のパスを表示する
- 進捗のための事前全件カウントは大規模フォルダで二重走査になるため、件数不明の indeterminate 表示を基本にし、処理済み件数を補助表示する
- 別フォルダで分析を開始したら前回 worker をキャンセルする

### 2.6 P2: 左ペイン FolderSize の応答性改善

**対象**: `src/file_manager/left_pane.py`

現状は単一 worker のため「並走数制限」は不要。改善すべき点は以下。

- 計算中に別フォルダを選んだ場合、古い計算を確実に止める
- `wait(400)` で止まらない場合に単にスキップするだけでなく、UI 上の `None` マークを解除する
- `os.scandir()` ベースに変えて `DirEntry.stat()` を活用し、`os.path.getsize()` の呼び出し回数を減らす
- 展開済み/クリック済みフォルダだけ計算し、ドライブ直下の大量フォルダを勝手に走査しない

### 2.7 P2: ソートとフィルタの負荷抑制

**対象**: `src/file_manager/qt_models.py`

- `lessThan()` はサイズ/日付で `fileInfo()` を毎回呼ぶため、大量ファイルのソートで重くなりやすい。列ごとの sort key キャッシュを検討する
- `set_filename_filter_text()` は入力ごとに即 invalidate している。検索欄側で 150ms 程度 debounce する
- 外国語判定は軽いが、検索と組み合わせる場合は先に文字列検索で落としてから判定する現状の順序を維持する

---

## 3. デザイン改善案

### 3.1 P1: 現テーマの実画面ポリッシュ

新しい大規模テーマを増やすより、現在の Fluent Light/Dark を実画面で整える。

- `nav_bar` の margins が計画値 `12,4,12,4` ではなく現状 `8,2,8,2`。他バーと揃える
- `drive_frame` は高さ 52px でやや厚い。ドライブ使用量バーを維持しつつ 40-44px 程度を検討する
- ツールバーの文字付き/アイコンのみ状態を設定で切替可能にし、デフォルトはアイコン + tooltip へ寄せる
- コンテキストメニューのショートカット表示を統一する

### 3.2 P1: 状態表現の統一

ファイル管理アプリでは「選択」「チェック」「切り取り中」「読み込み中」「無効」が混ざるため、色だけでなく形を揃える。

- 選択: アクセント背景 + 文字色維持
- チェック済み: チェックボックスで表現し、選択色とは混同させない
- 切り取り中: 半透明または薄い斜線/淡色表示
- 読み込み中: `Loading...` 文字ではなく薄いプレースホルダーまたはスピナー相当
- エラー: ステータスバー通知 + 該当列は `-` 表示

### 3.3 P2: ステータスバーの情報設計

redesign Phase C と合わせて実装する。

```text
[現在パス] | 選択 3 / 全 384 | 選択 142.5 MB | C: 空き 45 GB
```

- パスクリックでクリップボードコピー
- 選択なし時は「全 N 件 / 合計サイズ」を表示
- ディスク空き容量は 5 秒程度キャッシュする
- 一時通知（コピー完了、削除失敗など）は右側に短時間表示する

### 3.4 P2: ダイアログの標準レイアウト

既存ダイアログが増えているため、ヘッダー/本文/フッターの構成を揃える。

- フッターの主要ボタンは右端、キャンセルはその左
- 進捗があるダイアログは「停止」ボタンを必ず置く
- 結果一覧は検索/絞り込み欄を上部に置く
- 削除系操作は最終確認と対象件数を明示する

### 3.5 P3: インラインリネーム

`F2` がダイアログ方式のため、Explorer 互換のインライン編集に寄せる。

- 名前列のみ編集可
- 初期選択は拡張子前まで
- `Esc` でキャンセル、`Enter` で確定
- 既存の rename テストを維持し、ダイアログ方式はフォールバックとして残す

### 3.6 P3: コマンドパレット

Phase A-C 完了後の SHOULD。`Ctrl+K` / `Ctrl+Shift+P` で起動する。

実装方針:

- まず `QAction` 収集ではなく、明示的な `Command` データクラスで主要コマンドを登録する
- メニュー/ツールバー/ショートカットは同じ `Command` 定義から作る方向へ寄せる
- ファジー検索は初期版では `difflib` で十分。大規模化したら専用スコアリングへ移行

---

## 4. 機能整理 改善案

### 4.1 `SameFileSizeDialog` は即削除ではなく統合候補

同サイズのみの検出は偽陽性が多いが、重複検出の一次フィルタとしては有用。即削除ではなく、次の順で進める。

1. メニュー/ツールバー上の露出を「重複・類似検出」に統合する
2. 内部では `same_filesize.py` のロジックを「サイズ一致候補」タブまたは重複検出の前処理として再利用する
3. 統合後に単独ダイアログ参照と単独テストだけを削除する

### 4.2 重複・類似検出ダイアログの統合

**新規候補**: `src/file_manager/duplicate_detection_dialog.py`

タブ構成:

- `動画重複`: 既存 `VideoDuplicatesDialog`
- `ファイル名類似`: 既存 `FilenameSimilarityDialog`
- `サイズ一致候補`: 既存 `same_filesize.py` の結果を利用

既存ダイアログをいきなり壊さず、最初はラッパーダイアログから既存 UI を呼ぶ。テストが安定したら内部ウィジェット化する。

### 4.3 `video_digest_burst_count` は整理に変更

削除案は現状と合わない。設定 UI があり、テストでも引数として使われている。

改善案:

- 既定値が `video_digest_dialog.py` では 3、`file_manager.py` では 0 になっており不一致。まず 0 または 1 に統一する
- 「前後フレーム補完」などユーザーに意味が通るラベルへ変更する
- 高速化優先ならデフォルト 0、品質優先なら 1。大量動画では 0 を推奨する説明を tooltip に入れる
- どうしても削除する場合は、設定 UI、QSettings 読み書き、テスト、キャッシュキー `_b{burst_count}` を同時に移行する

### 4.4 `TestRunnerDialog` は開発専用化

完全削除より、まず本番 UI から隠す。

- `main.py` の常時 import をやめ、`--debug` または `FILE_MANAGER_DEV_TOOLS=1` のときだけ import する
- メニューの「テストを実行」は開発モード時のみ表示
- CI/開発者向けの導線は `python -m pytest` に一本化する

### 4.5 外国語フィルタは維持しつつ露出を調整

要件定義で MUST のため、削除や検索ダイアログへの完全移管は避ける。

改善案:

- ツールバー設定で表示/非表示を選べる現行構造を維持
- `FileSearchDialog` にも同じ判定を再利用した条件を追加する
- ラベルを「外国語名」から「日本語を含まない名前」など挙動が分かる名前へ変更する
- 判定ルールを tooltip に短く示す

### 4.6 VideoCluster は依存ガードと表示一貫性を優先

- `file_manager.py` の `VIDEO_CLUSTER_AVAILABLE` と `left_pane.py` の `_TAG_FILTER_AVAILABLE` を同じ判定基準に寄せる
- 依存がない場合はタグフィルタパネル、メニュー、ボタンを完全に非表示にする
- ANN（faiss-cpu / hnswlib）は依存追加が重いため P4。まずは DB インデックス、検索対象絞り込み、進捗/キャンセルを先に行う

---

## 5. 追加で実行したほうが良い改善

### 5.1 パフォーマンス計測を先に入れる

改善効果を測れるように、軽量な計測コマンドまたはテストを追加する。

- 1,000 / 10,000 件の一時フォルダで初回表示時間を計測
- メタデータ列あり/なしでスクロール時間を比較
- `setUniformRowHeights` 適用前後の差分を記録
- 結果は `docs/perf_notes.md` に残す

### 5.2 QSettings キーの棚卸し

動画設定、テーマ設定、列設定が増えているため、キー一覧と既定値をドキュメント化する。

- 既定値の不一致を防ぐ
- 設定破損時の fallback をテストしやすくする
- 将来の設定移行に備えて `settings_version` を持つ

### 5.3 QAction/Command 定義の一元化

メニュー、ツールバー、ショートカット、コマンドパレットで同じ操作が重複定義されている。

まずは `commands.py` に ID、表示名、tooltip、shortcut、handler 名、icon 名を定義し、段階的に参照元を寄せる。これによりショートカット表示、コマンドパレット、テストが簡単になる。

### 5.4 UI 自動チェックの追加

デザイン改善は見た目の回帰が起きやすい。

- `tests/test_ui_theme.py` に主要 QSS トークンの存在チェックを追加
- ボタン/メニューの `toolTip` と `accessibleName` の欠落チェック
- ライト/ダークの主要色コントラストテスト

---

## 6. 実装優先順位

| 優先度 | カテゴリ | 施策 | 工数 | 備考 |
| --- | --- | --- | --- | --- |
| P0 | 基盤 | redesign Phase A-C 継続 | 大 | MUST。同期、コピペ、ショートカット、ステータスバー |
| P1 | 高速化 | `FileListView.setUniformRowHeights(True)` | 小 | 即効。テスト影響小 |
| P1 | デザイン | nav/drive/toolbar の密度調整 | 小 | 既存 Fluent のポリッシュ |
| P1 | 機能整理 | `TestRunnerDialog` を開発モード限定表示 | 小 | 本番 UI を整理 |
| P1 | 設定整理 | `video_digest_burst_count` 既定値・ラベル統一 | 小 | 削除ではなく整合 |
| P2 | 高速化 | 動画メタデータ永続キャッシュ | 中 | SQLite 追加 |
| P2 | 高速化 | メタデータのビューポート連動フェッチ | 中 | debounce と同時実行制限 |
| P2 | 高速化 | DiskAnalyzer キャンセル/進捗改善 | 中 | 大容量フォルダ対策 |
| P2 | 機能整理 | 重複・類似検出の統合ダイアログ | 中 | 既存ロジック再利用 |
| P2 | デザイン | ステータスバー情報設計 | 中 | Phase C と合わせる |
| P3 | UX | インライン F2 リネーム | 中 | delegate/編集トリガー |
| P3 | UX | Command 定義一元化 + コマンドパレット | 中 | 先に commands.py |
| P3 | 機能整理 | 外国語フィルタを検索条件にも追加 | 中 | 維持しつつ露出改善 |
| P3 | 高速化 | FolderSize の `os.scandir()` 化 | 小-中 | 応答性改善 |
| P4 | 高速化 | VideoCluster ANN 対応 | 大 | 依存追加が重いので後回し |

---

## 7. 変更対象ファイル

### 小規模修正

```text
src/file_manager/views.py              # uniformRowHeights、ドラッグ Pixmap
src/file_manager/file_manager.py       # メタデータ投入制御、ツールバー/フィルタ/設定反映
src/file_manager/main.py               # 開発専用メニュー、Command 参照
src/file_manager/settings_dialog.py    # burst_count ラベル/既定値、ツールバー表示設定
src/file_manager/qt_models.py          # メタデータキャッシュ、フィルタ/ソート負荷抑制
src/file_manager/left_pane.py          # FolderSize キャンセル/応答性
src/file_manager/disk_analyzer.py      # キャンセル、現在パス通知
src/file_manager/disk_analysis_dialog.py # 停止ボタン、進捗表示
```

### 新規候補

```text
src/file_manager/video_metadata_cache.py       # 動画メタデータ永続キャッシュ
src/file_manager/duplicate_detection_dialog.py # 重複・類似検出の統合入口
src/file_manager/commands.py                   # 操作定義の一元化
src/file_manager/status_bar.py                 # Phase C のステータスバー
docs/perf_notes.md                             # 計測結果ログ
```

### 削除または非公開化候補

```text
src/file_manager/test_runner_dialog.py         # まず開発モード限定。安定後に削除判断
src/file_manager/same_filesize_dialog.py       # 統合後に単独 UI を削除判断
```

---

## 8. 検証方針

- ドキュメントのみ更新した場合はテスト不要
- コード変更時は最低限、関連テストを実行する
- UI 変更時は `QT_QPA_PLATFORM=offscreen` で既存 UI テストを通す
- 高速化変更は、体感ではなく簡易計測値を残す

推奨テスト:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_button_actions.py tests/test_ui_theme.py tests/test_video_digest.py -q
```

---

## 9. 参考

- `docs/ui_modernization_plan.md`
- `docs/file_manager_redesign_requirements.md`
- `docs/file_manager_redesign_implementation_plan.md`
- `src/file_manager/file_manager.py`
- `src/file_manager/qt_models.py`
- `src/file_manager/views.py`
- `src/file_manager/left_pane.py`
