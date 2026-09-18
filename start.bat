@echo off
setlocal enabledelayedexpansion

echo [File Manager] 起動の準備をしています...

REM 1. 仮想環境の確認と作成
if not exist ".venv" (
    echo [File Manager] 仮想環境 .venv を作成しています...
    python -m venv .venv
    if !errorlevel! neq 0 (
        echo [ERROR] 仮想環境の作成に失敗しました。Pythonがインストールされているか確認してください。
        pause
        exit /b 1
    )
)

REM 2. 仮想環境の有効化
call .venv\Scripts\activate.bat
if !errorlevel! neq 0 (
    echo [ERROR] 仮想環境の有効化に失敗しました。
    pause
    exit /b 1
)

REM 3. 依存パッケージのインストール
echo [File Manager] 依存パッケージを確認しています...
python -m pip install -r requirements.txt --quiet
if !errorlevel! neq 0 (
    echo [ERROR] パッケージのインストールに失敗しました。
    pause
    exit /b 1
)

REM 4. アプリケーションの起動
echo [File Manager] アプリケーションを起動します...
python run.py

if !errorlevel! neq 0 (
    echo [ERROR] アプリケーションがエラーで終了しました。
    pause
)

deactivate
