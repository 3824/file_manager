#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
テスト実行スクリプト
"""

import os
import sys
import subprocess

def run_tests():
    """テストを実行"""
    print("=" * 60)
    print("ファイルマネージャー設定機能のテスト実行")
    print("=" * 60)
    
    # テストファイルのリスト
    test_files = [
        "tests/test_simple.py",
        "tests/test_settings_functionality.py", 
        "tests/test_integration.py"
    ]
    
    # 各テストファイルの存在確認
    missing_files = []
    for test_file in test_files:
        if not os.path.exists(test_file):
            missing_files.append(test_file)
    
    if missing_files:
        print(f"エラー: 以下のテストファイルが見つかりません:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    # pytestの実行
    try:
        cmd = [
            sys.executable, "-m", "pytest"
        ] + test_files + [
            "-v",                    # 詳細出力
            "--tb=short",           # 短いトレースバック
            "--durations=10"        # 実行時間の表示
        ]
        
        print("テストコマンド:", " ".join(cmd))
        print("-" * 60)
        
        result = subprocess.run(cmd, capture_output=False, text=True)
        
        print("-" * 60)
        if result.returncode == 0:
            print("✓ すべてのテストが成功しました!")
            return True
        else:
            print("✗ 一部のテストが失敗しました")
            return False
            
    except FileNotFoundError:
        print("エラー: pytest が見つかりません")
        print("以下のコマンドでインストールしてください:")
        print("pip install -r requirements-test.txt")
        return False
    except Exception as e:
        print(f"エラー: テスト実行中に問題が発生しました: {e}")
        return False

def main():
    """メイン関数"""
    print("Python バージョン:", sys.version)
    print("作業ディレクトリ:", os.getcwd())
    print()
    
    success = run_tests()
    
    print("\n" + "=" * 60)
    if success:
        print("テスト完了: 設定機能は正常に動作しています")
    else:
        print("テスト失敗: 設定機能に問題があります")
    print("=" * 60)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
