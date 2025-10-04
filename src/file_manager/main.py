#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application entry point for the GUI file manager."""

import sys

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout

from .file_manager import FileManagerWidget


class MainWindow(QMainWindow):
    """Main application window that hosts the FileManagerWidget."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GUI File Manager")
        self.setGeometry(100, 100, 1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        self.file_manager = FileManagerWidget()
        layout.addWidget(self.file_manager)

        self._setup_menu_bar()
        self._setup_tool_bar()

        self.statusBar().showMessage("Ready")

    def _setup_menu_bar(self) -> None:
        """Create top-level menus."""
        menubar = self.menuBar()
        menubar.addMenu("File(&F)")
        menubar.addMenu("Edit(&E)")
        menubar.addMenu("View(&V)")
        menubar.addMenu("Help(&H)")

    def _setup_tool_bar(self) -> None:
        """Create application toolbar."""
        toolbar = self.addToolBar("Main Toolbar")
        toolbar.setMovable(False)
        # Example toolbar actions can be enabled when implemented.
        # toolbar.addAction("Up", self.file_manager.navigate_up)
        # toolbar.addAction("Refresh", self.file_manager.refresh)


def main() -> None:
    """Run the Qt application."""
    app = QApplication(sys.argv)
    app.setApplicationName("GUI File Manager")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("FileManager")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
