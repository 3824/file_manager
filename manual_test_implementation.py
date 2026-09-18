
import sys
import os
from PySide6.QtWidgets import QApplication
from src.file_manager.file_manager import FileManagerWidget

def main():
    app = QApplication(sys.argv)
    widget = FileManagerWidget()
    widget.show()
    
    # テスト用のダミー動画ファイルがなければメッセージ表示
    print("Please use the GUI to navigate to a folder containing video files.")
    print("Verify that new columns (Attributes, Duration, Resolution, FPS) appear in Detail View.")
    print("Verify that hovering over a video file shows a thumbnail preview.")
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
