# ファイラー再設計 仕様書

最終更新: 2026-05-08

本書は `file_manager_redesign_requirements.md` の要件を**実装可能な仕様**に落とし込んだもの。実装順序とタスク分割は `file_manager_redesign_implementation_plan.md` を参照すること。

---

## 1. 全体アーキテクチャ

### 1.1 既存構造（維持）

```
src/file_manager/
├ main.py                       # エントリポイント（QMainWindow + Mica + apply_theme）
├ file_manager.py               # FileManagerWidget / LeftPaneWidget / SettingsDialog
├ ui_theme.py                   # トークン + QSS テンプレート + アクセント派生
├ ui_icons.py                   # qtawesome ラッパー
├ video_*.py                    # 動画ダイジェスト・サムネイル・重複検出
├ disk_analysis_dialog.py       # ディスク分析
├ file_search.py / *_dialog.py  # ファイル検索
├ filename_*.py                 # ファイル名類似性／翻訳
└ models.py                     # データクラス
```

### 1.2 新規・拡張モジュール

```
src/file_manager/
├ navigation/                   # 新規パッケージ
│  ├ breadcrumb_bar.py          # パンくずアドレスバー
│  └ history.py                 # 履歴管理（既存ロジックを切り出し）
├ operations/                   # 新規パッケージ
│  ├ clipboard.py               # コピー／切り取り／貼り付けの実装
│  ├ transfer.py                # コピー／移動のワーカー（既存 _transfer_paths_to_directory を移植）
│  └ properties_dialog.py       # ファイルプロパティダイアログ
├ preview/                      # 新規パッケージ
│  ├ image_preview.py           # 画像プレビューウィジェット
│  └ text_preview.py            # テキストプレビューウィジェット
└ status_bar.py                 # 拡張ステータスバー（選択件数／合計サイズ／パス）
```

各モジュールは `FileManagerWidget` から差し替え可能なよう、`signals/slots` で接続する。既存の単一ファイル `file_manager.py` には**コンテナ（合成ロジック）**だけを残し、責務を移していく。

---

## 2. レイアウト

```
┌─────────────────────────────────────────────────────────────────────┐
│  MenuBar                                                       28px │
├─────────────────────────────────────────────────────────────────────┤
│  ToolBar (アイコン+任意ラベル)                                  36px │
├─────────────────────────────────────────────────────────────────────┤
│  TabBar (新規・Phase D)                                         32px │
├─────────────────────────────────────────────────────────────────────┤
│  DriveBar  [C:][D:][E:] ...                                     32px │
├─────────────────────────────────────────────────────────────────────┤
│  NavBar  [‹][›][↑] [Drive › Folder › Sub …]                    36px │
├─────────────────────┬───────────────────────────────────────────────┤
│ Sidebar             │  ListHeader (Name / Size / Type / Modified)   │
│  ┌───────┐          │  ─────────────────────────────────────────────│
│  │FOLDERS│          │  📁 docs                                      │
│  ├───────┤          │  📄 README.md                12 KB  text  …  │
│  │  ▾ G: │          │  …                                            │
│  │   ▸ a │          │                                               │
│  │   ▸ b │          │                                               │
│  └───────┘          ├───────────────────────────────────────────────┤
│                     │  PreviewPane (折りたたみ可: Ctrl+P)           │
├─────────────────────┴───────────────────────────────────────────────┤
│  StatusBar  選択 3 / 384 件   142.5 MB   G:\project\file_manager 24px │
└─────────────────────────────────────────────────────────────────────┘
```

各バーの高さは QSS トークン（`size.menubar.h`, `size.toolbar.h` …）で集中管理する。

---

## 3. コンポーネント仕様

### 3.1 メニューバー

| 項目 | 仕様 |
| --- | --- |
| 高さ | 28px |
| 構成 | ファイル / 編集 / 表示 / 移動 / ツール / ヘルプ |
| 編集メニュー | 切り取り(Ctrl+X) / コピー(Ctrl+C) / 貼り付け(Ctrl+V) / 全選択(Ctrl+A) / 名前変更(F2) / 削除(Delete) / プロパティ(Alt+Enter) |
| 表示メニュー | リスト / アイコン / 詳細 / 隠しファイル / プレビューペイン(Ctrl+P) / 行高（コンパクト/ノーマル/ゆとり） |
| 移動メニュー | 戻る(Alt+←) / 進む(Alt+→) / 上へ(Alt+↑) / アドレスバーへフォーカス(Ctrl+L) |

### 3.2 ツールバー

既存の `TOOLBAR_ALL_ITEMS` を維持しつつ、以下を追加する。

| 追加項目 | id | 配置位置 |
| --- | --- | --- |
| プロパティ | `properties` | rename の右 |
| プレビュー | `preview` | view_mode の右 |
| 切り取り（既存） | `cut` | 動作する実装に差し替え |
| 貼り付け（既存） | `paste` | 動作する実装に差し替え |

### 3.3 ナビバー（パンくずアドレスバー）

#### 3.3.1 表示モード

`BreadcrumbBar` ウィジェットは 2 つのモードを持つ。

| モード | 表示 | 切替方法 |
| --- | --- | --- |
| **Crumb** | `[‹] [›] [↑]  G: › project › file_manager` （セグメントは `QToolButton`） | 通常状態 |
| **Edit**  | `[‹] [›] [↑]  [G:\project\file_manager        ]`（`QLineEdit`） | クリックまたは `Ctrl+L`、空白部分クリックで Edit、Esc で Crumb |

#### 3.3.2 セグメント

- 各セグメントは `QToolButton`（テキスト + 右側に `›` のオーナードロー）
- 左クリック: そのパスへ移動
- 右クリック: そのフォルダ直下の兄弟一覧をポップアップ（最大 50 件、超過時はスクロール）
- 利用可能幅を超えるときは**先頭側を省略**して `…` ボタンに集約する

#### 3.3.3 API

```python
class BreadcrumbBar(QWidget):
    path_requested = Signal(str)            # ユーザがパス変更を要求
    edit_requested = Signal()               # 編集モード突入要求

    def set_path(self, path: str) -> None: ...
    def set_history_state(self, can_back: bool, can_forward: bool) -> None: ...
    def focus_address(self) -> None: ...    # Ctrl+L
```

### 3.4 ドライブバー

既存仕様を維持する。スタイルは前回改修で**ピル形状＋アクセント塗り**に到達済み。

| 項目 | 仕様 |
| --- | --- |
| 高さ | 32px（QSS で固定） |
| ボタン | `{drive}:` 形式、ピル `border-radius: 12px`、ホバー＝アクセントボーダー、選択＝アクセント塗り |
| マージン | `(8,2,8,2)` |

### 3.5 サイドバー（左ペイン）

| 項目 | 仕様 |
| --- | --- |
| 幅 | 永続化、最小 200px。スプリッタ ダブルクリックで折りたたみ／復元（実装済み） |
| ヘッダー | 「FOLDERS」（11px / `text.secondary` / 大文字） |
| ツリー | `QTreeView` + `QFileSystemModel`、行高 `size.row.h`、選択行に左 3px のアクセントバー |
| ピン留めセクション | Phase D で追加。先頭に「PINNED」セクションを置く（QStandardItemModel） |
| ドロップ受容 | 既存の `files_dropped` シグナルを維持 |

### 3.6 メインリスト（右ペイン）

#### 3.6.1 列定義

`DETAIL_VIEW_COLUMNS` を維持。フォルダの場合は `size` 列を `--` または「N 項目」と表示する。

| index | key | 表示名 | 既定幅 |
| --- | --- | --- | --- |
| 0 | name | ファイル名 | 260 |
| 1 | size | サイズ | 120 |
| 2 | type | 種類 | 140 |
| 3 | modified | 更新日時 | 170 |
| 4 | permissions | 権限 | 160 |
| 5 | created | 作成日時 | 170 |
| 6 | attributes | 属性 | 180 |
| 7 | extension | 拡張子 | 110 |
| 8 | owner | 所有者 | 160 |
| 9 | group | グループ | 160 |
| 10 | duration | 再生時間 | 100 |
| 11 | resolution | 解像度 | 100 |
| 12 | fps | FPS | 60 |

すべての列は `Interactive` モード（前回改修で対応済み）、列幅・並び順・表示状態は `QSettings` に永続化する。

#### 3.6.2 行高

`size.row.h` トークンを以下の 3 段階で運用。

| プリセット | size.row.h |
| --- | --- |
| コンパクト | 22px |
| ノーマル（既定） | 24px |
| ゆとり | 28px |

設定キー: `view/row_height_preset`（"compact" / "normal" / "comfortable"）。`apply_theme()` 呼び出し前に `TOKENS_*` を上書きする。

### 3.7 プレビューペイン

#### 3.7.1 構造

```
PreviewPane (QWidget)
└ stacked: QStackedWidget
   ├ VideoThumbnailPreview (既存)
   ├ ImagePreview          (新規)
   └ TextPreview           (新規)
```

選択ファイルの拡張子で stack を切替。動画・画像・テキスト・その他で表示を出し分ける。

#### 3.7.2 トグル

- メニュー「表示 → プレビューペイン」で `Ctrl+P`
- `QSettings("FileManager","Settings")` の `view/preview_visible`（bool）に永続化
- レイアウト変更は `right_pane_layout` の `widget.setVisible(bool)` のみで十分

### 3.8 ステータスバー

新規で `StatusBar` クラスを `QStatusBar` 派生として実装する。

| 領域 | 内容 |
| --- | --- |
| 左 | 現在パス（既存 `#statusPathLabel`） |
| 中央 | 選択件数 / 全件数（例: `3 / 384 件`） |
| 中央右 | 選択合計サイズ（バイトまたは KB/MB/GB） |
| 右 | 現在ドライブの空き容量（例: `123.4 GB / 931.5 GB`、5 秒キャッシュ） |
| 一時通知 | エラー・成功などをトーストとして 3 秒だけ表示 |

更新トリガーは `selection_changed` / `set_current_path` / `refresh()` の 3 箇所。

### 3.9 タブ（Phase D）

| 項目 | 仕様 |
| --- | --- |
| 場所 | ToolBar の下、NavBar の上 |
| 中身 | タブ 1 つに対し `(current_path, scroll_pos, selection)` を保持。アクティブ切替時に復元 |
| データ構造 | `list[TabState]` を `FileManagerWidget` が保持 |
| 永続化 | `QSettings` の `view/tabs/state` に JSON で保存（最大 20 タブ） |
| ショートカット | `Ctrl+T` 追加 / `Ctrl+W` 閉じる / `Ctrl+Tab` 次へ / `Ctrl+Shift+Tab` 前へ / `Alt+1〜9` 直接 |

---

## 4. データモデル拡張

### 4.1 `FileSystemModel`

既存実装を維持。**フォルダのサイズ列**だけ「`--` または項目数」を返すように `data()` を変更する（`section == 1` の処理）。

### 4.2 `Clipboard`

`operations/clipboard.py` に `ClipboardController` を新設。

```python
class Operation(Enum):
    COPY = auto()
    CUT  = auto()

@dataclass
class ClipboardState:
    paths: list[str]
    operation: Operation
    timestamp: float

class ClipboardController(QObject):
    state_changed = Signal(object)   # ClipboardState | None

    def copy(self, paths: list[str]) -> None: ...
    def cut(self, paths: list[str])  -> None: ...
    def paste(self, target_dir: str) -> tuple[int, list[str]]: ...
    def state(self) -> ClipboardState | None: ...
```

実装ポイント:
- `QApplication.clipboard().setMimeData(QMimeData)` で OS クリップボードに `urls` を載せる
- Windows の場合は **CFSTR_PREFERREDDROPEFFECT** を `QMimeData.setData("application/x-qt-windows-mime;value=Preferred DropEffect", ...)` で `1`(copy) または `2`(move) として書き込む
- 貼り付け時は MIME を確認して既存の `_transfer_paths_to_directory` を呼ぶ
- 切り取り中アイテムは `FileItemDelegate` で半透明表示（`opacity: 0.5`）

### 4.3 `History`

既存の `_nav_history` / `_nav_forward_stack` / `_nav_jumping` を `navigation/history.py` の `NavigationHistory` クラスに移譲する。テスト容易性が上がるため。

```python
class NavigationHistory:
    def push(self, path: str) -> None: ...
    def back(self) -> str | None: ...
    def forward(self) -> str | None: ...
    @property
    def can_back(self) -> bool: ...
    @property
    def can_forward(self) -> bool: ...
```

---

## 5. キーボードショートカット仕様

| カテゴリ | キー | アクション |
| --- | --- | --- |
| 移動 | `Alt+←` | 戻る |
| 移動 | `Alt+→` | 進む |
| 移動 | `Alt+↑` | 親フォルダ |
| 移動 | `Backspace` | 親フォルダ（リスト/ツリーにフォーカスがある時のみ） |
| 移動 | `Ctrl+L` | アドレスバー編集 |
| 移動 | `F5` | 表示更新 |
| 編集 | `F2` | リネーム |
| 編集 | `Delete` | 削除 |
| 編集 | `Shift+Delete` | ゴミ箱に移動（OS の永久削除と区別したい場合は逆も検討） |
| 編集 | `Ctrl+C` | コピー |
| 編集 | `Ctrl+X` | 切り取り |
| 編集 | `Ctrl+V` | 貼り付け |
| 編集 | `Ctrl+A` | 全選択 |
| 編集 | `Ctrl+I` | 選択反転 |
| 編集 | `Ctrl+Shift+N` | 新規フォルダ |
| ファイル | `Enter` / `Return` | 開く（フォルダなら降りる） |
| ファイル | `Alt+Enter` | プロパティ |
| 表示 | `Ctrl+1` / `Ctrl+2` / `Ctrl+3` | リスト / アイコン / 詳細 |
| 表示 | `Ctrl+H` | 隠しファイル切替 |
| 表示 | `Ctrl+P` | プレビューペイン切替 |
| タブ | `Ctrl+T` | 新規タブ |
| タブ | `Ctrl+W` | タブを閉じる |
| タブ | `Ctrl+Tab` / `Ctrl+Shift+Tab` | タブ切替 |
| タブ | `Alt+1〜9` | タブを直接切替 |

実装は `QAction` ベースで `QShortcut` を作る。表示モードの `Ctrl+1〜3` とタブ直接切替が衝突しないよう、タブ直接切替は `Alt+1〜9` に統一する。

---

## 6. 設定キー一覧

### 6.1 既存（維持）

| キー | 型 | 既定 |
| --- | --- | --- |
| `last_path` | str | "" |
| `last_left_path` | str | "" |
| `last_drive` | str | "" |
| `column_widths` | list[int] | [] |
| `show_*`（各列） | bool | 個別 |
| `view_mode` | str | "list" |
| `show_hidden` | bool | False |
| `color_*` | str(#hex) | 既存 |
| `video_*` | mixed | 既存 |
| `ui/theme_mode` | str | "light" |
| `ui/accent_mode` | str | "default" |
| `ui/accent_color` | str | "#0078D4" |

### 6.2 新規

| キー | 型 | 既定 | 用途 |
| --- | --- | --- | --- |
| `view/row_height_preset` | str | "normal" | "compact"/"normal"/"comfortable" |
| `view/preview_visible` | bool | true | プレビューペイン表示 |
| `view/column_order` | list[str] | DETAIL_VIEW_COLUMNS の並び | 列の並び順 |
| `view/address_bar_mode` | str | "auto" | "crumb"/"path"/"auto" |
| `view/dblclick_behavior` | str | "open" | "open"（既定）/ "navigate_only"（フォルダのみ降りる） |
| `view/splitter_state` | bytearray | None | QSplitter.saveState() |
| `view/tabs/state` | str(JSON) | "[]" | タブの永続化（Phase D） |
| `clipboard/last_op` | str | "" | "copy"/"cut" の最終状態（プロセス再起動時はクリア） |

`QSettings.sync()` は **`closeEvent` ＋アイドル時** にまとめて呼ぶ。1 操作 1 回の原則を守る。

---

## 7. 状態遷移とフロー

### 7.1 ナビゲーションフロー

```
[ユーザー操作]
   ├ ドライブボタン        ─→ select_drive(d)        ─┐
   ├ ツリーアイテム        ─→ on_tree_clicked        ─┤
   ├ アドレスバー Enter    ─→ navigate_to_address    ─┤
   ├ ダブルクリック        ─→ on_list_double_clicked ─┤
   ├ Alt+← / Alt+→ / Alt+↑ ─→ navigate_back/forward/up┤
   └ ファイル操作完了      ─→ refresh()              ─┤
                                                       ▼
                                            set_current_path(path)
                                                       │
                                            ┌──────────┴──────────┐
                                            ▼                     ▼
                                _sync_left_pane_to_path     set_current_path_async
                                  (ツリー同期)              (リスト読み込み)
                                            │                     │
                                            ▼                     ▼
                                    _trigger_tree_load     load_path_sync
                                            │                     │
                                            ▼                     ▼
                                    _apply_tree_selection    list_view.setRootIndex
                                  または _schedule_tree_sync
                                            │                     │
                                            └──────────┬──────────┘
                                                       ▼
                                            update_breadcrumb / update_status
```

### 7.2 クリップボード操作フロー

```
Ctrl+C 押下
   ▼
ClipboardController.copy(selected_paths)
   ├─ QMimeData に urls 設定
   ├─ Windows: Preferred DropEffect = 1 (Copy)
   └─ state_changed.emit(ClipboardState(COPY))

Ctrl+V 押下
   ▼
ClipboardController.paste(current_path)
   ├─ クリップボードから QMimeData 取得
   ├─ urls/Preferred DropEffect から (paths, op) を抽出
   ├─ TransferWorker(paths, current_path, op) を別スレッドで実行
   ├─ 進捗ダイアログ表示
   └─ 完了後: refresh() → _sync_left_pane_to_path
```

### 7.3 エラー復帰フロー

| 状況 | 復帰方法 |
| --- | --- |
| 無効パスをアドレスバーに入力 | 直前の有効値に戻し、ステータスバーに 3 秒トースト |
| 表示中フォルダが操作中に消失 | 親フォルダへ自動フォールバック、ステータスバーに通知 |
| 貼り付け先が読み取り専用 | エラーダイアログ表示、操作キャンセル |
| 同名衝突 | 「上書き／スキップ／別名／キャンセル」ダイアログ |
| 設定値破損 | デフォルトにフォールバック、起動を継続 |

---

## 8. アクセシビリティ仕様

### 8.1 アクセシブル名

| 対象 | accessibleName 例 |
| --- | --- |
| 戻るボタン | "戻る (Alt+←)" |
| 進むボタン | "進む (Alt+→)" |
| 上へボタン | "親フォルダへ (Alt+↑)" |
| ドライブボタン | "ドライブ {drive}" |
| アドレスバー | "アドレス" |
| 検索ボックス | "ファイル名フィルター" |

### 8.2 フォーカス順序

```
ToolBar の各ボタン → NavBar(戻る/進む/上へ) → Address(BreadcrumbBar) →
DriveBar の各ボタン → Sidebar Tree → ListView → PreviewPane → StatusBar
```

`Tab` で順送り、`Shift+Tab` で逆送り。フォーカスリングはアクセント色 2px。

### 8.3 コントラスト

`tests/test_ui_theme.py` に `test_text_contrast_ratio` を追加し、`bg.window` × `text.primary` の比が 4.5:1 以上、`bg.window` × `border.subtle` が 3:1 以上であることを assert。

---

## 9. パフォーマンス指標

| 操作 | 目標 |
| --- | --- |
| フォルダ切替（≤1,000 件） | 200 ms 以内に最初のレンダリング開始 |
| フォルダ切替（≤10,000 件） | 5 秒以内に完了、その間 UI 応答可能 |
| サムネイルプレビュー | 200 ms 以内に開始 |
| 列幅・列順の保存 | I/O は debounce 200 ms（連続変更時の I/O 抑制） |
| クリップボード貼り付け（100 ファイル） | 進捗ダイアログ表示・キャンセル可能 |

---

## 10. テスト仕様

### 10.1 既存テストの維持

| テスト | 維持義務 |
| --- | --- |
| `tests/test_button_actions.py` | 全パス |
| `tests/test_features.py` | 全パス |
| `tests/test_settings.py` | 全パス |
| `tests/test_ui_theme.py` | 全パス＋追加 |
| `tests/test_checkbox_functionality.py` | 全パス |
| `tests/test_filename_similarity_dialog.py` | 全パス |

### 10.2 新規テスト

| ファイル | 内容 |
| --- | --- |
| `tests/test_breadcrumb_bar.py` | パス → セグメント分解、Edit/Crumb 切替、無効パスの拒絶 |
| `tests/test_clipboard.py` | コピー／切り取り／貼り付けの相互運用、Preferred DropEffect の MIME 書込 |
| `tests/test_navigation_history.py` | push/back/forward の整合、`_nav_jumping` 相当の挙動 |
| `tests/test_properties_dialog.py` | 単一・複数選択時の集計、動画メタデータ読み出し |
| `tests/test_status_bar.py` | 選択件数・合計サイズの算出、トースト表示・消滅 |
| `tests/test_row_height_preset.py` | プリセット切替で QSS が更新される |
| `tests/test_sync_after_operation.py` | 削除・移動・リネーム後にツリーがリストと一致する（既存ロジックの回帰防止） |

### 10.3 視認性テスト

| ファイル | 内容 |
| --- | --- |
| `tests/test_contrast_ratio.py` | WCAG 2.1 AA 準拠を自動検証 |

### 10.4 手動チェックリスト

- [ ] キーボードのみで UC-1〜UC-11 が完了する
- [ ] フォーカスが常に視認できる
- [ ] パス変更・操作後にツリーが追従する
- [ ] 大量ファイル（≥5,000 件）で UI が固まらない
- [ ] Mica が有効な場合の見た目（Win11 22H2+）

---

## 11. 移行・互換戦略

### 11.1 既存コードからの分離

`file_manager.py` が現在 3,500 行を超える単一ファイルに膨れている。本仕様の実装にあたり、以下のリファクタリングを段階的に行う。

| Phase | 切り出し対象 | 行き先 |
| --- | --- | --- |
| A | 履歴管理 (`_nav_history` 等) | `navigation/history.py` |
| B | 同期ロジック (`_sync_left_pane_to_path` 等) | `navigation/sync.py` |
| C | クリップボード | `operations/clipboard.py` |
| C | 転送ワーカー (`_transfer_paths_to_directory` 等) | `operations/transfer.py` |
| C | プロパティダイアログ | `operations/properties_dialog.py` |
| D | プレビュー（画像／テキスト） | `preview/*.py` |
| D | タブ管理 | `navigation/tabs.py` |

### 11.2 既存 QSettings キーの扱い

- 既存キーは**変更しない**。新規キーは `view/...` 名前空間に置く。
- 旧キーが新キーで参照される場合は、初回起動時に旧キーから新キーへ複製してから新キーを正とする。

### 11.3 シグナル互換

`LeftPaneWidget.drive_selected` 等の既存シグナルは**シグニチャを変えない**。新たな同期処理は内部リファクタで吸収する。

---

## 12. 受け入れ判定（仕様レベル）

仕様としての完成は次を満たすとき。

- [ ] 本仕様の §3〜§8 がすべて実装されている
- [ ] §10 のテストがすべて緑
- [ ] §10.4 の手動チェックリストが完了している
- [ ] 既存テストが破綻していない
- [ ] CLAUDE.md の規約（日本語 UI／コメント、QSettings ネームスペース）に準拠している

---

## 13. 参考

- `docs/file_manager_redesign_requirements.md`
- `docs/ui_modernization_plan.md`
- [Microsoft Learn: BreadcrumbBar](https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/breadcrumbbar)
- [Files App Documentation](https://files.community/docs)
- [Microsoft: Compact mode in File Explorer](https://learn.microsoft.com/en-gb/answers/questions/5667932/how-to-correct-the-compact-view-that-isnt-compact)
- [Multi Commander Default Keyboard Shortcuts](https://multicommander.com/Docs/keyboard-shortcuts/WindowsExplorerStyle)
- [QFileSystemModel - Qt for Python](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QFileSystemModel.html)
