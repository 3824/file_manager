# ファイラー再設計 実装計画書

最終更新: 2026-05-08

`file_manager_redesign_requirements.md` の要件と `file_manager_redesign_spec.md` の仕様を、現実的な PR 単位に分割して進めるための計画書。

---

## 0. 進め方の前提

- **MUST → SHOULD → MAY** の順に着手する。MUST が未完のまま MAY に手を出さない。
- 各 Phase は**独立した PR** として出せる粒度。フィーチャーフラグは原則使わず、**完成したものから順次マージ**する。
- 大きすぎる Phase は内部で「ステップ」に分け、コミット単位で安全に積む。
- すべてのステップで `python -m pytest` を緑のまま維持する（CLAUDE.md 準拠）。
- 既存独自機能（動画ダイジェスト・重複動画・ディスク分析・翻訳）に手を入れない。

---

## 1. Phase 全体像

| Phase | テーマ | 主な要件 | 想定 PR 数 | 優先度 |
| --- | --- | --- | --- | --- |
| **A** | **同期と履歴の堅牢化（基盤）** | FY-1, FY-2, FY-3, FY-4, FN-7 | 2〜3 | MUST |
| **B** | **操作性の底上げ（キーボード・ショートカット）** | FN-2〜FN-5, FO-1〜FO-5, FI-1〜FI-2 | 4〜5 | MUST |
| **C** | **視認性の引き上げ（密度・ステータスバー・行高）** | FD-6, FD-8, NV-1〜NV-7, NO-3, NO-4 | 3〜4 | MUST |
| **D** | **必須機能の補完（パンくず・プレビュー拡張）** | FN-1, FP-2〜FP-4, FC-2〜FC-4 | 4〜5 | SHOULD |
| **E** | **拡張機能（タブ・ピン留め）** | FT-1〜FT-3 | 3〜4 | SHOULD |
| **F** | **品質と堅牢性** | NP-1〜NP-3, NA-1〜NA-3, NR-1〜NR-3 | 2〜3 | SHOULD |

各 Phase は前 Phase に依存することがあるが、おおよそ **A → B → C → D → E → F** の順を守る。

---

## 2. Phase A: 同期と履歴の堅牢化

### 2.1 目標

- ファイル操作・ナビゲーション・更新のいずれの後でも、左ペインのツリー選択がリスト位置と一致する。
- 履歴・同期ロジックをテスト容易な単位に分割し、回帰防止テストを敷く。
- 設定保存（列幅・スプリッタ・最終パス）の整合を担保する。

### 2.2 ステップ

#### A-1. 履歴管理を切り出す

**変更ファイル**

- 新規: `src/file_manager/navigation/__init__.py`
- 新規: `src/file_manager/navigation/history.py`
- 修正: `src/file_manager/file_manager.py`（`_nav_history`/`_nav_forward_stack`/`_nav_jumping` を `NavigationHistory` 利用に置換）

**新規テスト**

- `tests/test_navigation_history.py`: push/back/forward/clear、`_nav_jumping` 相当のフラグ、最大件数（オプション）

#### A-2. 同期ロジックを切り出す

**変更ファイル**

- 新規: `src/file_manager/navigation/sync.py`（`TreeSyncController`）
- 修正: `file_manager.py` の `_sync_left_pane_to_path` / `_trigger_tree_load_for_path` / `_apply_tree_selection` / `_schedule_tree_sync` を `TreeSyncController` 経由に。

**新規テスト**

- `tests/test_tree_sync.py`:
  - `folder_model.index(path)` が valid のときは即同期
  - invalid のときは `_schedule_tree_sync` が走る
  - `current_path` が変わっていたらリトライキャンセル

#### A-3. ファイル操作後の同期回帰テスト

**新規テスト**

- `tests/test_sync_after_operation.py`:
  - `refresh()` 後にツリー選択がリストと一致
  - `delete_selected_files()` 後の同期
  - `move_selected_files_to_trash()` 後の同期
  - `_apply_translation_renames()` 後の同期
  - `create_new_folder()` 後の同期

各テストは一時フォルダで小さいツリーを作って検証する。

#### A-4. 設定保存の整合

**変更ファイル**

- `file_manager.py`:
  - スプリッタ位置を `view/splitter_state` で保存／復元
  - QSettings.sync() 呼び出しを `closeEvent` の最後 1 回にまとめる
  - 列幅変更時の保存を debounce（200ms）

**新規テスト**

- `tests/test_persistence.py`:
  - 列幅変更 → 終了 → 再起動で復元
  - スプリッタ位置の保存・復元

### 2.3 完了条件

- 既存テストすべて緑
- 新規 4 ファイルのテスト追加・緑
- ファイル操作 6 種（削除・移動・リネーム・翻訳・新規・コピー）後にツリーがリストと一致する手動確認

---

## 3. Phase B: 操作性の底上げ

### 3.1 目標

- 標準ショートカットを揃え、キーボードのみで主要操作を完結できる
- コピー／切り取り／貼り付けが OS 互換で動作する
- ファイルプロパティダイアログを追加する

### 3.2 ステップ

#### B-1. ショートカット整備（軽量版）

**変更ファイル**

- `file_manager.py`: `_setup_shortcuts()` を新設し、`QShortcut`／`QAction` でキー割当を定義

| キー | アクション |
| --- | --- |
| `F2` | リネーム |
| `Delete` | 削除（既存挙動） |
| `Shift+Delete` | ゴミ箱送り |
| `Ctrl+A` | 全選択 |
| `Ctrl+I` | 選択反転（新規） |
| `Ctrl+Shift+N` | 新規フォルダ |
| `Ctrl+L` | アドレスバー編集（B-3 で実装、まずダミー） |
| `Backspace` | 親フォルダ（リスト/ツリーフォーカス時のみ） |
| `Alt+Enter` | プロパティ（B-4 で実装、まずダミー） |
| `Ctrl+H` | 隠しファイル切替 |
| `F5` | 表示更新 |

**新規テスト**

- `tests/test_keyboard_shortcuts.py`: 各ショートカットがハンドラを呼ぶ

#### B-2. クリップボード（コピー／切り取り／貼り付け）

**変更ファイル**

- 新規: `src/file_manager/operations/__init__.py`
- 新規: `src/file_manager/operations/clipboard.py`（`ClipboardController`）
- 新規: `src/file_manager/operations/transfer.py`（`TransferWorker` ＋既存 `_transfer_paths_to_directory` 移植）
- 修正: `file_manager.py` の `copy_selected_files`／`cut_selected_files`／`paste_files` を実装に差し替え

**実装ポイント**

```python
# 簡略
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
if sys.platform == "win32":
    drop_effect = b"\x01\x00\x00\x00" if op is Operation.COPY else b"\x02\x00\x00\x00"
    mime.setData(
        "application/x-qt-windows-mime;value=Preferred DropEffect",
        QByteArray(drop_effect),
    )
QApplication.clipboard().setMimeData(mime)
```

切り取り中アイテムは `FileItemDelegate` 側で `option.state |= QStyle.State_Selected` ではなく独自フラグを参照して半透明描画する。

**新規テスト**

- `tests/test_clipboard.py`:
  - コピー → 別フォルダで貼り付けてファイルが増える
  - 切り取り → 貼り付けで元が消える
  - QMimeData の `urls` と Preferred DropEffect の確認

#### B-3. アドレスバー編集モード

`Ctrl+L` で `address_bar.setFocus()` ＋ `selectAll()`。Phase D（パンくず）でリッチ化するまでは既存の `QLineEdit` を流用する。

**変更ファイル**

- `file_manager.py`: `focus_address_bar()` メソッド追加

**新規テスト**

- `tests/test_keyboard_shortcuts.py` に `test_ctrl_l_focuses_address` を追加

#### B-4. ファイルプロパティダイアログ

**変更ファイル**

- 新規: `src/file_manager/operations/properties_dialog.py`
- 修正: `file_manager.py`: `show_properties_dialog()` を追加し `Alt+Enter` から呼ぶ

**ダイアログ内容**

| 種別 | 内容 |
| --- | --- |
| 単一ファイル | 名前 / パス / 種類 / サイズ / 作成日 / 更新日 / アクセス日 / 属性 / 拡張子 / 動画系メタ |
| 複数選択 | 件数 / 合計サイズ / 種別内訳 |
| 単一フォルダ | 名前 / パス / 含有ファイル数 / 含有フォルダ数 / 合計サイズ（バックグラウンド集計、進捗バー付） |

**新規テスト**

- `tests/test_properties_dialog.py`: 単一・複数・フォルダの各ケース

#### B-5. リスト操作の補強

- `Ctrl+A` で全選択
- `Ctrl+I` で選択反転（既選択を反転する `selection_model().select(...)` を組む）
- `Backspace` で親フォルダ移動（フォーカスが list/tree のときのみ）

### 3.3 完了条件

- §3.2 のすべてのショートカットが動作
- コピー → Explorer 側で貼り付け、Explorer でコピー → 本アプリで貼り付けが両方動く
- プロパティダイアログがすべての選択ケースで表示される
- 既存テスト＋新規 4 ファイルのテストが緑

---

## 4. Phase C: 視認性の引き上げ

### 4.1 目標

- ステータスバーで「選択件数 / 合計サイズ / 現在パス / 空き容量」が常時見える
- 行高プリセット（コンパクト／ノーマル／ゆとり）切替
- WCAG コントラスト比の自動テスト追加
- フォーカスリングをすべての操作対象に統一

### 4.2 ステップ

#### C-1. ステータスバー強化

**変更ファイル**

- 新規: `src/file_manager/status_bar.py`（`StatusBar(QStatusBar)` 派生）
- 修正: `main.py` の `MainWindow` 設定で新 StatusBar を装着

**機能**

- 左: 現在パス（既存ラベル流用）
- 中央: `選択 N / 全 M 件`、`合計 X.X MB`
- 右: 空き容量 `X / Y GB`（5 秒キャッシュ）
- `show_message(text, level="info", timeout=3000)` で一時通知

**新規テスト**

- `tests/test_status_bar.py`: 件数集計、合計サイズ集計、トースト表示・消滅

#### C-2. 行高プリセット

**変更ファイル**

- `ui_theme.py`: トークン上書きヘルパー追加
- `file_manager.py`: 設定ダイアログに「行の高さ」ラジオを追加し、変更時に `apply_theme()` で QSS 再生成
- `QSettings` キー `view/row_height_preset` を追加

**新規テスト**

- `tests/test_row_height_preset.py`: プリセット選択時に QSS の `size.row.h` が更新される

#### C-3. フォーカスリング統一

`QSS` で `:focus` を網羅的にカバーする。具体的には:
- `QPushButton:focus`（既存）
- `QToolButton:focus`
- `QLineEdit:focus`、`QComboBox:focus`、`QSpinBox:focus`、`QFontComboBox:focus`（一部既存）
- `QTreeView:focus`、`QListView:focus`（`outline: none` の代わりに `::item:selected:focus` で枠線）

**新規テスト**

- なし（QSS 構文のみ）。手動チェック。

#### C-4. WCAG コントラストの自動検証

**変更ファイル**

- 修正: `tests/test_ui_theme.py` または新規 `tests/test_contrast_ratio.py`

**実装**

```python
def _contrast_ratio(fg_hex, bg_hex):
    # WCAG 2.1 の相対輝度計算
    ...

def test_text_contrast_aa():
    for tokens in (TOKENS_LIGHT, TOKENS_DARK):
        assert _contrast_ratio(tokens["text.primary"], tokens["bg.window"]) >= 4.5
        assert _contrast_ratio(tokens["text.secondary"], tokens["bg.window"]) >= 4.5
```

#### C-5. フォルダのサイズ列改善

**変更ファイル**

- `models.py` または `file_manager.py` 内の `FileSystemModel.data()`: フォルダの `size` 列を `--` または「N 項目」と表示

**新規テスト**

- `tests/test_models_dataclasses.py` に追加

### 4.3 完了条件

- ステータスバーがすべての画面で動く
- 行高プリセットが切替・永続化できる
- WCAG コントラスト自動テストが緑

---

## 5. Phase D: 必須機能の補完

### 5.1 目標

- パンくずアドレスバーへの置換
- 画像／テキストプレビュー
- プレビューペインのトグル

### 5.2 ステップ

#### D-1. パンくずアドレスバー（基盤）

**変更ファイル**

- 新規: `src/file_manager/navigation/breadcrumb_bar.py`
- 修正: `file_manager.py`: `address_bar` を `BreadcrumbBar` で置き換え（`navigate_to_address` を `path_requested` シグナルにフック）

**実装ポイント**

- `BreadcrumbBar` は `QWidget` 派生、内部に `QStackedLayout` で `Crumb` と `Edit` を切替
- `Crumb` は `QHBoxLayout` に `QToolButton`（セグメント） + `QToolButton`（"›"）を交互に詰める
- 利用可能幅を `resizeEvent` で監視し、収まらない先頭セグメントを `…` ボタンに集約

**新規テスト**

- `tests/test_breadcrumb_bar.py`: パス → セグメント分解、Edit/Crumb 切替、無効パス拒絶

#### D-2. プレビューペイン拡張

**変更ファイル**

- 新規: `src/file_manager/preview/__init__.py`
- 新規: `src/file_manager/preview/image_preview.py`（`QPixmap` で `QLabel` に表示、ファイルサイズ大は遅延読み込み）
- 新規: `src/file_manager/preview/text_preview.py`（先頭 256 KB を `QPlainTextEdit` 読込専用で表示）
- 修正: `video_thumbnail_preview.py` の親に `QStackedWidget` を入れて切替

**新規テスト**

- `tests/test_image_preview.py`: 画像読み込み、リサイズ
- `tests/test_text_preview.py`: テキスト表示、サイズ上限

#### D-3. プレビューペイントグル

**変更ファイル**

- `file_manager.py`: `Ctrl+P` で `PreviewPane.setVisible(...)` 切替、`view/preview_visible` 永続化

#### D-4. 設定オプション拡充

「外観」または「動作」タブに以下を追加:
- 行の高さ
- アドレスバー表示形態
- ダブルクリック挙動

### 5.3 完了条件

- パンくずがクリック・編集の両方で動く
- 画像・テキスト・動画のプレビューが選択ファイル種別で自動切替
- `Ctrl+P` でトグル＆設定保存

---

## 6. Phase E: 拡張機能（タブ・ピン留め）

### 6.1 目標

- タブで複数フォルダを切替できる
- 左ペインに「ピン留めフォルダ」セクションを追加

### 6.2 ステップ

#### E-1. タブバー基盤

**変更ファイル**

- 新規: `src/file_manager/navigation/tabs.py`（`TabState` データクラス、`TabController`）
- 修正: `file_manager.py`: ToolBar 下に `QTabBar` を装着し、タブ切替で `TabState` を載せ替える

**新規テスト**

- `tests/test_tabs.py`: タブ追加・削除・切替・永続化

#### E-2. ショートカット

`Ctrl+T` / `Ctrl+W` / `Ctrl+Tab` / `Ctrl+Shift+Tab` / `Alt+1〜9` を組み込む。表示モードの `Ctrl+1〜3` と衝突しないよう、タブ直接切替は `Alt+1〜9` に統一する。

#### E-3. ピン留めセクション

**変更ファイル**

- 修正: `LeftPaneWidget` に `PinnedFolderSection` を追加（QTreeView 上部に小さい QListView）
- 永続化キー: `pinned/folders`（list[str]）

**新規テスト**

- `tests/test_pinned_folders.py`: 追加・削除・並べ替え

### 6.3 完了条件

- タブ追加 / 切替 / 閉じる / 永続化が動作
- ピン留め追加・移動・削除が動作

---

## 7. Phase F: 品質と堅牢性

### 7.1 目標

- 大量ファイル時のパフォーマンス（10,000 件）
- アクセシビリティ（accessibleName、Reduce motion、フォントスケール）
- エラー復帰（無効パス / フォルダ消失 / 設定破損）

### 7.2 ステップ

#### F-1. accessibleName 設定

**変更ファイル**

- `file_manager.py`: 全ボタン・入力に `accessibleName`, `toolTip` を漏れなく付与

#### F-2. Reduce motion 対応

**変更ファイル**

- `ui_theme.py` または専用モジュール: Windows レジストリ `HKCU\Control Panel\Desktop\UserPreferencesMask` を読み、`QPropertyAnimation.setDuration(0)` を適用

#### F-3. パフォーマンス計測と改善

- 10,000 件の一時フォルダを `tests/perf/` 下で生成
- 起動・切替・スクロール時間を計測
- 必要なら `metadata_fetch_requested` シグナルの間引き／キャッシュ

#### F-4. エラー復帰

- 無効パス入力 → 直前の有効値に戻し、ステータスバートースト
- フォルダ消失 → 親フォルダへフォールバック（`os.path.exists()` 監視）
- 設定読み込み時の例外 → デフォルトに戻して起動継続（既存ロジック強化）

**新規テスト**

- `tests/test_error_recovery.py`: 無効パス、フォルダ消失、設定破損のシナリオ

### 7.3 完了条件

- パフォーマンス指標（仕様書 §9）を満たす
- すべての主要 UI 要素に accessibleName
- エラー復帰テストが緑

---

## 8. テスト戦略

### 8.1 通常のテストルーチン（CLAUDE.md 準拠）

各 Phase の各 PR で以下を実行する。

```bash
# 単体テスト（高速・非UI）
python -m pytest tests/test_simple.py tests/test_models_dataclasses.py \
                 tests/test_filename_similarity.py tests/test_video_digest.py \
                 tests/test_disk_analysis.py tests/test_file_search_schema.py \
                 tests/test_file_search_scope.py -v

# UIテスト（PySide6 必須）
python -m pytest tests/test_button_actions.py tests/test_features.py \
                 tests/test_settings.py tests/test_run.py \
                 -v -k "not test_tree_context_menu_triggers_duplicate"

# 各 Phase で追加するテスト
python -m pytest tests/test_navigation_history.py tests/test_tree_sync.py \
                 tests/test_clipboard.py tests/test_breadcrumb_bar.py \
                 tests/test_status_bar.py tests/test_properties_dialog.py \
                 -v
```

### 8.2 視覚回帰

- Phase C 完了時にライト／ダーク両方で `docs/screenshots/` にスクリーンショットを保存
- Phase D 完了時に同じく保存

### 8.3 手動チェックリスト（Phase 完了時）

各 Phase 完了時に以下を実施する。

- [ ] キーボードのみで UC-1〜UC-11 が完了するか
- [ ] フォーカスが目視できるか
- [ ] 状態同期（リスト / ツリー / アドレスバー）が一致するか
- [ ] ライト／ダーク両方で表示崩れがないか
- [ ] Win11 22H2+ で Mica が透ける／崩れていないか

---

## 9. 変更対象ファイル早見表

| ファイル | 役割 | 関わる Phase |
| --- | --- | --- |
| `src/file_manager/file_manager.py` | コンテナ／合成ロジック | A〜F |
| `src/file_manager/main.py` | エントリ／MainWindow | A, C |
| `src/file_manager/ui_theme.py` | トークン／QSS | C, F |
| `src/file_manager/ui_icons.py` | アイコン | B, D |
| `src/file_manager/navigation/history.py` | 履歴 | A |
| `src/file_manager/navigation/sync.py` | ペイン同期 | A |
| `src/file_manager/navigation/breadcrumb_bar.py` | パンくず | D |
| `src/file_manager/navigation/tabs.py` | タブ | E |
| `src/file_manager/operations/clipboard.py` | クリップボード | B |
| `src/file_manager/operations/transfer.py` | 転送ワーカー | B |
| `src/file_manager/operations/properties_dialog.py` | プロパティ | B |
| `src/file_manager/preview/image_preview.py` | 画像プレビュー | D |
| `src/file_manager/preview/text_preview.py` | テキストプレビュー | D |
| `src/file_manager/status_bar.py` | ステータスバー | C |
| `tests/test_*.py` | テスト | 全 Phase |

---

## 10. リスクと対策

| リスク | 影響 | 対策 |
| --- | --- | --- |
| `file_manager.py` のリファクタリングで既存テストが壊れる | リグレッション | Phase A の最初に履歴・同期だけを移植し、UI からの呼び出し側は残す。1 PR 1 切り出し |
| Windows のクリップボード MIME タイプ互換 | コピー／貼り付け不整合 | Explorer ↔ 本アプリの相互運用を**手動チェック**で検証 |
| BreadcrumbBar の幅計算 | レイアウトジャンプ | `resizeEvent` で再計算、最小幅を確保しつつ末尾は省略しない仕様 |
| プレビューペインのメモリ使用量 | 大画像でメモリ圧 | サイズ上限と `QPixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)` で抑制 |
| タブの永続化フォーマット変更 | ユーザー設定喪失 | バージョンキー（`view/tabs/version`）を持ち、互換ロード |
| 既存独自機能（動画系）への副作用 | 既存ユーザー混乱 | 各 Phase で `test_features.py` を必ず通す |

---

## 11. 受け入れ判定（実装計画レベル）

実装計画として完了したと判定するのは次のとき。

- [ ] Phase A〜C（MUST）が完了し、要件定義書 §6 の MVP DoD（機能性／操作性／視認性）を満たす
- [ ] Phase D（SHOULD）が完了し、パンくず・プレビュー拡張・トグルが利用可能
- [ ] Phase E（SHOULD）はリリース判断に応じて。MVP には含めなくてよい
- [ ] Phase F（SHOULD）の F-1〜F-4 が完了し、規模 10,000 件で UI が固まらない
- [ ] 既存テスト＋新規テストすべて緑、手動チェックリスト全項目クリア

---

## 12. 着手順序（推奨）

下記の順で進めると、各ステップの成果物が次のステップの土台になる。

1. **A-1 履歴切り出し** → A-2 同期切り出し → A-3 同期回帰テスト → A-4 設定保存整合
2. **B-1 ショートカット骨格** → B-2 クリップボード → B-3 Ctrl+L フォーカス → B-4 プロパティ → B-5 リスト補強
3. **C-1 ステータスバー** → C-2 行高プリセット → C-3 フォーカスリング → C-4 WCAG → C-5 フォルダサイズ列
4. （以降は Phase D, E, F の順）

各ステップで PR を切る。レビューと検証を挟みながら、安全に積み上げていく。

---

## 13. 参考

- `docs/file_manager_redesign_requirements.md`
- `docs/file_manager_redesign_spec.md`
- `docs/ui_modernization_plan.md`
- 本リポジトリ `CLAUDE.md`（テスト・規約）
