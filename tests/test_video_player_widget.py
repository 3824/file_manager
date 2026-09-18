import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from file_manager.video_player_widget import VideoPlayerWidget


def test_format_ms_handles_short_and_long_values():
    assert VideoPlayerWidget._format_ms(0) == "00:00"
    assert VideoPlayerWidget._format_ms(65_000) == "01:05"
    assert VideoPlayerWidget._format_ms(3_665_000) == "01:01:05"


def test_widget_defaults_to_muted_and_configured_speed(qtbot):
    widget = VideoPlayerWidget(default_speed=1.5, default_muted=True)
    qtbot.addWidget(widget)

    assert widget.audio_output.isMuted() is True
    assert widget.speed_combo.currentData() == 1.5


def test_close_button_requests_close(qtbot):
    widget = VideoPlayerWidget()
    qtbot.addWidget(widget)
    widget.show()

    called = {"closed": False}
    widget.closed_requested.connect(lambda: called.update(closed=True))

    widget.close_button.click()

    assert called["closed"] is True
