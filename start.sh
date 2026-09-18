#!/bin/bash

# [File Manager] 起動の準備をしています...
echo "[File Manager] 起動の準備をしています..."

# 1. 仮想環境の確認と作成
if [ ! -d ".venv" ]; then
    echo "[File Manager] 仮想環境 .venv を作成しています..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] 仮想環境の作成に失敗しました。Python 3.3+ がインストールされているか確認してください。"
        exit 1
    fi
fi

# 2. 仮想環境の有効化
source .venv/bin/activate
if [ $? -ne 0 ]; then
    echo "[ERROR] 仮想環境の有効化に失敗しました。"
    exit 1
fi

# 3. 依存パッケージのインストール
echo "[File Manager] 依存パッケージを確認しています..."
pip install -r requirements.txt --quiet
if [ $? -ne 0 ]; then
    echo "[ERROR] パッケージのインストールに失敗しました。"
    exit 1
fi

# 4. アプリケーションの起動
echo "[File Manager] アプリケーションを起動します..."
python3 run.py

if [ $? -ne 0 ]; then
    echo "[ERROR] アプリケーションがエラーで終了しました。"
fi

deactivate
