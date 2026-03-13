# コードレビュー結果

## Findings

1. **High**: 設定保存時に新規列キーが欠落し、動画メタデータ列が恒久的に非表示になる
- 対象: `src/file_manager/file_manager.py:2644`
- 詳細:
  - `SettingsDialog._persist_settings()` の `updated_columns` が旧10列のみで再構築されており、今回追加された `duration` / `resolution` / `fps` を落としています。
  - その後 `parent.visible_columns = updated_columns.copy()` で親へ反映されるため、`FileManagerWidget.update_column_visibility()` 側で `self.visible_columns.get(key, False)` が `False` となり、3列が非表示になります。
- 影響:
  - 設定ダイアログを一度保存すると、追加した動画メタデータ列が表示されなくなる（回帰）。
- 修正案:
  - `updated_columns` を固定dictで再構築せず、既存 `self.visible_columns` をベースに必要キーのみ上書きする。
  - もしくは `duration` / `resolution` / `fps` も保存対象に明示追加する。

2. **Medium**: 動画ダイジェストが利用不可でも `VideoMetadataWorker` を無条件生成しており、オプション機能が必須化している
- 対象: `src/file_manager/file_manager.py:844`, `src/file_manager/file_manager.py:729`
- 詳細:
  - `FileManagerWidget.__init__()` で `self.metadata_worker = VideoMetadataWorker()` を常に実行しています。
  - `VideoMetadataWorker.__init__()` は `VideoDigestGenerator()` を無条件で生成します。
  - 先頭では `video_digest` の import 失敗を `VIDEO_DIGEST_AVAILABLE = False` で許容する設計ですが、ここで無条件生成しているため、将来 import 失敗条件が増えた場合に起動失敗リスクがあります。
- 影響:
  - オプション機能の障害がアプリ本体の起動可否に波及し得る。
- 修正案:
  - `VIDEO_DIGEST_AVAILABLE` が `True` の場合のみワーカーを生成・接続する。
  - `False` の場合はメタデータ列を空表示にするフォールバックを維持する。

## Open Questions / Assumptions
- `duration` / `resolution` / `fps` を「常時表示固定列」にする意図であれば、設定保存処理と列メニューの設計をその方針に合わせて明文化する必要があります。
- `video_digest` import 失敗を完全に許容しない方針なら、先頭の `try/except ImportError` 自体を見直す方が一貫します。

## Change Summary
- 差分レビュー対象: `src/file_manager/file_manager.py`, `src/file_manager/video_duplicates_dialog.py`
- 主な指摘は `file_manager.py` 側の設定保存ロジックとオプション依存の扱いに集中。
- `video_duplicates_dialog.py` 追加分では、今回の確認範囲で即時の機能破綻は見当たりませんでした。

## 検証メモ
- `python -m pytest ...` は `PySide6` 未導入のためこの環境で実行不可。
