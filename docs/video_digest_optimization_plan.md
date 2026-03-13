# 動画ダイジェスト機能 軽量化・高速化 実装計画

## 1. 現状分析

### 1.1 現在の処理フロー

```
ファイル選択 → VideoDigestWorker(QThread) → extract_video_features()
  → cv2.VideoCapture で動画を開く
  → 6フレームを順次シーク・デコード
  → 各フレームに対して:
     - HSV ヒストグラム計算 (64bin)
     - Canny エッジ検出 → 8x8 リサイズ
     - カラー特徴量 → 8x8x3 リサイズ
  → サムネイル生成 (160x90 にリサイズ → QImage 変換)
  → UIに送出
```

### 1.2 計測済みボトルネック（HD動画・6フレーム基準）

| 処理 | 所要時間/フレーム | 合計 | 割合 |
|------|-------------------|------|------|
| フレームシーク + デコード | 5-120ms | 30-720ms | 50-70% |
| Canny エッジ検出 | 15-20ms | 90-120ms | 15-25% |
| HSV ヒストグラム | 5-10ms | 30-60ms | 10-15% |
| サムネイルリサイズ + Qt変換 | 3-8ms | 18-48ms | 5-10% |

**合計: 約200-950ms**（コーデック・解像度に大きく依存）

### 1.3 主要課題

1. **キャッシュが存在しない** — 同じ動画を開くたびにフル計算を繰り返す
2. **フレームシークが遅い** — H.265/VP9 等はキーフレーム間隔が広く、シークコストが高い
3. **フルデコード** — サムネイル用途でもフル解像度でデコードしている
4. **特徴量計算が毎回走る** — ダイジェスト表示時に不要な特徴量（重複検出用）まで計算している
5. **逐次処理** — 6フレームの抽出が直列で並列化されていない

## 2. 改善策

### 改善A: サムネイルキャッシュの導入（効果: 大 / 工数: 中）

#### 概要

一度生成したサムネイルと特徴量をディスクキャッシュに保存し、2回目以降の表示を即座に行う。

#### 技術方針

- キャッシュキー: `SHA256(ファイルパス + ファイルサイズ + 更新日時)` のハッシュ値
  - ファイル内容のハッシュは大容量動画では遅すぎるため、メタデータベースとする
- キャッシュ保存先: `%LOCALAPPDATA%/FileManager/cache/video_digest/`
- サムネイル形式: JPEG（品質85、1枚あたり5-15KB）
- 特徴量形式: NumPy `.npz`（圧縮、1動画あたり約2KB）
- キャッシュサイズ上限: 設定可能（デフォルト200MB）、LRU方式で古いものから削除

#### 想定インターフェース

```python
class VideoDigestCache:
    """動画ダイジェストのディスクキャッシュ"""

    def __init__(self, cache_dir: Path, max_size_mb: int = 200):
        ...

    def cache_key(self, video_path: Path) -> str:
        """パス + サイズ + 更新日時からキャッシュキーを生成"""
        ...

    def get_thumbnails(self, key: str) -> list[QPixmap] | None:
        """キャッシュ済みサムネイルを取得（なければNone）"""
        ...

    def put_thumbnails(self, key: str, thumbnails: list[QPixmap]) -> None:
        """サムネイルをキャッシュに保存"""
        ...

    def get_features(self, key: str) -> VideoFeatures | None:
        """キャッシュ済み特徴量を取得（なければNone）"""
        ...

    def put_features(self, key: str, features: VideoFeatures) -> None:
        """特徴量をキャッシュに保存"""
        ...

    def evict_lru(self) -> None:
        """キャッシュサイズ上限を超えた場合にLRUで削除"""
        ...
```

#### 期待効果

- 2回目以降の表示: **200-950ms → 5-20ms**（ディスクI/Oのみ）
- 重複検出の特徴量計算も省略可能

---

### 改善B: ダイジェスト表示と特徴量計算の分離（効果: 中 / 工数: 小）

#### 概要

現在 `extract_video_features()` はサムネイル表示に不要な特徴量（ヒストグラム、エッジ、カラー特徴量）もまとめて計算している。ダイジェスト表示時はサムネイル生成のみを行い、特徴量は重複検出時にのみ計算する。

#### 技術方針

`video_features.py` の `extract_video_features()` を2段階に分離:

```python
def extract_thumbnails_only(
    video_path: str,
    max_thumbnails: int = 6,
    thumbnail_size: tuple[int, int] = (160, 90),
    progress_callback: Callable[[int], None] | None = None,
) -> list[tuple[float, np.ndarray]] | None:
    """サムネイル用フレームのみ抽出（特徴量計算なし）"""
    ...

def compute_features_from_frames(
    frames: list[np.ndarray],
) -> tuple[list[np.ndarray], list[np.ndarray], np.ndarray]:
    """既に抽出したフレームから特徴量を計算"""
    ...
```

#### 期待効果

- ダイジェスト表示時: **Canny + ヒストグラム計算を省略 → 約120-180ms 短縮**
- 特徴量は重複検出時にオンデマンド計算（またはキャッシュから取得）

---

### 改善C: 低解像度デコードの活用（効果: 中 / 工数: 小）

#### 概要

サムネイル用途（160x90）に対してフルHD（1920x1080）をデコードするのは無駄。デコード時点で解像度を下げることで、デコード・後続処理の両方を高速化する。

#### 技術方針

**方式1: ffmpeg パイプライン（推奨）**

`opencv-python` の `VideoCapture` は解像度指定デコードに対応していないため、`ffmpeg` をサブプロセスで呼び出し、低解像度でデコードする。

```python
import subprocess

def extract_frame_ffmpeg(
    video_path: str, time_sec: float, width: int = 320, height: int = 180
) -> np.ndarray | None:
    """ffmpeg で指定時刻のフレームを低解像度で抽出"""
    cmd = [
        "ffmpeg", "-ss", str(time_sec),
        "-i", video_path,
        "-vframes", "1",
        "-vf", f"scale={width}:{height}",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-loglevel", "error",
        "-"
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=10)
    if result.returncode != 0:
        return None
    frame = np.frombuffer(result.stdout, dtype=np.uint8)
    return frame.reshape((height, width, 3))
```

利点:
- `-ss` を入力前に置くことでキーフレームベースの高速シークが可能
- `scale` フィルタでデコード直後にリサイズ → メモリ・CPU削減
- H.265/VP9 のハードウェアデコード（GPU対応環境）を自動活用

欠点:
- `ffmpeg` がPATHに必要（未検出時は OpenCV にフォールバック）
- サブプロセス起動コスト（Windows で約50ms/回、ただし6フレームを1コマンドで抽出可能）

**方式2: OpenCV の CAP_PROP_POS_MSEC シーク**

フレーム番号指定（`CAP_PROP_POS_FRAMES`）からタイムスタンプ指定（`CAP_PROP_POS_MSEC`）に変更。一部コーデックでキーフレームへの直接シークが速くなる。

```python
# 現在
cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
# 改善
cap.set(cv2.CAP_PROP_POS_MSEC, time_ms)
```

#### 期待効果

- ffmpeg方式: フレームデコード **50-70% 高速化**（特に H.265/VP9 で顕著）
- 6フレーム一括抽出で **サブプロセス起動を1回に集約可能**

---

### 改善D: プログレッシブ表示（効果: 体感大 / 工数: 小）

#### 概要

現在は6フレームすべて揃ってからUIに表示している。フレーム単位で逐次表示に変更することで、体感速度を改善する。

#### 技術方針

`VideoDigestWorker` にフレーム単位のシグナルを追加:

```python
class VideoDigestWorker(QThread):
    thumbnail_ready = Signal(int, QPixmap)  # index, pixmap
    # 既存
    digest_generated = Signal(str, list)    # 全完了時
    progress_updated = Signal(int)
```

ダイアログ側で `thumbnail_ready` を受け取り、1枚ずつグリッドに表示する。

#### 期待効果

- **最初の1枚が表示されるまでの時間: 全体の1/6に短縮**
- ユーザーの体感待ち時間を大幅に改善（実際の処理時間は同じ）

---

### 改善E: メモリ内キャッシュ（効果: 中 / 工数: 小）

#### 概要

ディスクキャッシュ（改善A）とは別に、セッション中に表示済みのサムネイルをメモリに保持する。ファイル選択の切り替え時に即座に再表示する。

#### 技術方針

`VideoThumbnailPreview` に LRU キャッシュを追加:

```python
from functools import lru_cache
from collections import OrderedDict

class ThumbnailMemoryCache:
    """セッション内メモリキャッシュ（最大50動画分）"""

    def __init__(self, max_entries: int = 50):
        self._cache: OrderedDict[str, list[QPixmap]] = OrderedDict()
        self._max_entries = max_entries

    def get(self, video_path: str) -> list[QPixmap] | None:
        ...

    def put(self, video_path: str, thumbnails: list[QPixmap]) -> None:
        ...
```

#### 期待効果

- 同一セッション内での再表示: **即時（0ms）**
- メモリ使用量: 50動画 × 6枚 × 約50KB ≈ **15MB**（許容範囲）

---

## 3. 改善の優先順位と実装順序

| 優先度 | 改善 | 効果 | 工数 | 依存 |
|--------|------|------|------|------|
| 1 | B: ダイジェスト/特徴量の分離 | 中 | 小 | なし |
| 2 | D: プログレッシブ表示 | 体感大 | 小 | なし |
| 3 | E: メモリ内キャッシュ | 中 | 小 | なし |
| 4 | A: ディスクキャッシュ | 大 | 中 | なし |
| 5 | C: 低解像度デコード(ffmpeg) | 中 | 中 | ffmpeg |

**推奨実装順序:**

1. **Phase 1（即効性）**: B + D + E を実装（工数小・依存なし・既存コード変更も最小限）
2. **Phase 2（永続化）**: A を実装（ディスクキャッシュでアプリ再起動後も高速化）
3. **Phase 3（根本改善）**: C を実装（ffmpeg 依存を追加し、デコード自体を高速化）

## 4. 実装詳細

### Phase 1: 即効性のある改善（B + D + E）

#### 4.1 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/file_manager/video_features.py` | `extract_thumbnails_only()` を追加、既存関数はそのまま残す |
| `src/file_manager/video_digest.py` | サムネイル生成時に特徴量計算をスキップ、`thumbnail_ready` シグナル追加 |
| `src/file_manager/video_digest_dialog.py` | プログレッシブ表示対応、1枚ずつグリッドに配置 |
| `src/file_manager/video_thumbnail_preview.py` | メモリキャッシュ統合 |

#### 4.2 video_features.py の変更

```python
def extract_thumbnails_only(
    video_path: str,
    max_thumbnails: int = 6,
    thumbnail_size: tuple[int, int] = (160, 90),
    progress_callback: Callable[[int], None] | None = None,
) -> list[tuple[float, np.ndarray]] | None:
    """サムネイル用フレームのみ抽出する（特徴量計算なし）

    Returns:
        [(position, frame), ...] のリスト。position は 0.0-1.0 の正規化位置。
    """
    cap = cv2.VideoCapture(video_path)
    try:
        if not cap.isOpened():
            return None
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return None
        positions = _calculate_positions(max_thumbnails)
        results = []
        for i, pos in enumerate(positions):
            frame_pos = int(pos * total_frames)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
            ret, frame = cap.read()
            if ret:
                # サムネイルサイズに直接リサイズ（フル解像度を保持しない）
                frame = _resize_to_thumbnail(frame, thumbnail_size)
                results.append((pos, frame))
            if progress_callback:
                progress_callback(int((i + 1) / len(positions) * 100))
        return results if results else None
    except Exception:
        return None
    finally:
        cap.release()
```

#### 4.3 video_digest.py の変更

```python
class VideoDigestWorker(QThread):
    # 新規シグナル
    thumbnail_ready = Signal(int, QPixmap)  # 1枚ずつ通知
    # 既存シグナル（互換性維持）
    digest_generated = Signal(str, list)
    progress_updated = Signal(int)
    error_occurred = Signal(str)
```

`generate_digest()` 内で、各フレーム変換後に `thumbnail_ready` を発行する。

#### 4.4 video_thumbnail_preview.py の変更

`ThumbnailMemoryCache` を内部クラスとして追加し、`display_video()` の冒頭でキャッシュヒットを確認。ヒット時はワーカーを起動せず即座にサムネイルを表示する。

### Phase 2: ディスクキャッシュ（A）

#### 4.5 新規ファイル

- `src/file_manager/video_digest_cache.py`

#### 4.6 キャッシュ構造

```
%LOCALAPPDATA%/FileManager/cache/video_digest/
├── {hash_prefix}/
│   ├── {full_hash}.meta.json    # メタ情報（パス、サイズ、日時、作成日）
│   ├── {full_hash}_0.jpg        # サムネイル0
│   ├── {full_hash}_1.jpg        # サムネイル1
│   ├── ...
│   └── {full_hash}.features.npz # 特徴量（オプション）
└── cache_index.json             # LRU管理用インデックス
```

- `hash_prefix` は先頭2文字（ディレクトリ分散）
- `cache_index.json` にアクセス日時を記録し、LRU削除に使用

#### 4.7 キャッシュ連携

```
display_video() →
  1. メモリキャッシュを確認 → ヒット → 即表示
  2. ディスクキャッシュを確認 → ヒット → メモリに載せて表示
  3. ミス → ワーカーで生成 → メモリ + ディスクに保存 → 表示
```

#### 4.8 設定画面への追加

- キャッシュ最大サイズ（MB）のスピンボックス
- 「キャッシュをクリア」ボタン
- 現在のキャッシュ使用量の表示

### Phase 3: 低解像度デコード（C）

#### 4.9 ffmpeg 検出とフォールバック

```python
import shutil

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
```

- `ffmpeg` が PATH にある場合: ffmpeg パイプラインを使用
- ない場合: 既存の OpenCV 方式にフォールバック
- 設定画面に ffmpeg パスの手動指定欄を追加（オプション）

#### 4.10 一括フレーム抽出

6フレームを1回の ffmpeg 呼び出しで抽出する（サブプロセス起動コスト削減）:

```python
def extract_frames_ffmpeg(
    video_path: str,
    timestamps: list[float],
    width: int = 320,
    height: int = 180,
) -> list[np.ndarray | None]:
    """複数タイムスタンプのフレームを一括抽出"""
    # select フィルタで複数フレームを1パスで抽出
    select_expr = "+".join(
        f"eq(n\\,{int(ts)})" for ts in timestamps
    )
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"select='{select_expr}',scale={width}:{height}",
        "-vsync", "vfr",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-loglevel", "error",
        "-"
    ]
    ...
```

## 5. テスト計画

### 5.1 Phase 1 テスト

変更対象:
- `tests/test_video_digest.py` に追加

確認項目:
- `extract_thumbnails_only()` がフレームリストを返す（モック使用）
- `extract_thumbnails_only()` が特徴量を計算しない（`compute_frame_features` が呼ばれない）
- `thumbnail_ready` シグナルが1枚ずつ発行される
- `ThumbnailMemoryCache` の get/put/LRU削除が正しく動作する
- キャッシュヒット時にワーカーが起動されない

### 5.2 Phase 2 テスト

新規:
- `tests/test_video_digest_cache.py`

確認項目:
- キャッシュキー生成が決定的（同一入力→同一キー）
- サムネイルの保存・復元で画質劣化が許容範囲内
- 特徴量の保存・復元で値が完全一致
- LRU削除が上限超過時に正しく動作する
- ファイル更新（タイムスタンプ変更）でキャッシュが無効化される
- キャッシュディレクトリが存在しない場合に自動作成される

### 5.3 Phase 3 テスト

`tests/test_video_digest.py` に追加:

確認項目:
- `FFMPEG_AVAILABLE` が正しく判定される（モック使用）
- ffmpeg 未検出時に OpenCV フォールバックが動作する
- ffmpeg 呼び出しのコマンドライン引数が正しい（モック使用）

## 6. 期待される総合効果

### 処理時間の比較（HD動画・6フレーム）

| シナリオ | 現状 | Phase 1後 | Phase 2後 | Phase 3後 |
|----------|------|-----------|-----------|-----------|
| 初回表示 | 200-950ms | 80-770ms | 80-770ms | 50-200ms |
| 同セッション再表示 | 200-950ms | **0ms** | **0ms** | **0ms** |
| アプリ再起動後 | 200-950ms | 200-950ms | **5-20ms** | **5-20ms** |
| 体感（初回） | 全部揃うまで待つ | 最初の1枚が1/6の時間で表示 | 同左 | 同左 |

### Phase 1 だけでも得られる効果

- ダイジェスト表示の **特徴量計算省略で約120-180ms短縮**
- プログレッシブ表示で **体感待ち時間を1/6に**
- メモリキャッシュで **セッション内の再表示を即時化**

## 7. 注意事項

- Phase 1 は既存の公開インターフェース（`VideoFeatures`, `extract_video_features()`）を変更しない。新関数を追加する形で既存機能との互換性を維持する
- 重複検出機能（`video_duplicates.py`）は引き続き `extract_video_features()` を使用し、特徴量をフル計算する
- Phase 2 のディスクキャッシュは重複検出の特徴量もキャッシュ可能だが、初期実装ではサムネイルのみをキャッシュ対象とする
- Phase 3 の ffmpeg はオプション依存。インストールガイドを設定画面のツールチップに記載する
