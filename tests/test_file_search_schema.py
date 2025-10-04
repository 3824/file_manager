import sys
import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "file_manager"
FILE_SEARCH_PATH = ROOT / "file_search.py"
FILE_SEARCH_SPEC = importlib.util.spec_from_file_location("file_manager_file_search", FILE_SEARCH_PATH)
file_search = importlib.util.module_from_spec(FILE_SEARCH_SPEC)
sys.modules[FILE_SEARCH_SPEC.name] = file_search
FILE_SEARCH_SPEC.loader.exec_module(file_search)
FileSearchIndex = file_search.FileSearchIndex


def test_file_index_schema_has_directory_and_hash(tmp_path):
    db_path = tmp_path / "index.db"
    index = FileSearchIndex(index_db_path=str(db_path))

    sample_dir = tmp_path / "data"
    sample_dir.mkdir()
    sample_file = sample_dir / "sample.txt"
    sample_file.write_text("hello", encoding="utf-8")

    index.update_index_for_directory(str(sample_dir))

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
        assert "directory" in columns
        assert "content_hash" in columns

        row = conn.execute(
            "SELECT directory, content_hash FROM files WHERE path = ?",
            (str(sample_file),),
        ).fetchone()
        assert row is not None
        directory, content_hash = row
        assert directory.replace('\\', '/').lower() == str(sample_dir).replace('\\', '/').lower()
        assert content_hash is None
    finally:
        conn.close()




