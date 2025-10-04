import importlib.util
import json
import sys
from dataclasses import is_dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src" / "file_manager"

MODELS_PATH = ROOT / "models.py"
MODELS_SPEC = importlib.util.spec_from_file_location("file_manager_models", MODELS_PATH)
models = importlib.util.module_from_spec(MODELS_SPEC)
sys.modules[MODELS_SPEC.name] = models
MODELS_SPEC.loader.exec_module(models)

APP_PREF_PATH = ROOT / "app_preferences.py"
APP_PREF_SPEC = importlib.util.spec_from_file_location("file_manager_app_preferences", APP_PREF_PATH)
app_preferences = importlib.util.module_from_spec(APP_PREF_SPEC)
sys.modules[APP_PREF_SPEC.name] = app_preferences
APP_PREF_SPEC.loader.exec_module(app_preferences)
AppPreference = app_preferences.AppPreference


def test_search_query_normalization():
    query = models.SearchQuery(keywords=[" Foo ", "", "Bar"], scope="all", case_sensitive=True, limit=25)
    assert is_dataclass(models.SearchQuery)
    assert query.keywords == ["Foo", "Bar"]
    assert query.scope == "all"
    assert query.case_sensitive is True
    assert query.limit == 25


def test_search_query_invalid_scope():
    with pytest.raises(ValueError):
        models.SearchQuery(keywords=["foo"], scope="invalid")


def test_search_result_item_paths_are_normalized(tmp_path):
    path = tmp_path / "data" / "file.txt"
    item = models.SearchResultItem(path=path, name="file.txt", matched_field="name", score=0.87)
    assert item.path == path
    assert item.directory == path.parent
    assert json.loads(item.to_json())["path"].endswith("file.txt")


def test_duplicate_group_requires_valid_reason(tmp_path):
    entry = models.DuplicateEntry(path=tmp_path / "video.mp4", size=123, duration_seconds=1.5, hash_value="abc")
    group = models.DuplicateGroup(group_id="g1", files=[entry], reason="hash")
    assert group.files[0].path.name == "video.mp4"
    with pytest.raises(ValueError):
        models.DuplicateGroup(group_id="g2", files=[entry], reason="size")


def test_disk_usage_node_totals(tmp_path):
    root = models.DiskUsageNode(path=tmp_path, display_name="root", size_bytes=100)
    child = models.DiskUsageNode(path=tmp_path / "child", display_name="child", size_bytes=40)
    root.add_child(child)
    assert root.children[0] is child
    assert root.total_size == 140


def test_digest_request_defaults(tmp_path):
    source = tmp_path / "movie.mp4"
    request = models.DigestRequest(source_path=source, thumbnail_count=8, clip_length=2.0)
    assert request.output_dir == tmp_path
    assert request.thumbnail_count == 8


def test_app_preference_validation(tmp_path):
    pref = AppPreference(
        font_family="Noto",
        font_size=12,
        icon_size=24,
        list_palette={"background": "#ffffff", "foreground": "#000000"},
        startup_mode="specific",
        startup_folder=tmp_path,
        index_db_path=tmp_path / "index.db",
    )
    assert pref.startup_folder == tmp_path
    with pytest.raises(ValueError):
        AppPreference(
            font_family="Noto",
            font_size=12,
            icon_size=24,
            list_palette={"background": "#ffffff"},
            startup_mode="unknown",
            startup_folder=tmp_path,
            index_db_path=tmp_path / "index.db",
        )


