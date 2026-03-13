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
cd G:/project/file_manager && python -m pytest tests/test_button_actions.py tests/test_features.py tests/test_settings.py tests/test_run.py tests/test_video_thumbnail_preview.py -v -k "not test_tree_context_menu_triggers_duplicate" 2>&1 | tail -40
```

**注意:**
- `test_checkbox_detailed.py`, `test_checkbox_functionality.py`, `test_filename_similarity_dialog.py` は `pytest-qt` パッケージが必要（未インストール時はスキップ）
- `test_tree_context_menu_triggers_duplicate` は既知の失敗テスト（スキップ対象）
- `test_file_manager_settings.py` はウィジェット生成でハングする可能性あり。UIテストを個別実行する場合は2分のタイムアウトを設定すること

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

### モック/モンキーパッチを使ったテスト
```python
def test_some_action(monkeypatch, qtbot):
    called = {}
    def fake_handler(self):
        called["called"] = True
    monkeypatch.setattr(fm.FileManagerWidget, "target_method", fake_handler)
    widget = fm.FileManagerWidget()
    qtbot.addWidget(widget)
    widget.trigger_button.click()
    assert called.get("called") is True
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
