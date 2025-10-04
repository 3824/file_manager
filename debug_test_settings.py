from PySide6.QtWidgets import QApplication
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from file_manager.file_manager import FileManagerWidget, SettingsDialog, QSettings

app = QApplication(sys.argv)
print('QApp created')
main = FileManagerWidget()
main.show()
print('Main widget shown')

# Use the real QWidget as parent to reproduce the issue
settings = QSettings('FileManager', 'Settings')
dlg = SettingsDialog(main, settings, main.visible_columns)
print('SettingsDialog created with real parent')

# Call accept and exit
try:
    dlg.accept()
    print('accept() returned')
except Exception as e:
    print('accept() raised:', e)

print('Exiting')
app.quit()
