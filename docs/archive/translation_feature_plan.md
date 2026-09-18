# ファイル名日本語翻訳リネーム機能 実装計画

## 1. 目的

選択したファイルのうち、ファイル名が日本語以外で構成されているものを対象に、日本語へ翻訳した候補名を提示し、ユーザー確認後に一括リネームできる機能を追加する。

対象は「ファイル名のみ」であり、拡張子は保持する。

## 2. 想定ユースケース

1. リストビューで複数ファイルを選択する
2. 右クリックメニューから「ファイル名を日本語に翻訳」を実行する
3. 翻訳候補をプレビューで確認する
4. 必要に応じて候補名を手修正する
5. 問題ないものだけ適用して一括リネームする

## 3. 実装方針

### 3.1 UI導線

- 実装箇所は `FileManagerWidget.show_list_context_menu()` を起点とする
- 既存の「名前変更」の近くに「ファイル名を日本語に翻訳」を追加する
- 複数選択に対応し、未選択時はグレーアウトする
- 単一選択時も使用可能とする（1件のプレビューを表示）

### 3.2 翻訳対象の判定

- 拡張子を除いたベース名のみを判定対象にする
- ひらがな、カタカナ、漢字を一定割合以上含む場合は「日本語」とみなし、翻訳対象外にする
- 数字、記号、日付、連番だけのファイル名は翻訳せずスキップする
- 混合言語（例: `hello_世界.txt`）は、非日本語部分の割合が高い場合のみ翻訳対象とする
- フォルダは初期実装では対象外とし、ファイルのみ対応する

### 3.3 リネームの安全性

- OS 禁止文字 `\ / : * ? " < > |` を除去または代替する
- 前後空白、末尾ピリオドなど、Windows で不正になりやすい形式を正規化する
- 同名衝突時は自動上書きせず、プレビュー上でエラー表示して適用対象から外す
- 翻訳候補同士の衝突（複数ファイルが同一の翻訳結果になるケース）も検出する
- 翻訳結果が空文字、または元名と同一の場合はスキップする

### 3.4 翻訳API

#### 選定: Google Translate（googletrans ライブラリ）

初期実装では `googletrans` （非公式 Google Translate ラッパー）を採用する。

理由:
- APIキー不要で導入が容易
- 多言語の自動検出に対応
- 個人用途で十分な品質

制約:
- 非公式APIのため、将来的に動作しなくなる可能性がある
- レート制限が不明確

将来的に公式API（Google Cloud Translation, DeepL 等）に切り替える場合は、サービス層のインターフェースを維持したまま実装を差し替えられる構造にする。

#### API キーが必要なプロバイダへの切り替え時

- 認証情報は `QSettings` に保存する（既存プロジェクトの設定管理方式に合わせる）
- 設定画面に API キー入力欄を追加する形とする
- 注: `.env` + `python-dotenv` は本プロジェクトで未使用のため、既存の `QSettings` パターンを優先する

### 3.5 非同期処理

- 翻訳API呼び出しは `QThread` + ワーカーパターンで非同期化する
- 既存の `VideoDuplicatesWorker` パターンに倣い、`TranslationWorker(QObject)` を作成する
- プログレス表示とキャンセル機能を備える
- UI スレッドをブロックしない設計とする

## 4. 実装ステップ

### Phase 1: 翻訳サービス層の追加

新規ファイル:

- `src/file_manager/filename_translation.py`

責務:

- ファイル名ベース名の抽出
- 日本語判定（`is_japanese()` ユーティリティ）
- 翻訳API呼び出し（`googletrans` 経由）
- リネーム用ファイル名正規化（`sanitize_filename()`）
- 衝突検出（翻訳先の同名チェック）
- 一括処理結果の返却

想定インターフェース:

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TranslationStatus(Enum):
    """翻訳結果のステータス"""
    READY = "ready"
    SKIPPED_JAPANESE = "skipped_japanese"
    SKIPPED_NO_TEXT = "skipped_no_text"
    SKIPPED_SAME = "skipped_same"
    ERROR_API = "error_api"
    ERROR_CONFLICT = "error_conflict"
    ERROR_INVALID_NAME = "error_invalid_name"


@dataclass
class TranslationRenameCandidate:
    source_path: Path
    original_name: str
    translated_name: str
    source_language: str | None
    status: TranslationStatus
    message: str = ""


class FilenameTranslationService:
    """ファイル名翻訳サービス"""

    def is_japanese(self, text: str) -> bool:
        """テキストが日本語かどうかを判定する"""
        ...

    def sanitize_filename(self, name: str) -> str:
        """ファイル名をWindows互換に正規化する"""
        ...

    def translate_filenames(
        self, paths: list[Path], target_language: str = "ja"
    ) -> list[TranslationRenameCandidate]:
        """ファイル名一覧を翻訳し、リネーム候補を返す"""
        ...

    def detect_conflicts(
        self, candidates: list[TranslationRenameCandidate]
    ) -> list[TranslationRenameCandidate]:
        """翻訳候補同士および既存ファイルとの衝突を検出する"""
        ...
```

### Phase 2: プレビューダイアログ追加

新規ファイル:

- `src/file_manager/translate_preview_dialog.py`

責務:

- 翻訳候補の一覧表示（QTableWidget ベース）
- 適用対象のチェック切り替え
- 翻訳後ファイル名の手修正（編集時に衝突を再チェック）
- エラー候補の非活性表示
- プログレスバー（翻訳中の進捗表示）

UI案:

- 列: `適用 / 元の名前 / 翻訳後の名前 / 検出言語 / 状態`
- `READY` の行だけ初期チェック ON
- `translated_name` 列は編集可能（`QLineEdit` デリゲート）
- 衝突や不正名は赤系背景で表示し適用不可
- ダイアログ下部に「適用」「キャンセル」ボタン
- 翻訳中はプログレスバーとキャンセルボタンを表示

ワーカー:

```python
class TranslationWorker(QObject):
    """翻訳処理をバックグラウンドで実行するワーカー"""
    progress = Signal(int, int)           # current, total
    candidate_ready = Signal(object)      # TranslationRenameCandidate
    finished = Signal(list)               # 全候補のリスト
    error = Signal(str)
```

### Phase 3: コンテキストメニュー連携

変更対象:

- `src/file_manager/file_manager.py`

追加内容:

- `show_list_context_menu()` 内の「名前変更」アクションの次に「ファイル名を日本語に翻訳」アクションを追加
- `translate_selected_filenames()` メソッドを追加

処理フロー:

1. 選択ファイルのパス一覧を取得
2. `TranslatePreviewDialog` を生成・表示
3. ダイアログ内で翻訳ワーカーを起動し、候補を非同期で取得
4. ユーザーが確認・編集後「適用」を押下
5. 承認済み候補のみ `os.rename()` で反映
6. 成功件数・スキップ件数・失敗件数を `QMessageBox` で表示
7. `self.refresh()` でファイル一覧を更新

## 5. テスト計画

### 5.1 単体テスト

新規:

- `tests/test_filename_translation.py`

確認項目:

- `is_japanese()`: 日本語テキスト → True、英語・中国語・韓国語 → False
- `is_japanese()`: 混合テキストの閾値判定が正しい
- `sanitize_filename()`: OS禁止文字の除去
- `sanitize_filename()`: 前後空白・末尾ピリオドの正規化
- 拡張子が保持される
- 日本語名はスキップされる（`SKIPPED_JAPANESE`）
- 数字のみのファイル名はスキップされる（`SKIPPED_NO_TEXT`）
- 翻訳結果が元名と同じ場合はスキップされる（`SKIPPED_SAME`）
- `detect_conflicts()`: 同名衝突が検出される
- `detect_conflicts()`: 翻訳候補同士の衝突が検出される
- APIエラー時に `ERROR_API` になる（モック使用）

注: 翻訳APIの呼び出しはすべてモック/モンキーパッチでテストする（CLAUDE.md 規約に従い実API呼び出しを行わない）

### 5.2 UIテスト

新規:

- `tests/test_translate_preview_dialog.py`

確認項目:

- 候補一覧が正しく表示される
- `READY` の行だけ初期チェック ON
- 翻訳後ファイル名を編集できる
- 編集後の衝突再チェックが動作する
- 適用対象だけ `get_approved_candidates()` で取得できる
- エラー行が非活性で表示される

### 5.3 結合テスト

追加先:

- `tests/test_features.py`

確認項目:

- コンテキストメニューに「ファイル名を日本語に翻訳」項目が存在する
- 複数選択で翻訳ダイアログが起動する
- リネーム後にファイル一覧が更新される

## 6. 依存パッケージの追加

### requirements.txt に追加

```
googletrans==4.0.0-rc1
```

### requirements-test.txt

追加不要（既存の `pytest-mock` でAPIモックに対応可能）

## 7. 懸念点と対策

### API依存

- `googletrans` は非公式APIのため、将来動作しなくなる可能性がある
- 対策: サービス層を抽象化し、差し替え可能にする。代替候補として `deep-translator` も検討
- UI側は例外ではなく `TranslationStatus` を受け取る設計とする

### 翻訳品質

- 固有名詞や作品名は不自然な訳になる可能性がある
- プレビューで手修正を必須導線にすることで対処する

### ファイル名衝突

- 複数ファイルが同じ翻訳結果になる可能性がある
- 事前衝突チェック（既存ファイル + 翻訳候補同士）を行い、適用前にブロックする

### 性能

- 翻訳API呼び出しは `QThread` ワーカーで非同期化し、UIブロックを回避する
- プログレス表示とキャンセル機能で大量ファイル選択時にも対応する

## 8. 実装順序

1. `filename_translation.py` を追加して単体テスト `test_filename_translation.py` を作成・通過
2. `translate_preview_dialog.py`（ワーカー含む）を追加して UI テスト `test_translate_preview_dialog.py` を作成・通過
3. `file_manager.py` にコンテキストメニューと `translate_selected_filenames()` を追加
4. 結合テストを `test_features.py` に追加・通過
5. 全テスト実行で既存機能への影響がないことを確認

## 9. 今回の計画で意図的に含めないもの

- フォルダ名の翻訳リネーム
- 自動実行設定（手動実行のみ）
- 翻訳履歴の保存
- 元に戻す Undo 機能
- 複数翻訳プロバイダの切り替えUI
- 既存 `rename_selected_file()` のリファクタリング（一括リネームは翻訳機能内で完結させる）

まずは「手動実行」「確認付き」「ファイルのみ」の範囲で安全に導入する。
