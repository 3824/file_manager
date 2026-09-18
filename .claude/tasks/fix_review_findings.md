# コードレビュー指摘対応依頼

以下の2点を修正してください。既存の未追跡ファイルや他者の変更は戻さず、差分は対象箇所に絞ってください。

## 1. 動画サムネイルプレビューの型不一致クラッシュ

### 問題

`src/file_manager/video_digest.py` の `VideoDigestGenerator.generate_digest()` は、ワーカースレッド安全性のため `digest_generated` に `QImage` のリストを流すようになっています。

該当箇所:

- `src/file_manager/video_digest.py`
  - `thumbnail_ready.emit(index, key_image)`
  - `digest_generated.emit(video_path, thumbnails)`

一方、受け側の `src/file_manager/video_thumbnail_preview.py` は `QPixmap` 前提のままです。

該当箇所:

- `src/file_manager/video_thumbnail_preview.py`
  - `_handle_digest(self, token, video_path, pixmaps)`
  - `scaled = pixmap.scaled(...)`
  - `label.setPixmap(scaled)`

`pixmaps` に `QImage` が入ると、`QImage.scaled()` の戻り値も `QImage` になり、`QLabel.setPixmap()` に渡す箇所で例外になります。

再現例:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); from PySide6.QtWidgets import QApplication; from PySide6.QtGui import QImage, QColor; from file_manager.video_thumbnail_preview import VideoThumbnailPreview; app=QApplication.instance() or QApplication([]); p=VideoThumbnailPreview(); p._disk_cache=None; img=QImage(20,10,QImage.Format_RGB888); img.fill(QColor(1,2,3)); path='G:/project/file_manager/README.md'; p._current_video=path; p._active_token=1; p._handle_digest(1, path, [img])"
```

現在のエラー:

```text
ValueError: QLabel.setPixmap called with wrong argument values
```

### 期待する対応

`VideoThumbnailPreview` 側で `QImage` と `QPixmap` の両方を受けられるようにしてください。

推奨方針:

- `_handle_digest()` の入力をいったん `QPixmap` リストへ正規化する。
- `QImage` は GUI スレッド側で `QPixmap.fromImage(image)` に変換する。
- メモリキャッシュとディスクキャッシュには従来通り `QPixmap` を保存する。
- 既存の `QPixmap` を使うテストは壊さない。

追加テスト:

- `tests/test_video_thumbnail_preview.py` に、`_handle_digest()` が `QImage` リストを受けてもラベルへ表示できるテストを追加してください。

## 2. 動画ダイジェスト設定の保存先と読み込み先が不一致

### 問題

設定画面は `QSettings("FileManager", "Settings")` に動画ダイジェスト設定を保存しています。

該当箇所:

- `src/file_manager/settings_dialog.py`
  - `video_thumbnail_width`
  - `video_thumbnail_height`
  - `video_digest_max_frames`
  - `video_digest_burst_count`
  - `video_digest_cache_size_mb`

しかし、ポップアップの動画ダイジェストダイアログは `QSettings("FileManager", "VideoDigest")` を読んでいます。

該当箇所:

- `src/file_manager/video_digest_dialog.py`
  - `self.settings = QSettings("FileManager", "VideoDigest")`

このため、設定画面で変更したサムネイルサイズ・最大フレーム数・バースト数が `VideoDigestDialog` に反映されません。

さらに `video_digest_dialog.py` の `video_digest_burst_count` 既定値は `3` ですが、`FileManagerWidget.load_settings()` と設定画面側の既定値は `0` です。未設定時にポップアップだけ常にバースト生成になり、意図せず重くなります。

### 期待する対応

`VideoDigestDialog` は `QSettings("FileManager", "Settings")` から読むように統一してください。

推奨方針:

- `src/file_manager/video_digest_dialog.py` の `QSettings("FileManager", "VideoDigest")` を `QSettings("FileManager", "Settings")` に変更する。
- `video_digest_burst_count` の既定値を `0` に揃える。
- 既存設定との後方互換が必要なら、`Settings` に値が無い場合のみ旧 `VideoDigest` をフォールバックで読む形にしてください。ただし最終的な保存先は `Settings` に統一してください。

追加テスト:

- `tests/test_video_digest.py` または適切なテストファイルに、`QSettings("FileManager", "Settings")` に保存した値が `VideoDigestDialog` の `max_thumbnails`、`thumbnail_size`、`burst_count` に反映されるテストを追加してください。

## 確認

少なくとも以下を実行してください。

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest tests/test_video_thumbnail_preview.py tests/test_video_digest.py -q -p no:cacheprovider
```

この環境では一部の既存一時ディレクトリで `PermissionError: [WinError 5] アクセスが拒否されました` が出る場合があります。その場合は新しい `--basetemp` を指定して再実行してください。

