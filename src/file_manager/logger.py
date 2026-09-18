import logging
import os
import sys

def setup_logger(name="file_manager"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        
        # コンソール出力
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # ファイル出力（オプション）
        try:
            log_dir = os.path.join(os.path.expanduser("~"), ".file_manager", "logs")
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(
                os.path.join(log_dir, "app.log"), encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception:
            # ログディレクトリが作成できない場合はコンソールのみ
            pass
            
    return logger

logger = setup_logger()
