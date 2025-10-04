"""Pytest fixtures providing a lightweight qtbot replacement."""

import time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QSignalSpy, QTest


class _SimpleQtBot:
    """Minimal helper that mirrors the subset of pytest-qt used in tests."""

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._widgets = []

    def addWidget(self, widget):
        """Register widget and keep it alive for the test duration."""
        if widget is not None:
            self._widgets.append(widget)
        return widget

    def waitSignal(self, signal, timeout: int = 1000):
        """Wait until the signal fires or raise on timeout."""
        spy = QSignalSpy(signal)
        if not spy.wait(timeout):
            raise AssertionError("Signal was not emitted within timeout")
        return spy

    def waitUntil(self, condition, timeout: int = 1000, interval: int = 50):
        """Wait until condition returns True, processing events meanwhile."""
        deadline = time.monotonic() + timeout / 1000.0
        while time.monotonic() < deadline:
            if condition():
                return
            self._app.processEvents()
            QTest.qWait(interval)
        raise AssertionError("Condition was not met within timeout")

    def _finalize(self) -> None:
        """Release widgets and finish pending events."""
        while self._widgets:
            widget = self._widgets.pop()
            try:
                widget.close()
                widget.deleteLater()
            except Exception:
                pass
        self._app.processEvents()


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication exists for the entire test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def qtbot(qapp, request):
    """Provide a simple qtbot compatible helper."""
    bot = _SimpleQtBot(qapp)
    request.addfinalizer(bot._finalize)
    return bot
