import os
import sys

sys.path.insert(0, os.path.join(r"b:\project\file_manager", 'src'))

from PySide6.QtWidgets import QApplication
from file_manager.file_manager import FileManagerWidget

app = QApplication.instance() or QApplication([])
widget = FileManagerWidget()
widget.show()

# ensure tree has data; use home path maybe
from PySide6.QtCore import QPoint

index = widget.left_pane.tree_view.indexAt(QPoint(0, 0))
menu = widget.left_pane.tree_view

