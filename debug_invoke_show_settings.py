import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from PySide6.QtWidgets import QApplication
from file_manager.file_manager import FileManagerWidget

app = QApplication([])
print('App started')
try:
    w = FileManagerWidget()
    w.show()
    print('Widget shown')
    try:
        w.show_settings()
        print('show_settings returned')
    except Exception as e:
        print('show_settings raised:', e)
except Exception as e:
    print('setup raised:', e)
finally:
    app.quit()
    print('App quit')
