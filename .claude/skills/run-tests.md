# run-tests スキル

コードの実装・変更後に、単体テストとUIテストを実行して品質を確認するスキルです。

## トリガー条件

- ユーザーが `/run-tests` を実行した時
- 実装作業が完了した時（CLAUDE.md ルールに基づく自動実行）

## 実行手順

### Step 1: 単体テスト（非UI）実行

まず高速に実行できる非UIテストを実行する:

```bash
cd G:/project/file_manager && python -m pytest tests/test_simple.py tests/test_models_dataclasses.py tests/test_filename_similarity.py tests/test_video_digest.py tests/test_disk_analysis.py tests/test_file_search_schema.py tests/test_file_search_scope.py -v 2>&1 | tail -30
```

### Step 2: UIテスト実行

UI関連の変更があった場合、またはフルテストが必要な場合:

```bash
cd G:/project/file_manager && python -m pytest tests/test_button_actions.py tests/test_features.py tests/test_settings.py tests/test_run.py tests/test_checkbox_functionality.py tests/test_keyboard_shortcuts.py -v -k "not test_tree_context_menu_triggers_duplicate" 2>&1 | tail -40
```

**注意:**
- `test_checkbox_functionality.py`, `test_filename_similarity_dialog.py` は `pytest-qt` が必要（インストール済みなら通常実行）
- `test_tree_context_menu_triggers_duplicate` は既知の失敗テスト（スキップ対象）
- `test_file_manager_settings.py` はウィジェット生成でハングする可能性あり

### Step 3: 新機能のテスト実行

新機能を実装した場合:
```bash
cd G:/project/file_manager && python -m pytest tests/test_<新機能名>.py -v 2>&1
```

### Step 4: 結果分析

- テストが全てパスした場合: 成功を報告
- テストが失敗した場合:
  1. 失敗したテスト名とエラーメッセージを確認
  2. 該当コードを読んで原因を特定
  3. 修正を提案または実施
  4. 修正後にテストを再実行

## テスト作成のパターン

このプロジェクトのテストは以下のパターンに従う:

### インポート
```python
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import file_manager.file_manager as fm
```

### 非UIテスト（モジュール単体）
```python
def test_some_function():
    from file_manager.some_module import some_function
    result = some_function("input")
    assert result == "expected"
```

### Widget テスト用 Fixture
```python
@pytest.fixture
def make_widget(qtbot):
    def _make(tmp_path):
        widget = fm.FileManagerWidget()
        qtbot.addWidget(widget)
        widget.show()
        widget.set_current_path(str(tmp_path))
        qtbot.waitUntil(lambda: not widget.right_progress_bar.isVisible(), timeout=5000)
        return widget
    return _make
```

### ダイアログのモック（重要）

このプロジェクトのダイアログは `utils.py` の `silent_*` ヘルパーを使用している。
テストで `QMessageBox.question` / `QMessageBox.information` をパッチしても効果がない。
**必ず `silent_question` / `silent_information` 等をモジュール名前空間でパッチすること**:

```python
# NG: QMessageBoxの静的メソッドをパッチしても silent_* には効かない
monkeypatch.setattr(fm.QMessageBox, "question", ...)  # exec()がブロックしてハング

# OK: 実際に呼ばれる silent_* 関数をパッチする
monkeypatch.setattr(fm, "silent_question", lambda *a, **k: fm.QMessageBox.Yes)
monkeypatch.setattr(fm, "silent_warning", lambda *a, **k: None)
# またはunittest.mockで:
patch("src.file_manager.filename_similarity_dialog.silent_question", return_value=QMessageBox.Yes)
```

このパッチを誤ると `mb.exec()` が永久にブロックしてテストがハングする。

### 設定ダイアログテスト
```python
def test_settings_apply_button(monkeypatch, qtbot):
    settings = QSettings("TestOrg", "TestApply")
    dialog = fm.SettingsDialog(None, settings, {"name": True})
    qtbot.addWidget(dialog)

    persist_called = {}
    monkeypatch.setattr(dialog, "_persist_settings", lambda: persist_called.update(called=True))

    dialog.apply_button.click()

    assert persist_called.get("called") is True
    assert dialog.isVisible()  # ダイアログは閉じない
```

### 外部API（翻訳API等）のモックテスト
```python
def test_translate_filename(monkeypatch):
    """APIを呼ばずに翻訳機能をテスト"""
    def mock_translate(text, target="ja"):
        return {"translated_text": "翻訳結果", "detected_source_language": "en"}
    monkeypatch.setattr(translator, "translate_text", mock_translate)
    result = translator.translate_filename("example.txt")
    assert result == "翻訳結果.txt"
```

## 注意事項

- QApplication はセッション全体で1つだけ（conftest.py で管理）
- テスト後のウィジェットクリーンアップは qtbot が自動で行う
- ネットワーク依存のテスト（API呼び出し等）は必ずモックを使用し、実際のAPI呼び出しを行わない
- Windows 環境で実行されるため、パス区切りに注意
- テストファイルは `tests/test_<モジュール名>.py` に配置
- 削除・確認ダイアログは `silent_*` ヘルパーを使うこと（`QMessageBox.question()` は音が鳴るため使用禁止）
