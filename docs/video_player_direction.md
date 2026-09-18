# 動画プレーヤー機能 — 方向性検討ドキュメント

最終更新: 2026-05-17
ステータス: 方向性検討（実装着手前）
関連ドキュメント: [`docs/video_scrub_preview_plan.md`](./video_scrub_preview_plan.md)

---

## 1. 目的

選択した動画ファイルの内容を **再生しながら確認できる** プレビュー機能を、本ファイルマネージャーに追加する。

本ドキュメントは、ソフトウェアエンジニア（SE）/ UI デザイナー / 認知科学（人の認知）の 3 視点による議論と Web 調査に基づき、採るべき方向性を複数案で提示するものである。

---

## 2. 既存実装の前提

| 項目 | 現状 |
|------|------|
| 既存プレビュー | `VideoThumbnailPreview`（`video_thumbnail_preview.py`）が右ペイン下部の `bento_grid` に常時表示され、最大 6 枚の等間隔サムネイルを生成 |
| デコード基盤 | `cv2`（opencv-python）が必須依存、未導入時はプレースホルダで縮退 |
| 進行中の計画 | [スマートスクラブ・プレビュー](./video_scrub_preview_plan.md)：FFmpeg + PySceneDetect でシーン境界キーフレームを抽出し、ホバーでスクラブ表示する設計 |
| QtMultimedia 採用状況 | 未採用（`QMediaPlayer` / `QVideoWidget` は使用ファイル 0） |
| 既存ユーザ設定の重要事項 | マウスオーバーサムネイル拡大はデフォルト OFF（user memory）。**動画の自動再生は同様に「明示的なオプトイン」が原則** |

→ **今回の追加は「右ペインを占有しない別ウィンドウの軽量プレーヤー」**として位置付けるべき。既存の `VideoThumbnailPreview` は維持し、動画再生は明示操作で一時的に開く独立ウィンドウに限定する。

---

## 3. 3 視点での議論サマリ

### 3.1 ソフトウェアエンジニア視点（実装方式）

#### 候補バックエンド比較

| バックエンド | 長所 | 短所 | 評価 |
|---|---|---|---|
| **`QMediaPlayer` + `QVideoWidget`**（PySide6 標準） | 追加依存ゼロ。Qt の widget hierarchy にネイティブ統合。別ウィンドウ化しやすい。`setPlaybackRate`/`setLoops`/`setMuted` 標準提供 | Windows の OS コーデックに依存。一部 MP4（HEVC等）が再生不能のケースが報告されている。エラーが silent になりやすい | **第一候補** |
| **PySide6 6.5+ の FFmpeg バックエンド** | `QT_MEDIA_BACKEND=ffmpeg` で QMediaPlayer 経由のまま H.265/HEVC を含む幅広いコーデック対応 | デフォルトのまま使えるが、ジッタや "surface pool size" 警告など環境依存のトラブル報告あり | **第一候補と組合せ** |
| `python-vlc`（libVLC バインディング） | コーデック耐性が抜群、HW デコード強力 | VLC ランタイムの同梱/インストールが必要 → PyInstaller exe の配布サイズが急増。ウィンドウ埋込みが OS ハンドル経由でやや脆い | 第二候補（QMediaPlayer NG 時のフォールバック） |
| `OpenCV` + `QTimer` で自前デコード | 既存依存のみで完結、サムネイル生成と統合しやすい | 音声非対応、A/V 同期を自前実装、CPU 負荷大 | **音声不要の極小プレビューに限れば可** |
| `PyAV`（FFmpeg バインディング） | 音声/映像を細かく制御可能 | 学習コスト高、Qt とのブリッジを自作 | 不採用 |

#### 重要な実装上の留意点（Web調査より）

- **バックエンド切替が必要**: Windows で `QT_MEDIA_BACKEND=ffmpeg` を設定するだけで再生不能だった MP4 が再生できるケースが多数報告されている。`__init__.py` の `OPENCV_FFMPEG_LOGLEVEL` 設定と同様の場所で環境変数を投入する。
- **`errorOccurred` シグナルの必須処理**: 未接続だと "サイレントに無音/黒画面" になり、ユーザは原因が掴めない（Qt フォーラムの定番落とし穴）。
- **PyInstaller 同梱**: Qt Multimedia の plugin (`plugins/multimedia/*.dll`)・FFmpeg dll を `build_exe.py` に明示的に含める必要がある。
- **複数ファイル選択中の再生**: `currentIndex` 変更ごとの load/play を 200ms 程度デバウンスしないと、リスト矢印移動でクラッシュ・スタッタが発生する。
- **音声のデフォルト**: ファイル選択のたびに音が出るのは耐え難い。**`muted=True` を初期値**にし、明示的なクリックで解除する（YouTube 等のプレビュー慣習に一致）。

### 3.2 UI デザイナー視点（UX パターン）

#### 既存ソフトの実装パターン（調査結果）

| ソフト | プレビュー型 | 再生発火 | 音 | 観察された問題 |
|---|---|---|---|---|
| Windows Explorer Preview Pane | 右ペイン埋込 | 選択 → 自動 | 自動オン | 重い・固まる・スクロール時 CPU 高負荷の苦情多数 |
| macOS QuickLook (Space キー) | モーダル/フローティング | キー操作 → 自動 | 自動オン | サイズ変更可。ユーザの意図が明示的 |
| Adobe Bridge | 右ペイン埋込 + フルスクリーン | 選択 → スクラブ可、再生はクリック | クリック後オン | スクラブで概要、再生で深掘り |
| YouTube/Netflix サムネイル | サムネ上 | ホバー → 自動（無音） | 常にミュート | デファクトの "発火基準" |
| Plex/Jellyfin | サムネ上 + 全画面再生 | ホバー → トリックプレイ画像、クリック → 再生 | クリック後 | プレビューと再生を分離 |
| DaVinci Resolve / Blackmagic | タイムライン | ホバー → スクラブ、Space → 再生 | 再生時のみ | プロ向けの「ホバー=スカウト、Space=再生」 |

#### 重要な原則

1. **発火条件は段階的に**:「選択（メタ表示） → ホバー（スクラブ） → 明示操作（再生）」と段階を踏むのが UX 上の現代標準。Explorer の「選択即再生＋音」は嫌われている。
2. **無音再生がデフォルト**: ホバー・自動再生は常にミュート。音は明示的アンミュート後のみ。
3. **アスペクト比 16:9 を尊重**: 縦長・スクエア動画はレターボックスで黒帯、ウィジェット自体は伸縮させない。
4. **コントロールは最小**: 再生/停止・シーク・音量・全画面・速度の 5 つで足りる。ファイル管理の流れを切らない。
5. **キーボードは Space=再生/停止、←/→=5秒シーク、F=フルスクリーン、M=ミュート** が業界標準。

### 3.3 認知科学視点（人の動画把握）

#### 主要な知見（HCI/認知研究より）

- **動画把握タスクは「ワーキングメモリ」を圧迫する**: 一度に提示する情報は厳選すべき（Sweller の認知負荷理論）。複数サムネイル + 再生映像 + 音声 + 操作 UI を同時提示すると認知過負荷で、結果的に「内容把握」が遅くなる。
- **0.05 秒で形成される第一印象**: サムネイルの認識は 50ms オーダーで完了する（Hum Perception-Centric Thumbnail Generation, ACM MM 2023）。**初期表示はサムネ/シーン代表画像で十分**で、再生は「もっと知りたい」と判断したユーザに対する深掘りツールである。
- **動画スキミング研究の合意**（ACM Comp Surveys "Video Skimming: Taxonomy and Comprehensive Survey"）: 等倍再生は **「概要把握」には非効率**。シーン境界キーフレームの提示 → 興味箇所を 1.5x〜2.0x で再生 → 細部はノーマル速度、という階層的アプローチが効率的。
- **オブジェクト検索タスク**（PMC 11125056, "Video Playback Visual Cues in Object Retrieval"）: 「対象物の最終出現位置からの通常速度再生」が探索時間と認知負荷を有意に下げる。**シーク+部分再生** は単なるホバースクラブより高効率な場面がある。
- **「動き」は強制的に注意を奪う**（PreAttentive Processing）: 自動再生は視線を独占する。ユーザが別タスク（ファイル整理）をしている時に視界の隅で映像が動き続けるのは、認知的妨害として強く嫌われる。

#### 設計への含意

- **「概要 → 再生 → 詳細」の階層構造**を UI に反映すべし。再生は最初に出すものではなく、ユーザの能動的選択で開く。
- **再生中の他操作は注意分散コストが高い**。再生時は他のチラチラ動く UI（自動更新のメタ情報など）を抑制する。
- **再生速度の選択肢を必ず提供**（1.0x / 1.5x / 2.0x）。学習動画・チュートリアル動画では 1.5x 以上が標準視聴速度になっている。

---

## 4. 方向性 — 3 つの案

軽量性とファイラー本体の操作性を優先し、**右ペイン内に再生領域を追加しない**ことを前提とする。既存の `VideoThumbnailPreview` は維持し、再生プレーヤーは別ウィンドウで必要時だけ生成する。

---

### 案 A: 別ウィンドウ軽量プレーヤー（小規模、推奨）

> ファイル一覧から明示操作で軽量な別ウィンドウを開き、ファイラー本体の右ペインを占有しない案。

#### 概要

- ファイル一覧で動画を選択し、**Space キー**、ツールバー、またはコンテキストメニューの「動画を再生」で専用ウィンドウを開く。
- プレーヤーウィンドウは `QDialog` または独立 `QWidget` とし、ファイラー本体の右ペイン・`bento_grid` には組み込まない。
- `QMediaPlayer + QVideoWidget` はウィンドウを開いた時だけ生成し、閉じた時に `stop()` と `setSource(QUrl())` で解放する。
- コントロール: Play/Pause・シークバー・時刻表示・音量/ミュート・速度（1.0/1.5/2.0x）・外部プレーヤーで開く・閉じる。
- キー: Space=再生/停止、←/→=5秒、M=ミュート、F=最大化/復元、Esc=閉じる。

#### スコープ

| 項目 | 内容 |
|---|---|
| 新規モジュール | `src/file_manager/video_player_widget.py` + `src/file_manager/video_player_window.py` |
| 改修 | `file_manager.py`（Space ショートカット・ツールバー/コンテキストメニュー・選択動画パスの受け渡し）、`__init__.py`、`settings_dialog.py` |
| バックエンド | `QMediaPlayer` 標準。`QT_MEDIA_BACKEND=ffmpeg` は起動時に設定し、なお NG なら "外部プレーヤーで開く" ボタンを表示 |
| 自動再生 | **ウィンドウ起動という明示操作後のみ再生開始可**。選択変更・ホバーでは絶対に再生しない |
| 音 | **既定ミュート** |
| 設定 | 「動画プレーヤー機能の有効/無効」「既定の再生速度」「既定ミュート」（settings_dialog.py に追加） |

#### 長所 / 短所

- ✅ 右ペインを占有せず、ファイル一覧・サムネイル・履歴カードのレイアウトに影響しない。
- ✅ 認知科学視点での「能動的選択での深掘り」原則に合致。
- ✅ 既存の `[[feedback_hover_thumbnail_default]]`（オプトイン重視）の方針と整合。
- ✅ `QMediaPlayer` を常駐させないため、通常のファイル操作中の負荷を最小化できる。
- ⚠ 別ウィンドウのため、ファイラー内で完結する一体感は弱い。
- ⚠ ウィンドウ位置・サイズの保存や多重起動抑制が必要。

---

### 案 B: 連続プレビュー対応プレーヤー（中規模）

> 案 A の別ウィンドウを拡張し、動画フォルダの棚卸し向けに前後ファイルへ連続移動できるようにする。

#### 概要

- 案 A と同じ `VideoPlayerWidget` / `VideoPlayerWindow` を再利用する。
- プレーヤー内の「前/次」ボタン、または Ctrl+←/Ctrl+→ で同一フォルダ内の前後動画へ移動する。
- ファイル切替は 200ms デバウンスし、切替前に必ず `stop()` と `setSource(QUrl())` を実行する。
- 次動画へ移動した場合も既定ミュートを維持する。

#### スコープ

| 項目 | 内容 |
|---|---|
| 新規モジュール | 案 A のモジュールを拡張。必要なら `video_playlist.py` を追加 |
| 改修 | `file_manager.py`（同一フォルダ内の動画リスト提供）、`settings_dialog.py` |
| バックエンド | 案 A と同じ |

#### 長所 / 短所

- ✅ 視界を一時的に動画に集中させられる → 認知科学的に「短時間で内容把握」に向く。
- ✅ 連続選択 → 連続プレビューで「動画フォルダの棚卸し」が高速化。
- ✅ 右ペインを常時占有しないので、整理作業中は邪魔にならない。
- ⚠ 同一フォルダ内の動画列挙、ソート順同期、削除/移動済みファイルへの耐性が必要。

---

### 案 C: スクラブ + ホバー再生 ハイブリッド（大規模）

> 既存の「[スマートスクラブ・プレビュー](./video_scrub_preview_plan.md)」計画と統合し、**ホバーでスクラブ、クリックで再生**の YouTube/Plex 流ハイブリッドを実現する完全版。

#### 概要

- スマートスクラブ計画（PySceneDetect + FFmpeg）を先に or 並行で完了。
- 右ペインのプレビュー領域には再生 UI を置かず、次の段階的体験を提供:
  1. **選択直後**: 代表サムネ（シーン境界の 1 枚）表示。
  2. **ホバー**: シークバー上のマウス位置に対応した最寄りキーフレームを即時スナップ表示（スクラブ、**無音**）。
  3. **クリック**: その位置から別ウィンドウの `QMediaPlayer` で再生開始（既定ミュート）。
- スクラブ用キーフレーム抽出は既存計画通り FFmpeg I-frame seek、再生は QMediaPlayer。
- Animated WebP のループ再生（受動把握）は **完全に "オプトイン" 設定** にする（user memory: hover thumbnail default OFF の方針を継承）。

#### スコープ

| 項目 | 内容 |
|---|---|
| 新規モジュール | スクラブ計画分（`video_keyframes.py`, `scene_detection.py`, `video_scrub_preview.py`）+ 本案 (`video_player_widget.py`) |
| 改修 | `video_thumbnail_preview.py` のスクラブ対応、`file_manager.py`、`settings_dialog.py`、`requirements.txt`（`scenedetect>=0.6.7` 追加） |
| バックエンド | QMediaPlayer + FFmpeg シーク + OpenCV フォールバック |

#### 長所 / 短所

- ✅ プロ向けツール（DaVinci, Adobe Bridge, Plex）と同等の体験。
- ✅ 認知負荷の階層（概要 → スクラブ → 再生）が完璧に表現できる。
- ✅ 内容把握速度の理論的最大値。
- ⚠ 開発コストが最大（FFmpeg 同梱・PySceneDetect 導入・キャッシュ管理・大量のテスト）。
- ⚠ FFmpeg ランタイムの配布で `build_exe.py` 改修が必要。
- ⚠ ユーザが期待する「素朴な再生プレーヤー」を超えてしまう可能性。

---

## 5. 推奨方針

### 段階的アプローチ: 別ウィンドウ軽量プレーヤーを先に作る

| フェーズ | 内容 | 目安規模 | 期待効果 |
|---|---|---|---|
| **Phase 1（推奨即実装）** | 案 A: 別ウィンドウ軽量プレーヤー | 2 ファイル新規、2〜3 ファイル改修、追加依存なし | 右ペインを占有せず、最短で「再生しながら確認」を満たす |
| **Phase 2** | 案 B: 連続プレビュー対応 | 案 A の拡張 | フォルダ棚卸しタスクの効率化 |
| **Phase 3** | 案 C: スクラブプレビューと統合（既存 `video_scrub_preview_plan.md` をマージ） | 既存計画分を含む | プロ品質のプレビュー体験 |

### Phase 1 の軽量化条件

- ファイラー起動時・ファイル選択時には `QMediaPlayer` を生成しない。
- プレーヤーウィンドウを開いた時だけ `QMediaPlayer` / `QAudioOutput` / `QVideoWidget` を生成する。
- 同時再生は 1 本だけに制限し、既存ウィンドウがある場合は新規作成せず同じウィンドウへ動画を読み込む。
- ウィンドウを閉じる時は `stop()`、`setSource(QUrl())`、`deleteLater()` を順に行い、動画ファイルのロックとメモリ常駐を避ける。
- Phase 1 ではホバー再生、スクラブ用キーフレーム生成、PySceneDetect 導入、FFmpeg dll 同梱を行わない。

### 全フェーズ共通の設計原則（議論からの合意事項）

1. **選択変更・ホバーによる自動再生は禁止**。再生は Space/メニュー/ボタンで別ウィンドウを開いた後だけ行う
2. **既定ミュート、アンミュートは明示操作後のみ**
3. **再生速度 1.0/1.5/2.0x を必ず提供**（HCI 研究で内容把握の効率が向上）
4. **`errorOccurred` を必ずハンドル**して、再生不可ファイルは「外部プレーヤーで開く」ボタンに切り替える
5. **`QT_MEDIA_BACKEND=ffmpeg` を `__init__.py` で設定**し、HEVC など Windows 標準で再生不能な MP4 を救う
6. **キーバインド**: Space=Play/Pause, ←/→=±5s, M=Mute, F=Fullscreen, Esc=Close
7. **同時に存在する `QMediaPlayer` は 1 個だけ**。ウィンドウを閉じたら即解放する
8. **設定でプレーヤー機能の有効/無効を切替可能**（`QSettings("FileManager", "Settings")` に追加）
9. **右ペイン・`bento_grid` には再生 UI を追加しない**

---

## 6. リスクと対策

| リスク | 対策 |
|---|---|
| Windows でコーデック不足により再生不能 | `QT_MEDIA_BACKEND=ffmpeg` を強制 → それでも NG なら "外部プレーヤーで開く" にフォールバック |
| QMediaPlayer が無音失敗（silent failure） | `errorOccurred` シグナルを必ず接続、ユーザに通知 |
| 大容量動画のロード遅延 | 別ウィンドウ内にロード中表示を出し、ファイラー本体はブロックしない |
| PyInstaller exe のサイズ増 | Qt Multimedia plugin 同梱の最小セット選別、FFmpeg dll は必要最小限 |
| 連続ファイル切替でクラッシュ | Phase 2 以降のみ対象。切替前に `stop()` / `setSource(QUrl())`、さらに `QTimer` 200ms でデバウンス |
| 自動再生による不快感 | 選択変更・ホバーでは再生しない。別ウィンドウ起動後も既定ミュート |
| ファイラー本体のメモリ常駐増 | `QMediaPlayer` / `QAudioOutput` / `QVideoWidget` を別ウィンドウ内で遅延生成し、閉じたら破棄 |
| 認知負荷増（複数 UI 同時更新） | 再生中は他の自動更新（履歴・ストレージ容量）の更新を抑制 |

---

## 7. 開かれた決定事項（次にユーザに確認したいこと）

1. **別ウィンドウの起動キーは Space でよいか?**（macOS QuickLook 風。Enter は既存の開く操作と衝突しやすい）
2. **別ウィンドウ起動後に自動で再生開始するか?**（推奨: 起動操作を明示操作とみなし、ミュートで再生開始）
3. **ウィンドウ位置・サイズを保存するか?**（推奨: 保存する）
4. **FFmpeg dll 同梱の許可**（exe サイズが約 30〜50MB 増加見込み。Phase 1 では Qt 同梱範囲から開始）
5. **設定既定値**: プレーヤー有効/無効、既定再生速度、既定ミュート

---

## 8. 参考文献・調査ソース

### PySide6 / Qt Multimedia
- [QMediaPlayer — Qt for Python](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QMediaPlayer.html)
- [QVideoWidget — Qt for Python](https://doc.qt.io/qtforpython-6/PySide6/QtMultimediaWidgets/QVideoWidget.html)
- [Player Example — Qt for Python](https://doc.qt.io/qtforpython-6/examples/example_multimedia_player.html)
- [Qt Multimedia in Qt 6](https://www.qt.io/blog/qt-multimedia-in-qt-6)
- [QMediaFormat — Qt for Python](https://doc.qt.io/qtforpython-6/PySide6/QtMultimedia/QMediaFormat.html)
- [How to test ffmpeg in PySide 6.4? — Qt Forum](https://forum.qt.io/topic/140448/how-to-test-ffmpeg-in-pyside-6-4)
- [PySide6 QMediaPlayer do not play all mp4 — Qt Forum](https://forum.qt.io/topic/131818/pyside6-qmediaplayer-do-not-play-all-mp4)
- [Fix QMediaPlayer Wrong Duration on Windows — PythonGUIs](https://www.pythonguis.com/faq/is-it-just-me-or-is-qmediaplayer-not-working-properly/)
- [BBC-Esq/Pyside6_PyQt6_video_audio_player（python-vlc 参考実装）](https://github.com/BBC-Esq/Pyside6_PyQt6_video_audio_player)
- [Building a PyQt6 Video Player with VLC — CodersLegacy](https://coderslegacy.com/building-a-pyqt6-video-player-with-vlc/)

### UX / デザインパターン
- [Adobe Bridge: Preview dynamic media files](https://helpx.adobe.com/bridge/using/preview-dynamic-media-files-adobe.html)
- [WWDC19: What's New in File Management and Quick Look](https://developer.apple.com/videos/play/wwdc2019/719/)
- [Windows 11 File Explorer Preview Pane (NinjaOne)](https://www.ninjaone.com/blog/show-or-hide-the-preview-pane-in-file-explorer-in-windows-11/)
- [Adobe Bridge: hover scrub 解説](https://taylorhieber.co/video-thumbnail-preview-thumbnail-scrubbing-on-hover-in-adobe-bridge/)
- [Mux: Create timeline hover previews](https://www.mux.com/docs/guides/create-timeline-hover-previews)
- [Mux: Storyboards and Trick Play](https://www.mux.com/blog/tricky-storyboards-and-trick-play)
- [VLC keyboard shortcuts](https://www.vlchelp.com/vlc-media-player-shortcuts/)
- [Jellyfin: Show video preview on thumbnail hover (feature request)](https://features.jellyfin.org/posts/139/show-video-preview-on-thumbnail-hover)

### 認知科学 / HCI 研究
- [Video Skimming: Taxonomy and Comprehensive Survey (ACM Comp Surveys 2019)](https://dl.acm.org/doi/10.1145/3347712)
- [Swifter: Improved Online Video Scrubbing (Autodesk Research)](https://www.research.autodesk.com/app/uploads/2023/03/swifter-improved-online-video.pdf_rec46kl91LgCROmKf.pdf)
- [Exploring the Role of Video Playback Visual Cues in Object Retrieval Tasks (PMC 11125056)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11125056/)
- [Toward Human Perception-Centric Video Thumbnail Generation (ACM MM 2023)](https://dl.acm.org/doi/10.1145/3581783.3612434)
- [Minimize Cognitive Load to Maximize Usability — Nielsen Norman Group](https://www.nngroup.com/articles/minimize-cognitive-load/)
- [A Systematic Study on Video Summarization (ACM 2023)](https://dl.acm.org/doi/10.1145/3607540.3617139)
- [Personalized Video Summarization Survey (MDPI 2024)](https://www.mdpi.com/2076-3417/14/11/4400)

### Windows Explorer プレビューペインの実例調査
- [File Explorer Preview Pane in Windows 10 is lagging — Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/3840732/file-explorer-preview-pane-in-windows-10-is-laggin)
- [Preview Pane Slow to Load in Windows 11 Pro — Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/4283166/preview-pane-slow-to-load-in-windows-11-pro)

---

## 9. 次のアクション

ユーザ確認後、Phase 1（別ウィンドウ軽量プレーヤー）着手:

1. `src/file_manager/video_player_widget.py` の新規実装
2. `src/file_manager/video_player_window.py` の新規実装（別ウィンドウ、位置/サイズ保存、多重起動抑制）
3. `src/file_manager/file_manager.py` に Space ショートカット、ツールバー/コンテキストメニュー、選択動画パスの受け渡しを追加
4. `src/file_manager/settings_dialog.py` に有効/無効・既定速度・既定ミュートの設定追加
5. `src/file_manager/__init__.py` で `QT_MEDIA_BACKEND` 環境変数の設定
6. `tests/test_video_player_widget.py` / `tests/test_video_player_window.py` 新規（既存の軽量 `qtbot` を利用し、`QMediaPlayer` は可能な範囲でモック）
7. 既存テスト regress 確認
