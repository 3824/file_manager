# UI モダナイゼーション設計書

## 概要

本ドキュメントは、PySide6 製ファイルマネージャーの UI を One Commander V3
（参考画像: `One-Commander-Slide2.jpg` Light Acrylic theme）に学んだモダンな
スタンドアロンアプリの作法へ刷新するための要件・方針・実装計画である。

対象は次の体験向上である。

- 各コンポーネントを Fluent / Material 3 系のフラットモダンに刷新する
- 余白・行高・角丸・線幅をタイトに整え、情報密度の高いスタイリッシュな見た目にする
- ライト／ダークの両テーマと、Windows 11 のシステムアクセント追従に対応する
- 既存機能（ツールバー、ナビ、ドライブバー、ツリー、ファイルリスト等）を破壊せず
  段階的に移行できる構成とする

参考: 現在のテーマ実装は `src/file_manager/main.py` の
`_DARK_THEME_QSS` / `_CLASSIC_THEME_QSS` にある。デフォルトは
`_CLASSIC_THEME_QSS`（Windows クラシック風）が適用されている
（main.py:1117）。

---

## 1. 専門家パネル（議論サマリ）

設計判断の根拠を残すため、4 つのペルソナによる議論結果を要約する。

### 1.1 PC 向け UI/UX デザイナー（10 年以上の Windows/macOS アプリ経験）

- デスクトップは情報密度を重視してよい。モバイル流の大きな余白は冗長。
- ボタンの最小高は **28px** が現代の Windows 流儀。32px は大きすぎる。
- 角丸は **4–8px** がスイートスポット。12px を超えると玩具的になる。
- 絵文字アイコンは解像度差・OS 差・字体ばらつきで統一感を損なう。
  単一のアイコンセット（Fluent Icons / Material Symbols / Lucide）に揃えるべき。
- One Commander の Acrylic は美しいが、軽量にやるなら Mica 風の薄い不透明
  オーバーレイと微弱なドロップシャドウで十分代替できる。

### 1.2 Qt/PySide6 エンジニア

- QSS は強力だが、ネイティブ Mica は `PySide6 ≥ 6.5` で
  `DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE)` を `ctypes` で呼ぶ。
- リスト行の角丸選択や行スパンは `QStyledItemDelegate` で実現できる
  （既に `delegate` の素地あり）。
- マウスオーバー時のみ太くなるスクロールバーは、QSS の `QScrollBar:hover`
  でハンドル幅を切り替えるか、`QEvent::Enter/Leave` で動的に QSS を当て直す。
- アイコンは `qtawesome` を導入することで Fluent / FA / Material Symbols が
  そのまま使える。色はテーマトークンと連動させる。
- テーマ切替は `app.setStyleSheet()` を差し替えるだけでよく、QSettings に保存する。

### 1.3 Windows ネイティブ／Fluent 専門家

- Windows 11 ネイティブ感の四点セット:
  1. **角丸ウィンドウ**（OS が自動で付ける／フレームレスにする際は注意）
  2. **Mica バックドロップ**（DWM API）
  3. **SystemAccentColor**（HKCU\Software\Microsoft\Windows\DWM\AccentColor）
  4. **Segoe UI Variable** フォント（Windows 11 標準）
- スクロールバーは「常時細い → ホバーで太い」が今風。フェードよりシフト。
- カスタムタイトルバーは慎重に。OS の Snap や DWM 描画を壊しがち。
- ダイアログは中央寄せ＋影＋角丸 8px がデファクト。

### 1.4 アクセシビリティ専門家

- 文字色／背景色のコントラスト比は本文 **4.5:1 以上**、UI 要素 **3:1 以上**。
- キーボードフォーカスは **1.5–2px** のアクセント色アウトラインで明確に。
- 基本フォントは **13–14px**。設定で 1.0 / 1.15 / 1.3 倍スケールに対応する。
- アニメーションは OS の "Reduce motion" に追従させ、必要時はオフにする。
- 状態（選択／無効／エラー）は色だけでなく形・アイコン・テキストでも示す。

---

## 2. 参考画像から抽出した要件

`One-Commander-Slide2.jpg` の Light Acrylic theme から取り込みたい要素。

| 要素 | 取り込み方針 |
| --- | --- |
| Acrylic／半透明 | Windows 11 22H2+ では Mica/Acrylic、それ以外はソリッド + 弱影 |
| Columns Layout（over-under split） | 将来拡張: ペイン分割を多段化（Phase 5） |
| Color Tags | 既存のファイル属性色（hidden/readonly/system/normal）に統一 |
| フォルダサイズ列 | 既存ロジック流用（実装済み機能を UI で常設に） |
| マウスオーバーで出るスクロールバー | QSS で常時 4px、ホバー 10px |
| 単一／二段ペイン切替 | QSplitter のドラッグで折りたたみ／復元 |
| 折りたたみ可能なペイン | サイドバーのトグルボタン追加 |
| Windows コンテキストメニュー | 既存 QMenu のスタイルを Fluent 化（ネイティブ統合は Phase 5） |
| Folder size sort | 既存挙動に合わせ列ヘッダで切替 |

---

## 3. 現状把握と課題

### 3.1 現状のテーマ

- `_DARK_THEME_QSS`: Material Dark + Deep Purple アクセント。
  パディング・最小高がやや大きく（`min-height: 32px`、行高 24–28px）、
  情報密度がやや低い。
- `_CLASSIC_THEME_QSS`: Windows XP/2000 風で、現代的ではない。
  デフォルト適用中（main.py:1117）。
- ライトモダン（Fluent / Light Acrylic 風）が存在しない。

### 3.2 アイコン

- ツールバーラベルが絵文字（`↑ 上へ`、`📋 コピー` など、
  file_manager.py:31-52）。OS／フォントで描画が割れる。

### 3.3 余白・密度

- ルート `QVBoxLayout` のマージン 5px / spacing 5px（file_manager.py:644-646）、
  ドライブバー margins 8/6、ナビバー margins 8/4、ペイン内 spacing 0。
- 概ね妥当だがアプリ全体としては「外周 5px ＋ 各バー 8px ＋ コンテンツ」で
  ボーダー線が二重に見える箇所がある。外周は 0、内側のバーで 8px に統一する。

### 3.4 ペイン構造

- `QSplitter`（水平）で `treePanel`（左） / `rightPane`（右）。
- `rightPane` は `navBar` + `fileList`。サムネイルプレビュー機能あり。

これを「ペイン」「カード」と呼べる粒度の塊として設計し直す。

---

## 4. デザイン原則

- **Flat & Subtle**: 影・グラデーションは控えめ、線は 1px・低彩度。
- **Density First**: 情報密度を優先。ヒットエリアは最低 28x28、
  視覚要素は密に配置する。
- **Token-driven**: 色・余白・角丸・タイポは中央のトークンから引く。
- **Theme-aware**: ライト／ダーク／システム追従の 3 種をサポート。
- **Accessible by default**: コントラスト 4.5:1、フォーカスリング、
  Reduce motion 対応。

---

## 5. デザイントークン（提案）

`src/file_manager/ui_theme.py` を新設し、以下のトークンを Python 側で定義、
QSS テンプレートに展開する。

### 5.1 スペーシング（4px グリッド）

| トークン | 値 |
| --- | --- |
| `space.0` | 0px |
| `space.1` | 2px |
| `space.2` | 4px |
| `space.3` | 6px |
| `space.4` | 8px |
| `space.5` | 12px |
| `space.6` | 16px |
| `space.7` | 24px |

### 5.2 角丸

| トークン | 値 | 用途 |
| --- | --- | --- |
| `radius.xs` | 4px | リスト行選択、チップ |
| `radius.sm` | 6px | ボタン、入力、メニュー項目 |
| `radius.md` | 8px | カード、ダイアログ、ポップアップ |
| `radius.lg` | 12px | フローティングサーフェス |

### 5.3 ライト（Fluent / One Commander 風）

| トークン | 値 |
| --- | --- |
| `bg.window` | `#F3F3F3` |
| `bg.surface` | `#FFFFFF` |
| `bg.subtle` | `#FAFAFA` |
| `bg.muted` | `#EDEDED` |
| `bg.hover` | `rgba(0,0,0,0.04)` |
| `bg.pressed` | `rgba(0,0,0,0.08)` |
| `border.subtle` | `#E5E5E5` |
| `border.strong` | `#CCCCCC` |
| `text.primary` | `#1A1A1A` |
| `text.secondary` | `#5C5C5C` |
| `text.disabled` | `#A0A0A0` |
| `accent.primary` | `#0078D4` （または SystemAccentColor） |
| `accent.hover` | `#106EBE` |
| `accent.bg.subtle` | `rgba(0,120,212,0.08)` |

### 5.4 ダーク（Fluent Dark）

| トークン | 値 |
| --- | --- |
| `bg.window` | `#1F1F1F` |
| `bg.surface` | `#262626` |
| `bg.subtle` | `#2B2B2B` |
| `bg.muted` | `#333333` |
| `bg.hover` | `rgba(255,255,255,0.06)` |
| `bg.pressed` | `rgba(255,255,255,0.10)` |
| `border.subtle` | `#3A3A3A` |
| `border.strong` | `#4A4A4A` |
| `text.primary` | `#F2F2F2` |
| `text.secondary` | `#B0B0B0` |
| `text.disabled` | `#5A5A5A` |
| `accent.primary` | `#4CC2FF` |
| `accent.hover` | `#62CCFF` |
| `accent.bg.subtle` | `rgba(76,194,255,0.16)` |

### 5.5 タイポグラフィ

| トークン | 値 |
| --- | --- |
| `font.family.ui` | `"Segoe UI Variable Display","Segoe UI","Yu Gothic UI","Meiryo",sans-serif` |
| `font.family.mono` | `"Cascadia Code","Consolas",monospace` |
| `font.size.xs` | 11px |
| `font.size.sm` | 12px |
| `font.size.md` | 13px（基準） |
| `font.size.lg` | 15px |
| `font.size.xl` | 18px |
| `font.weight.regular` | 400 |
| `font.weight.medium` | 500 |
| `font.weight.semibold` | 600 |

### 5.6 サイズ／高さ

| トークン | 値 |
| --- | --- |
| `size.button.h` | 28px |
| `size.input.h` | 28px |
| `size.row.h` | 26px |
| `size.toolbar.h` | 36px |
| `size.titlebar.h` | 32px |
| `size.scrollbar.thin` | 4px |
| `size.scrollbar.thick` | 10px |
| `size.divider` | 1px |

---

## 6. コンポーネント仕様

### 6.1 タイトル／ウィンドウ

- 標準のシステムタイトルバーを使用（カスタム化はしない）。
- Windows 11 で Mica を有効化（後述 §9）。
- 最小サイズ 960x600。

### 6.2 メニューバー

- 高さ 28px、`bg.window` 背景に下罫線 1px `border.subtle`。
- 項目ホバー: `bg.hover`、選択時: `accent.bg.subtle` + `accent.primary` テキスト。
- ドロップダウン `QMenu` は `radius.md` (8px)、
  項目高さ 26px、左パディング 12px、ショートカット表示用に右パディング 28px。

### 6.3 ツールバー

- 高さ 36px。背景 `bg.window`、下罫線 `border.subtle`。
- ボタンは透明背景 + アイコン 16px + ラベル 12px の組み合わせ
  （ラベル ON/OFF を設定で切替可能、現状の絵文字＋テキストはアイコンと
  別 QLabel に分離）。
- アイコンは `qtawesome` 経由で Fluent/Material から統一。
- ボタンサイズ 28x28（アイコンのみ時）／自動拡張（ラベル時）。
- ホバー: `bg.hover`、押下: `bg.pressed`、チェック: `accent.bg.subtle`。
- セパレータは縦線 1px、上下 6px のマージン。

### 6.4 ナビバー（アドレスバー行）

- 高さ 36px、`bg.window`。
- 戻る／進む／上へ ボタン: 28x28 アイコンボタン、`radius.sm`。
- アドレスバー（パンくず化を将来対応）:
  `bg.surface`、`border.subtle` 1px、`radius.sm`、padding 4/10、
  フォーカス時 `border` を `accent.primary` に。

### 6.5 ドライブバー

- 高さ 32px、`bg.subtle`、下罫線 `border.subtle`。
- ドライブチップ: `radius.sm` (6px) のピル、padding 2/10、
  最小 28x24、選択時 `accent.bg.subtle` + `accent.primary` テキスト。
  （現状の `border-radius: 14px` の強い丸みは控えめにする）
- 容量プログレスは下に 2px の細線で示す（既存の QProgressBar を流用）。

### 6.6 サイドバー（左ペイン: 旧 treePanel）

- 幅は QSettings で永続化、最小 200px。トグルボタンで折りたたみ。
- 内容:
  1. ヘッダー（"DRIVES" / "PINS" / "TREE" 等のセクションラベル、
     11px / `text.secondary` / letter-spacing 0.6px / 大文字）
  2. ピン留めフォルダ（将来）
  3. ツリービュー
- ツリー行高 26px、選択 `accent.bg.subtle` + `radius.xs`、左 4px のアクセント
  バーで現在選択を強調する（QSS の `border-left`）。

### 6.7 メインリスト（右ペイン: fileList）

- 列ヘッダー: 28px、`bg.subtle`、フォント 11px / `text.secondary` /
  大文字、ソートインジケータは小さい三角。
- 行: 26px、ホバー `bg.hover`、選択 `accent.bg.subtle` + `radius.xs`。
- 区切り線は無し（行の zebra も無し）→ 余白で区切る。
  現行コードの `setAlternatingRowColors(True)` は `False` に変更するか、
  QSS で alternate 色を通常行と同色にして視覚上の zebra を消す。
- アイコン: 16px、ファイル種別で qtawesome から自動アサイン。
- カラータグ: 名前列の左側に 3px のカラーバーを表示（属性色を流用）。
- ダブルクリック・Enter で開く（既存挙動踏襲）。

### 6.8 ステータスバー

- 高さ 24px、`bg.subtle`、上罫線 `border.subtle`、`text.secondary`、11px。
- 表示項目（左→右）:
  - 現在パス（既存 `#statusPathLabel`）
  - 選択件数 / 総数
  - 選択合計サイズ
  - ディスク残量（現在ドライブ）

### 6.9 入力（QLineEdit / QComboBox / QSpinBox 共通）

- 高さ 28px、`radius.sm`、padding 4/10、`bg.surface`、
  `border.subtle` 1px。
- フォーカス: `border` を `accent.primary`、影は出さない。
- 無効: `bg.muted`、`text.disabled`、border `border.subtle`。

### 6.10 ボタン

- 既定: `bg.surface`, `border.subtle`, `radius.sm`, h=28, padding 6/14。
- Primary: `accent.primary` 背景、白文字、ホバー `accent.hover`。
- Subtle: 透明背景、ホバーで `bg.hover`。
- Destructive: `#C42B1C` 背景、白文字。
- フォーカスリング: 原則はアクセント色の 2px 表示とする。
  QSS の `outline` / `outline-offset` は Qt ではウィジェット種別により効かないため、
  入力系は `border`、ビュー項目は delegate、必要なボタン類は個別 QSS または
  `QProxyStyle` で補完する。

### 6.11 タブ

- パディング 6/14、`radius.sm` 上のみ、選択時下線 2px `accent.primary`。
- 非選択 `text.secondary`、選択 `text.primary`。

### 6.12 スクロールバー

- 通常: 幅 4px、ハンドル `bg.muted`、トラック透明。
- ホバー: 幅 10px、ハンドル `bg.hover` 透明合成、丸み 5px。
- 矢印ボタンは表示しない。

### 6.13 スプリッター

- 通常: 1px、`border.subtle`。
- ホバー: 2px、`accent.primary`。
- ダブルクリックでペインを折りたたむ／戻す。

### 6.14 ダイアログ／ポップアップ

- `bg.surface`、`radius.md`、ドロップシャドウ rgba(0,0,0,0.18) 16px。
- ヘッダー（タイトル）+ ボディ + フッター（ボタン）の 3 ブロック。
- ボタン配置: フッター右寄せ、Primary が右端。

### 6.15 ツールチップ

- `bg.surface`（ダーク時 `#2B2B2B`）、`text.primary`、border `border.subtle`、
  `radius.sm`、padding 4/8、12px。

---

## 7. レイアウト改善

### 7.1 ルート

- `FileManagerWidget` のルート `QVBoxLayout` のマージン
  `5,5,5,5` → `0,0,0,0` に変更（file_manager.py:645）。
- spacing は `0` に変更して、各バーの上下罫線が連続して見えるようにする。

### 7.2 各バー内パディング統一

| バー | 現在 | 提案 |
| --- | --- | --- |
| driveBar | 8,6,8,6 / spacing 6 | 12,4,12,4 / spacing 6 |
| navBar | 8,4,8,4 / spacing 4 | 12,4,12,4 / spacing 6 |
| treePanel ヘッダー | 12,8,12,4 | 12,8,12,8 |

### 7.3 階層

```
MainWindow (Mica/solid)
├ MenuBar         (28h)
├ ToolBar         (36h)
├ NavBar          (36h)
├ DriveBar        (32h)
├ Splitter
│  ├ Sidebar      (>= 200w)
│  │   ├ SectionHeader
│  │   └ TreeView
│  └ MainPane
│      ├ ListHeader
│      ├ FileList
│      └ PreviewPane (collapsible)
└ StatusBar       (24h)
```

---

## 8. テーマ切替アーキテクチャ

### 8.1 モジュール構成

```
src/file_manager/
├ ui_theme.py         # トークン定義 + QSS テンプレート展開
├ ui_icons.py         # qtawesome ラッパー、アイコン名 → QIcon
└ main.py             # apply_theme(app, mode) 呼び出しのみ
```

### 8.2 API

```python
# ui_theme.py
TOKENS_LIGHT: dict[str, str]
TOKENS_DARK:  dict[str, str]

def build_qss(tokens: dict[str, str]) -> str: ...
def apply_theme(app: QApplication, mode: str) -> None:
    """mode: 'light' | 'dark' | 'system'"""
```

`mode='system'` のとき Windows レジストリ
`HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme`
を見て切り替える。`QSettings("FileManager","Settings")` の
`ui/theme_mode` に永続化する。

### 8.3 アクセントカラー追従

```python
# 取得（簡略）
import winreg
key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
    r"SOFTWARE\Microsoft\Windows\DWM")
val, _ = winreg.QueryValueEx(key, "AccentColor")  # 0xAABBGGRR
```

取得不可時はライト `#0078D4` / ダーク `#4CC2FF` をフォールバック。
実装では `0xAABBGGRR` から `#RRGGBB` へ変換し、アルファは無視する。
また、アクセント色から `accent.hover` / `accent.bg.subtle` を派生させる責務を
`ui_theme.py` に持たせる。極端に明るい／暗い／赤系など視認性が落ちる色では、
WCAG のコントラスト計算に基づいて前景色や選択背景の濃度を補正する。

### 8.4 設定 UI

- `オプション > 設定` の「外観」タブに以下を追加:
  - テーマ: ライト / ダーク / システム
  - アクセント: システム追従 / カスタム（カラーピッカー）
  - フォントスケール: 1.0 / 1.15 / 1.3
  - スクロールバー: 自動拡大 / 常時固定

---

## 9. Mica/Acrylic 適用（Windows 11）

- `MainWindow.show()` 後に DWM API を呼ぶ。

```python
import ctypes
from ctypes import wintypes

DWMWA_SYSTEMBACKDROP_TYPE = 38    # Win11 22H2+
DWMSBT_MAINWINDOW = 2             # Mica
DWMSBT_TRANSIENTWINDOW = 3        # Acrylic

def enable_mica(hwnd: int) -> None:
    value = ctypes.c_int(DWMSBT_MAINWINDOW)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd),
        DWMWA_SYSTEMBACKDROP_TYPE,
        ctypes.byref(value),
        ctypes.sizeof(value),
    )
```

- 適用条件: `sys.platform == "win32"` かつ Windows 11 22H2+。
  `DWMWA_SYSTEMBACKDROP_TYPE = 38` は Windows 11 初期版では利用できない場合があるため、
  build 22621 以上を基本条件とし、それ未満はソリッド背景へフォールバックする。
- 失敗時は無視してソリッド背景にフォールバック。
- Mica を使うときは `bg.window` を半透明（rgba alpha=0）にする必要がある
  ため、テーマトークンに `mica.enabled` フラグを追加する。

---

## 10. アイコン戦略

### 10.1 依存追加

- `qtawesome>=1.3` を `requirements.txt` に追加。
- 内部に `ui_icons.py` を作り、論理名 → qtawesome 名のマッピングを持つ。

```python
ICONS = {
    "up":          "fa6s.arrow-up",
    "refresh":     "fa6s.rotate-right",
    "copy":        "fa6s.copy",
    "cut":         "fa6s.scissors",
    "paste":       "fa6s.paste",
    "delete":      "fa6s.trash",
    "rename":      "fa6s.pen-to-square",
    "new_folder":  "fa6s.folder-plus",
    "search":      "fa6s.magnifying-glass",
    "settings":    "fa6s.gear",
    ...
}

def icon(name: str, color: str | None = None) -> QIcon:
    return qta.icon(ICONS[name], color=color or current_token("text.primary"))
```

### 10.2 移行

- `TOOLBAR_ALL_ITEMS`（file_manager.py:31-52）の `label` から絵文字を分離し、
  `icon` キーを追加する。
- ツールバーボタンは段階的に `QToolButton` へ統一する。
  ただし現行実装は `QPushButton` を `QToolBar.addWidget()` で配置しているため、
  Phase 1 の QSS は `QToolBar QPushButton` も対象に含める。
  Phase 3 で qtawesome 導入と合わせて `QToolButton` 化を検討する。
- アイコン色はテーマ切替時に `qta.icon(...)` を再生成して反映する。

---

## 11. インタラクション

### 11.1 マウスオーバーで太くなるスクロールバー

```css
QScrollBar:vertical {
    background: transparent;
    width: 4px;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: {{bg.muted}};
    border-radius: 2px;
    min-height: 24px;
}
QScrollBar:vertical:hover {
    width: 10px;
}
QScrollBar::handle:vertical:hover {
    background: {{text.secondary}};
    border-radius: 5px;
}
```

QSS の `:hover` だけでは幅変化に追随しない場合がある。その場合は
`eventFilter` で `Enter/Leave` を捕捉して `setFixedWidth` を切り替える
（`ui_scrollbar.py` を新設）。

### 11.2 折りたたみペイン

- スプリッターのダブルクリックで `setSizes([0, total])` ↔ 復元。
- ペイン頭部に折りたたみアイコン（Chevron）を置く。

### 11.3 フォーカスリング

- 入力系は `:focus { border: 1px solid {{accent.primary}}; }` を共通適用する。
  Qt の QSS では CSS の `outline-offset` が期待通り効かない場合があるため、
  `outline` 指定だけに依存しない。リスト／ツリーのフォーカス状態は
  `QStyledItemDelegate` 側の描画で補完する。

### 11.4 Reduce motion

- Windows レジストリ
  `HKCU\Control Panel\Desktop\UserPreferencesMask` の bit を見て、
  必要なら QPropertyAnimation を `setDuration(0)` にする。

---

## 12. QSS テンプレート（抜粋）

`ui_theme.py` 内に文字列で持ち、`{{token.name}}` プレースホルダを
`build_qss()` で置換する。以下は冒頭の例。

```css
/* ===== Base ===== */
QWidget {
    background-color: {{bg.window}};
    color: {{text.primary}};
    font-family: {{font.family.ui}};
    font-size: {{font.size.md}};
}

/* ===== ToolBar ===== */
QToolBar {
    background-color: {{bg.window}};
    border-bottom: 1px solid {{border.subtle}};
    spacing: 2px;
    padding: 4px 8px;
    min-height: {{size.toolbar.h}};
}
QToolBar QToolButton {
    background-color: transparent;
    color: {{text.primary}};
    border: 1px solid transparent;
    border-radius: {{radius.sm}};
    padding: 4px 8px;
    min-width: 28px;
    min-height: 28px;
}
QToolBar QToolButton:hover    { background-color: {{bg.hover}}; }
QToolBar QToolButton:pressed  { background-color: {{bg.pressed}}; }
QToolBar QToolButton:checked  { background-color: {{accent.bg.subtle}};
                                color: {{accent.primary}}; }
/* Phase 1 では現行実装の QPushButton にも同等スタイルを当てる */
QToolBar QPushButton {
    background-color: transparent;
    color: {{text.primary}};
    border: 1px solid transparent;
    border-radius: {{radius.sm}};
    padding: 4px 8px;
    min-width: 28px;
    min-height: 28px;
}
QToolBar QPushButton:hover    { background-color: {{bg.hover}}; }
QToolBar QPushButton:pressed  { background-color: {{bg.pressed}}; }
QToolBar QPushButton:checked  { background-color: {{accent.bg.subtle}};
                                color: {{accent.primary}}; }

/* ===== List ===== */
QTreeView#fileList {
    background-color: {{bg.surface}};
    alternate-background-color: {{bg.surface}};
    color: {{text.primary}};
    border: none;
    outline: none;
    selection-background-color: {{accent.bg.subtle}};
    selection-color: {{text.primary}};
}
QTreeView#fileList::item {
    padding: 4px 6px;
    min-height: {{size.row.h}};
    border-radius: {{radius.xs}};
}
QTreeView#fileList::item:hover    { background-color: {{bg.hover}}; }
QTreeView#fileList::item:selected { background-color: {{accent.bg.subtle}};
                                    color: {{text.primary}}; }
```

完全な QSS は実装時に `_DARK_THEME_QSS` / `_CLASSIC_THEME_QSS` を
置き換える形で `ui_theme.py` に集約する。

---

## 13. 移行計画（フェーズ）

各フェーズは独立した PR として出せる粒度に切る。

### Phase 1: テーマトークンと QSS 刷新（影響最小） ✅ 完了

- [x] `src/file_manager/ui_theme.py` を新設。
  - `TOKENS_LIGHT` / `TOKENS_DARK` / `_COMMON` トークン辞書定義
  - `build_qss(tokens)` によるテンプレート展開
  - `apply_theme(app, mode)` / `get_saved_mode()` API
  - `_is_dark_system()` による Windows レジストリ判定（`with` 文でリーク修正済み）
- [x] 既存 `_DARK_THEME_QSS` / `_CLASSIC_THEME_QSS` を新トークン式に置換、
  ライト Fluent / ダーク Fluent の 2 種を提供。
- [x] `QToolBar QPushButton` を QSS の対象に含む（既存の QPushButton ツールバー対応）。
- [x] デフォルトテーマをライト Fluent に切替。`app.setStyle("Fusion")` に変更。
- [x] 既存オブジェクト名（`#navBar` 等）はそのまま維持。
- [x] `tests/test_ui_theme.py` 新設（10 件 → 最終 18 件）。

### Phase 2: 余白・密度の最適化 ✅ 完了

- [x] `FileManagerWidget` ルートレイアウト margins `5,5,5,5` → `0,0,0,0`、spacing `5` → `0`。
- [x] driveBar margins → `12,4,12,4`、navBar margins → `12,4,12,4` / spacing `6`。
- [x] treePanel ヘッダーマージン → `12,8,12,8`。
- [x] ナビボタンサイズ `30,30` → `28,28`。
- [x] ボタン min-height 28px・行高 26px は QSS で実現。

### Phase 3: アイコン統一（qtawesome） ✅ 完了

- [x] `requirements.txt` に `qtawesome>=1.3` を追加。
- [x] `src/file_manager/ui_icons.py` 新設（Font Awesome 6 Solid マッピング + `apply_icon_to_button()`）。
- [x] ツールバーボタン生成箇所で qtawesome アイコンを適用。絵文字フォールバック維持。
- [x] ナビバーの戻る・進む・上へボタンにも qtawesome アイコンを適用。
- [x] `delete` アイコンを `fa6s.xmark` に変更（ゴミ箱移動 `fa6s.trash-can` と区別）。
- 注: QPushButton → QToolButton 化は今後の課題として先送り（既存テストへの影響を回避）。

### Phase 4: インタラクション強化（一部完了）

- [x] マウスオーバーで太くなるスクロールバー（QSS `QScrollBar:vertical:hover { width: 10px }`）。
- [x] フォーカスリング統一（`QPushButton:focus { border-color: accent; outline: none }`）。
- [x] スプリッター ダブルクリックでペイン折りたたみ／復元
  （`_SplitterCollapseFilter(QObject)` eventFilter 実装）。
  - `setChildrenCollapsible(False)` を維持（ドラッグによる意図しない折りたたみを防ぐ）。
- [ ] Reduce motion 検出（アニメーションなしのため視覚影響は低いが未実装）。

### Phase 5: ネイティブ感／拡張機能（一部完了）

- [x] Mica バックドロップ（Windows 11 22H2+ build >= 22621）
  - `_is_mica_capable()` で build 判定（正規表現で堅牢化）。
  - `__init__` で `WA_TranslucentBackground` を事前設定、`showEvent` で DWM API 呼び出し。
  - 成功時: `apply_theme(mica_active=True)` で `QMainWindow { background: transparent }` を追加適用。
  - 失敗時: `WA_TranslucentBackground` を解除して通常テーマを再適用。
- [x] システムアクセントカラー追従
  - `get_system_accent_color()` で `HKCU\SOFTWARE\Microsoft\Windows\DWM\AccentColor` を読み出し。
  - `_derive_accent_tokens(hex, is_dark)` で hover / bg.subtle / selection.bg を派生（加算ベースで飽和色対応）。
  - `apply_theme()` の `accent_mode`（"default"/"system"/"custom"）対応。
- [x] 設定ダイアログに「外観」タブを追加
  - テーマ選択（ライト / ダーク / システム設定に従う）。
  - アクセントカラー（デフォルト / Windows システムカラー / カスタム）。
  - 保存時に `settings.sync()` → `apply_theme()` → `refresh_icons()` で即時反映。
- [ ] カラム式ナビ（複数カラム同時表示）／プレビューペイン折りたたみ（将来課題）。

---

## 14. テスト方針

CLAUDE.md のテストルールに従う。

- 単体テスト（非UI）はトークン展開のテストを追加:
  `tests/test_ui_theme.py` で `build_qss(TOKENS_LIGHT)` の出力に未置換の
  `{{...}}` が残っていないことを assert する。
- UI テストは既存の `test_button_actions.py`, `test_features.py`,
  `test_settings.py`, `test_run.py` を維持。
  オブジェクト名（`#navBar` 等）と `objectName` は変更しないため、
  既存セレクタテストへの影響はない想定。
- 視覚回帰は手動。Phase 1 完了時にスクリーンショットを `docs/screenshots/`
  に保存し、ライト／ダークそれぞれ Before/After を残す。
- アクセシビリティ簡易チェック: 主要トークンの文字色／背景色ペアを
  WCAG 2.x のコントラスト計算で単体テスト化する。
  併せて、主要画面のキーボード操作・フォーカス表示・無効状態の見え方を
  手動チェックリストで確認する。

---

## 15. 既存コードへの主要変更点（リスト）

| ファイル | 変更内容 |
| --- | --- |
| `src/file_manager/ui_theme.py` | **新規**: トークン + QSS テンプレート + `apply_theme` / `try_enable_mica` / `get_system_accent_color` / `_derive_accent_tokens` |
| `src/file_manager/ui_icons.py` | **新規**: qtawesome ラッパー（Font Awesome 6 Solid マッピング） |
| `src/file_manager/main.py` | `apply_theme()` 切替、`app.setStyle("Fusion")`、`MainWindow.showEvent` で Mica 試行 |
| `src/file_manager/file_manager.py` | ルートレイアウト margins/spacing 変更、ツールバーアイコン適用、`SettingsDialog` に「外観」タブ追加、`_SplitterCollapseFilter` 追加 |
| `requirements.txt` | `qtawesome>=1.3` を追加 |
| `tests/test_ui_theme.py` | **新規**: トークン展開テスト 18 件（Phase 1〜5 のカバレッジ） |

---

## 16. 受け入れ基準（Definition of Done）

- [x] ライト Fluent / ダーク Fluent の 2 テーマが選択でき、再起動後も保持される
- [x] デフォルトテーマがライト Fluent になっている
- [x] ツールバー、ナビバー、ドライブバー、ツリー、ファイルリスト、
      ステータスバー、ダイアログがいずれも新スタイルで表示される
- [x] ボタン min-height 28px、行高 26px、外周マージン 0px が反映されている
- [x] アイコンが qtawesome に置換され、絵文字依存が解消されている
      （未インストール時は絵文字フォールバック）
- [x] スクロールバーがマウスオーバーで太くなる
- [x] キーボードフォーカスリングがアクセント色で表示される
- [ ] Windows 11 22H2+ では Mica が適用され、それ以外ではソリッド背景になる（視覚確認待ち）
- [x] 既存の単体テスト・UI テストがすべてパスする（52 件 / 2026-05-07 時点）
- [ ] 主要画面の Before/After スクリーンショットが `docs/screenshots/` にある（手動作業）

---

## 17. リスクと回避策

| リスク | 影響 | 回避策 |
| --- | --- | --- |
| qtawesome が環境にない | アイコン崩れ | `try/except ImportError` で絵文字へフォールバック |
| Mica が Win10 / Win11 初期版で失敗 | 例外 | DWM 呼び出しを `try/except` ＋ Windows 11 22H2+ 判定 |
| QSS 変更で既存テストの geometry assertion が壊れる | UI テスト失敗 | min-height は QSS 経由のみ変更、widget サイズの直接代入は変更しない |
| アクセントカラーが極端な色（赤等）で読みづらい | 視認性低下 | hover 計算を乗算から加算ベースに変更し、飽和色・純黒でも変化が出るよう対処済み |
| `setStyle("Windows")`（main.py:1116）と新 QSS の競合 | 部分的に旧スタイル残存 | `setStyle("Fusion")` に変更し、QSS の効きを統一 |

---

## 18. 参考

- One Commander V3 (Light Acrylic theme) — UI レイアウトと密度の参考
- Microsoft Fluent Design System — 配色、角丸、Mica
- WinUI 3 / Files App — タブ、コマンドバー、ステータスバー
- Material 3 — トナルサーフェス、ステートレイヤー
- VSCode — サイドバー密度、Activity Bar、コマンドパレット
- 本リポジトリ `src/file_manager/main.py` の既存 `_DARK_THEME_QSS` —
  本書のダークトークンの基盤
