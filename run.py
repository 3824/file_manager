#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUIファイラーアプリケーション実行スクリプト
"""

import sys
import os

# srcディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from file_manager.main import main

if __name__ == "__main__":
    main()
