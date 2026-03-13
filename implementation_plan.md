# Implementation Plan - Spec.md Updates

Based on `spec.md`, we need to enhance the existing `file_manager` implementation.

## 1. Goal
Implement requirements from `spec.md` that are currently missing or incomplete:
1.  **Video Metadata Columns**: Display Duration, Resolution, FPS in the detailed view.
2.  **Smart Preview**: Show video thumbnail digest on mouse hover.
3.  **Drive Bar**: Ensure drive bar features (mostly implemented, will verify).

## 2. Proposed Changes

### 2.1 Video Metadata Columns (`src/file_manager/file_manager.py`)
*   **Modify `CustomFileSystemModel`**:
    *   Increase `columnCount` to support new columns: `Duration`, `Resolution`, `FPS`.
    *   Update `headerData` to label new columns.
    *   Add `metadata_cache` dictionary to store fetched video info.
    *   In `data()`, checks cache for video files:
        *   If cached: return value.
        *   If not cached: return "..." and trigger an asynchronous fetch (using `QThreadPool` or `QThread`).
*   **VideoInfoWorker**:
    *   Create a worker/runnable that uses `VideoDigestGenerator.get_video_info` to fetch metadata without blocking the UI.
    *   On completion, update cache and emit `dataChanged`.

### 2.2 Smart Preview Integration (`src/file_manager/file_manager.py`)
*   **Modify `FileManagerWidget`**:
    *   Enable `setMouseTracking(True)` on views.
    *   Connect `entered` signal of `QTreeView`/`QListView` (or implementation of custom hover delegate).
    *   When hovering over a video file:
        *   If `VideoThumbnailPreview` is not visible, show it (or use a floating window/tooltip style).
        *   Call `self.thumbnail_preview.display_video(path)`.
    *   *Decision*: For this iteration, we will use a **Floating Widget** or a fixed **Preview Pane** at the bottom/side that updates on hover/selection, as "popup" implementation can be complex with focus stealing. The current `VideoThumbnailPreview` widget is a good candidate for a preview pane.

### 2.3 Drive Bar & UI Refinements (`src/file_manager/file_manager.py`)
*   Verify `LeftPaneWidget` properly handles drive selection and updates the view.
*   Ensure `VideoThumbnailPreview` is properly instantiated and added to the layout (it looked initialized but maybe not added in the previous read).

## 3. Verification Plan
*   **Automated Tests**:
    *   Create/Update `tests/test_file_manager_metadata.py` to test model column data and caching logic.
    *   Verify `get_video_info` integration.
*   **Manual Verification**:
    *   Run `run.py`.
    *   Navigate to a folder with videos.
    *   Check if Duration/Resolution columns populate (eventually).
    *   Hover over a video and check if thumbnails appear.
