# CLAUDE.md - プロジェクトルール

## プロジェクト概要

PySide6ベースのファイルマネージャーアプリケーション（Windows向け）。

## ディレクトリ構成

- `src/file_manager/` - メインソースコード
- `tests/` - テストコード（pytest）
- `docs/` - ドキュメント
- `.claude/skills/` - Claude Code スキル

## 開発ルール

### テスト実行ルール（必須）

**コードの実装・変更が完了したら、必ず `/run-tests` スキルの手順に従ってテストを実行すること。**

1. **単体テスト（非UI）**: 高速な非UIテストをまず実行
   ```bash
   cd G:/project/file_manager && python -m pytest tests/test_simple.py tests/test_models_dataclasses.py tests/test_filename_similarity.py tests/test_video_digest.py tests/test_disk_analysis.py tests/test_file_search_schema.py tests/test_file_search_scope.py -v
   ```

2. **UIテスト**: UI関連の変更時に実行
   ```bash
   cd G:/project/file_manager && python -m pytest tests/test_button_actions.py tests/test_features.py tests/test_settings.py tests/test_run.py -v -k "not test_tree_context_menu_triggers_duplicate"
   ```

3. **新機能を実装した場合**: 対応するテストファイルを作成し、テストがパスすることを確認

### 既知のテスト制約

- `test_checkbox_detailed.py`, `test_checkbox_functionality.py`, `test_filename_similarity_dialog.py` は `pytest-qt` が必要（未インストール時はスキップ）
- `test_tree_context_menu_triggers_duplicate` は既知の失敗（スキップ対象）
- `test_file_manager_settings.py` はウィジェット生成でハングする可能性あり

### テスト作成規約

- テストファイルは `tests/test_<モジュール名>.py` に配置
- PySide6 ウィジェットのテストは `qtbot` フィクスチャを使用（conftest.py で提供）
- 外部API（翻訳API等）のテストは必ずモック/モンキーパッチを使用し、実際のAPI呼び出しを行わない
- `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))` でインポートパスを設定

### コーディング規約

- UI テキストは日本語
- コメントは日本語
- PySide6 のシグナル/スロットパターンに従う
- エラーは QMessageBox でユーザーに通知
- 設定は QSettings("FileManager", "Settings") で管理

### 依存関係

- `requirements.txt` - 本体の依存パッケージ
- `requirements-test.txt` - テスト用の依存パッケージ

### Git

- メインブランチ: `main`
- 機能ブランチ: `feature/<機能名>`
