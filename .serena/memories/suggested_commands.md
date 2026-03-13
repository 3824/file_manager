# Suggested Commands (Windows/PowerShell)
## 環境セットアップ
- `python -m venv .venv`
- `.\.venv\Scripts\Activate.ps1`
- `pip install -r requirements.txt`
- `pip install -r requirements-test.txt`

## 実行
- `python run.py`

## テスト
- `pytest`
- 個別実行例: `pytest tests/test_video_duplicates.py -q`

## フォーマット/静的解析（AGENTS.md準拠）
- `black .`
- `isort .`
- `flake8`

## ビルド
- `pip install pyinstaller`
- `python build_exe.py`
- `python build_exe.py clean`

## 便利コマンド（Windows）
- 一覧: `Get-ChildItem`
- 移動: `Set-Location <path>`
- 検索: `rg <pattern>` / `rg --files`
- Git: `git status`, `git diff`, `git add -p`, `git commit`
