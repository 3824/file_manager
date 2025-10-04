import os
import sys
import pytest
from unittest.mock import patch

# テスト対象のファイルのパスを追加
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_run_script_imports():
    """run.pyのインポートが正常に動作することを確認"""
    try:
        from run import main
        assert True  # インポートが成功した場合
    except ImportError as e:
        pytest.fail(f"Failed to import main from run.py: {str(e)}")

def test_run_script_execution():
    """run.pyのメイン処理が正常に実行できることを確認"""
    with patch('file_manager.main.main') as mock_main:
        try:
            import run
            if hasattr(run, '__main__'):
                run.main()
                mock_main.assert_called_once()
        except Exception as e:
            pytest.fail(f"Failed to execute run.py: {str(e)}")

def test_run_script_path_setup():
    """srcディレクトリがPythonパスに正しく追加されていることを確認"""
    import run
    src_path = os.path.join(os.path.dirname(os.path.abspath(run.__file__)), 'src')
    assert src_path in sys.path, "src directory is not in Python path"