# 動画内容ベースのマルチラベル・クラスタリング機能 調査検討

最終更新: 2026-05-16
状態: CV/ML 専門家・LLM/VLM 専門家の検討結果を統合
関連: `docs/video_scrub_preview_plan.md`

## 0. 結論

特定フォルダ以下の動画を、サムネイルやキーフレーム、必要に応じて音声・字幕から解析し、内容ベースでクラスタリングすることは実装可能です。

ただし、クラスタを「排他的な分類先」として扱うと長尺動画や複合内容の動画で破綻しやすいため、内部モデルは **動画・シーン・フレームを単位にした多対多のタグ/クラスタ所属** として設計するのが妥当です。

推奨方針は以下です。

| レイヤ | 目的 | 推奨 |
|---|---|---|
| L1 埋め込み | 類似検索、近傍探索、クラスタ発見 | SigLIP 2 / CLIP 系画像埋め込み |
| L2 タグ生成 | ユーザーに見せる可読タグ | RAM++ または VLM による JSON タグ |
| L3 構造発見 | 未知のグルーピング検出 | UMAP + HDBSCAN、または近傍グラフ |
| UI | 可視化・修正 | タグチップ、類似動画一覧、クラスタサムネイル、後段で 2D マップ |

最初から高精度 VLM 前提にすると重くなりすぎるため、MVP は **キーフレーム抽出 + 画像埋め込み + 類似動画表示 + 仮クラスタ** から始め、シーン単位・HDBSCAN・VLMタグ・音声解析を段階導入するのが最も成功率が高いです。

## 1. 専門家レビューの要点

### 1.1 CV/ML 専門家の見解

動画を直接 1 本のラベルへ分類するのではなく、まずシーン・キーフレーム・フレーム特徴へ分解し、複数粒度の埋め込みを保持するべきです。

推奨される処理パイプライン:

```text
動画ファイル
  -> メタデータ抽出
  -> シーン分割または等間隔キーフレーム抽出
  -> 画像 embedding 生成
  -> frame / scene / video 単位で保存
  -> 近傍検索 index 作成
  -> クラスタリング / タグ集約
  -> PySide6 UI で可視化
```

重要な設計判断:

- 1 動画を 1 ベクトルだけに潰すと、複数内容を含む動画を扱いにくい
- MVP は平均 pooling の動画ベクトルでよいが、早期に `scene_embedding` を保存できる設計にする
- クラスタリングは `video` 単位ではなく `scene` 単位で行い、UI 表示時に `video` へ集約するとマルチラベル化しやすい
- クラスタ ID だけではユーザーに意味が伝わらないため、代表サムネイル・代表タグ・ユーザー編集名を持たせる

### 1.2 LLM/VLM 専門家の見解

VLM はクラスタリングそのものより、クラスタや動画に人間可読なタグ・説明を付ける用途に向いています。

推奨される使い方:

- 動画ファイルを直接渡すより、代表フレーム 8〜32 枚を抽出して複数画像として渡す
- 長尺動画は 5 分単位、または一定数のシーン単位でチャンク化する
- VLM 出力は自由文ではなく JSON Schema / Pydantic で検証する
- タグは `raw_tag` と `canonical_tag` を分け、同義語統合層を置く
- クラウド VLM は明示的 opt-in に限定し、デフォルトは完全ローカルにする

VLM 出力例:

```json
{
  "summary": "室内で人物が料理をしている短い動画",
  "tags": [
    {
      "canonical": "料理",
      "aliases": ["調理", "クッキング"],
      "category": "activity",
      "confidence": 0.86,
      "evidence": [
        {"timestamp_sec": 12.4, "note": "まな板と食材が見える"}
      ]
    }
  ],
  "objects": ["包丁", "まな板", "野菜"],
  "places": ["キッチン"],
  "actions": ["切る", "混ぜる"],
  "sensitive": {
    "contains_faces": true,
    "contains_children": false,
    "contains_documents": false,
    "contains_screen_text": false
  },
  "uncertain": ["料理名は特定不可"]
}
```

## 2. 推奨アーキテクチャ

```text
Stage 0: 動画列挙・メタデータ取得
  - path, size, mtime, duration, width, height, fps
  - 変更検知用に size / mtime / partial hash を保存

Stage 1: キーフレーム抽出
  - MVP: 等間隔で 4〜8 枚
  - 改善版: PySceneDetect でシーン分割し、各シーンから代表フレーム
  - 既存の video_scrub_preview_plan.md の抽出処理と共用する

Stage 2: 埋め込み生成
  - frame_embedding: 各キーフレーム
  - scene_embedding: シーン内フレームの平均または中央値
  - video_embedding: scene/frame embedding の平均または重み付き平均

Stage 3: 類似検索・クラスタリング
  - 小規模: NumPy cosine 類似度
  - 中規模以上: hnswlib
  - クラスタ: K-Means / Agglomerative から開始し、HDBSCAN へ拡張

Stage 4: タグ付け
  - Zero-shot 類似度、RAM++、VLM、音声/字幕からタグ候補を生成
  - raw tag を canonical tag に正規化
  - ユーザー修正を保持

Stage 5: UI 表示
  - タグチップ
  - 類似動画一覧
  - クラスタ代表サムネイル
  - 後段で UMAP 2D マップ
```

### 2.1 多重所属を前提にした内部モデル

クラスタはフォルダのような排他的分類ではなく、タグに近い扱いにします。

内部的には次の関係を持たせます。

```text
video -> frame[]
video -> scene[]
video -> tag[]
video -> cluster[]
scene -> tag[]
scene -> cluster[]
video -> neighbor[]
```

これにより、1 本の動画に「料理」「人物」「屋内」「夜」「旅行」のような複数タグを付けられます。長尺動画では、前半がゲーム画面、後半が会話、というような内容混在も扱えます。

## 3. モデル・特徴量の候補

### 3.1 埋め込みモデル

| 候補 | 用途 | 評価 |
|---|---|---|
| SigLIP 2 | 画像・テキスト類似、ゼロショット、類似検索 | 第一候補。多言語・画像検索に強い |
| OpenCLIP / CLIP | 画像埋め込み、テキスト検索 | 実装例が多く MVP 向き |
| DINOv2/DINOv3 系 | 視覚類似・重複に強い | テキスト検索には不向き |
| ONNX 化 CLIP 系 | 配布・CPU 推論 | Windows アプリ化で有利 |

既存文書では SigLIP 2 を推奨しており、方向性は妥当です。一方で Python 3.13 / Windows では ML パッケージの wheel 対応が実装リスクになるため、モデル層は差し替え可能にしておくべきです。

MVP では以下の順に現実的です。

1. OpenCLIP または SigLIP 2 で画像埋め込み
2. CPU/ONNX Runtime への差し替え口を用意
3. GPU がある場合だけ PyTorch 高速推論を使う

### 3.2 軽量特徴量

画像埋め込みだけでなく、軽量特徴量も保存しておくと UI とフィルタに効きます。

- 動画長
- 解像度、fps
- 平均輝度、平均彩度
- 色ヒストグラム
- サムネイルの暗さ/明るさ
- スクリーン録画らしさ
- 顔・人物・文字の有無

「暗い動画」「白背景」「講義スライド」「ゲーム画面」などは軽量特徴だけでも補助分類できます。

### 3.3 VLM / LLM

VLM は高価なので、全件必須にはしません。

| モード | 内容 | 想定 |
|---|---|---|
| 軽量 | 画像埋め込み + Zero-shot / RAM++ | CPU でも実用 |
| 標準 | 外れ値・代表クラスタのみ VLM | GPU または高速ローカル VLM |
| 高精度 | 全件 VLM + 音声/字幕 | 時間がかかるがタグ品質が高い |
| クラウド | Gemini/OpenAI 等を opt-in | プライバシー確認必須 |

Ollama や LM Studio のようなローカルサーバーを抽象化すると、モデルの差し替えがしやすくなります。

## 4. クラスタリング方式

### 4.1 MVP

最初は以下で十分です。

- `video_embedding = frame_embedding の平均`
- cosine 類似度で top-k 類似動画を表示
- K-Means または Agglomerative Clustering で仮クラスタ
- クラスタ名はユーザー編集可能

この段階で「似た動画がまとまるか」「UI として有用か」を検証できます。

### 4.2 本命構成

本格版では HDBSCAN を採用します。

HDBSCAN が向いている理由:

- クラスタ数を事前に決めなくてよい
- ノイズを扱える
- 所属確率を扱える
- `scene_embedding` 単位でクラスタリングすれば、1 動画が複数クラスタに属せる

推奨方針:

```python
umap.UMAP(
    n_components=10,
    n_neighbors=30,
    min_dist=0.0,
    metric="cosine",
)

hdbscan.HDBSCAN(
    min_cluster_size=5,
    min_samples=3,
    cluster_selection_method="eom",
    prediction_data=True,
)
```

2D 表示用の UMAP とクラスタリング用の UMAP は分けます。クラスタリングは 10D 程度、可視化は 2D が適切です。

### 4.3 近傍グラフ

クラスタリングとは別に、類似動画検索用の近傍グラフを持つと UI で使いやすいです。

- 〜5,000 動画: NumPy brute force でも現実的
- 5,000〜100,000 embedding: hnswlib が軽量で扱いやすい
- さらに大規模: FAISS も候補

このアプリの規模では、まず hnswlib を第一候補にします。

## 5. タグ設計

### 5.1 タグの出所

タグは出所を分けて保存します。

| source | 内容 |
|---|---|
| `visual_embedding` | CLIP/SigLIP のゼロショット推定 |
| `ram` | RAM++ などの画像タグモデル |
| `vlm` | VLM の構造化出力 |
| `audio` | Whisper 等の文字起こし |
| `subtitle` | `.srt`, `.vtt`, `.ass` |
| `filename` | ファイル名・フォルダ名 |
| `manual` | ユーザー確定タグ |
| `cluster` | 自動クラスタ名 |

UI では「推定タグ」と「ユーザー確定タグ」を分けます。自動タグは誤る前提で、ユーザー修正を第一級データとして扱います。

### 5.2 同義語統合

VLM や音声解析では表記揺れが必ず発生します。

例:

- 車 / 自動車 / 乗用車
- 料理 / 調理 / クッキング
- ゲーム実況 / gameplay / playthrough

推奨する正規化手順:

1. 文字正規化: 大文字小文字、全半角、記号、単複
2. 手動辞書: `synonym_map`
3. 埋め込み類似度: 近いタグ候補を提示
4. ローカル LLM: opt-in で候補統合
5. ユーザー確定: 破壊的な統合は確認制

保存項目:

```text
raw_tag
canonical_tag
aliases
category
source
confidence
confirmed_by_user
```

## 6. 音声・字幕・OCR の扱い

映像だけでは話題を取り逃がします。特にゲーム実況、講義、レビュー動画、会議録画では音声・字幕が重要です。

推奨:

- 音声: faster-whisper / whisper.cpp でローカル文字起こし
- 字幕: `.srt`, `.vtt`, `.ass` を解析
- OCR: 画面内文字やスライドタイトルを抽出
- ファイル名: 弱教師としてタグ候補に使う

統合方針:

- 映像由来タグは「見た目」
- 音声・字幕由来タグは「話題」
- 固有名詞は音声/字幕由来の価値が高い
- 文字起こし全文の保存はオプションにする

## 7. データスキーマ案

SQLite で開始できます。後で hnswlib index を別ファイルとして保存します。

```sql
CREATE TABLE videos (
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE NOT NULL,
  size INTEGER,
  mtime REAL,
  partial_sha1 TEXT,
  duration REAL,
  width INTEGER,
  height INTEGER,
  fps REAL,
  scanned_at REAL
);

CREATE TABLE frames (
  id INTEGER PRIMARY KEY,
  video_id INTEGER NOT NULL,
  scene_id INTEGER,
  timestamp REAL,
  thumbnail_path TEXT
);

CREATE TABLE embeddings (
  id INTEGER PRIMARY KEY,
  owner_type TEXT NOT NULL,      -- video / scene / frame / text
  owner_id INTEGER NOT NULL,
  model_name TEXT NOT NULL,
  model_version TEXT,
  dim INTEGER NOT NULL,
  vector BLOB NOT NULL
);

CREATE TABLE tags (
  id INTEGER PRIMARY KEY,
  canonical_tag TEXT NOT NULL,
  category TEXT,
  UNIQUE(canonical_tag, category)
);

CREATE TABLE video_tags (
  video_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  raw_tag TEXT,
  score REAL,
  source TEXT NOT NULL,
  confirmed_by_user INTEGER DEFAULT 0,
  PRIMARY KEY (video_id, tag_id, source)
);

CREATE TABLE clusters (
  id INTEGER PRIMARY KEY,
  method TEXT NOT NULL,
  model_name TEXT,
  params_json TEXT,
  label TEXT,
  representative_video_id INTEGER,
  created_at REAL
);

CREATE TABLE cluster_members (
  cluster_id INTEGER NOT NULL,
  owner_type TEXT NOT NULL,      -- video / scene
  owner_id INTEGER NOT NULL,
  score REAL,
  PRIMARY KEY (cluster_id, owner_type, owner_id)
);
```

ポイント:

- embedding は `owner_type` で `video / scene / frame` を共通化する
- モデル名とバージョンを保存し、モデル更新時に再計算できるようにする
- `cluster_members` を多対多にし、1 動画の複数クラスタ所属を許容する

## 8. UI/UX 案

### 8.1 初期実装で有用な画面

- フォルダスキャン進捗
- 解析キューとキャンセル
- 類似動画一覧
- クラスタ別サムネイルグリッド
- タグフィルタ
- ファイル一覧上のタグチップ
- 1 動画の所属クラスタ、推定タグ、近傍動画
- タグ修正、クラスタ名変更、解析対象から除外

### 8.2 2D マップ

UMAP 2D + `QGraphicsView` の散布図は有用ですが、MVP 必須ではありません。まずはクラスタサムネイルグリッドと類似動画一覧の方が実用価値が高いです。

追加する場合:

- サムネイルをクラスタ色付きで配置
- ドラッグで範囲選択
- ダブルクリックで動画選択
- ホイールズーム
- クラスタ/タグで絞り込み

### 8.3 タグフィルタ例

```text
▼ タグ
  □ 料理 (42)
  □ 人物 (37)
  □ 屋内 (51)
  □ ゲーム画面 (18)
  □ 講義・スライド (9)
  ─────────────────
  ▼ 自動クラスタ
    □ cluster_07: 夜景 + 音楽 (8)
    □ cluster_12: 料理動画 (5)
```

## 9. プライバシー設計

デフォルトは完全ローカル処理にします。

必須方針:

- 動画、フレーム、音声、字幕をデフォルトで外部送信しない
- クラウド解析はファイル単位・処理単位で明示的 opt-in
- 送信前に対象データのプレビューを表示
- 一時フレーム、抽出音声、文字起こしの保存期間を設定可能にする
- 顔、子ども、書類、画面共有、ナンバープレート等を sensitive タグとして扱う
- 元動画のコピーは DB に保存しない
- 解析結果の削除・再スキャンを UI から可能にする

クラウド利用時は、プロバイダ名、送信内容、API キー管理場所、保持ポリシーを UI に明示します。

## 10. 評価指標

教師ラベルがない前提なので、内部指標とユーザー評価を併用します。

内部指標:

- silhouette score
- Davies-Bouldin index
- Calinski-Harabasz index
- 近傍検索の再現率
- クラスタ安定性
- 重複候補の precision

ユーザー評価:

- 似た動画 top-k の適合率
- 推定タグの採用率
- クラスタ名の手修正回数
- クラスタ分割/統合の回数
- 「意味のあるクラスタ」と判断された割合

注意点:

- silhouette score だけで品質判断しない
- embedding 空間で良いクラスタと、ユーザーに便利な分類は一致しない場合がある
- UI 上の修正履歴を評価データとして蓄積する

## 11. 実装ロードマップ

### Phase 1: 最小実装

- 対象フォルダから動画を列挙
- ffmpeg / OpenCV / PyAV で等間隔キーフレーム抽出
- サムネイル生成
- CLIP/SigLIP 系の画像埋め込み生成
- SQLite にキャッシュ
- cosine 類似度で似た動画 top-k を表示

成功条件:

- 1 動画を選ぶと類似動画が妥当に並ぶ
- 再スキャン時に未変更動画をスキップできる
- UI が固まらずバックグラウンド処理できる

### Phase 2: 仮クラスタとタグ UI

- video embedding 平均で K-Means / Agglomerative を実装
- クラスタごとの代表サムネイルを表示
- クラスタ名をユーザー編集可能にする
- `video_tags` / `cluster_members` を多対多で保存
- タグチップとタグフィルタを追加

成功条件:

- 同じ種類の動画がある程度まとまる
- 動画が複数タグを持てる
- ユーザー修正を保持できる

### Phase 3: シーン単位対応

- PySceneDetect でシーン分割
- `scene_embedding` を保存
- scene 単位クラスタから video へタグ集約
- 長尺動画・混在動画の分類精度を改善

成功条件:

- 1 本の動画に複数内容タグが付く
- 長い動画でも代表性が改善する

### Phase 4: 本格クラスタリング・高速化

- hnswlib による近傍検索
- UMAP(10D) + HDBSCAN によるクラスタ発見
- soft membership を `cluster_members.score` として保存
- videohash 等による重複・近似動画検出
- 2D マップビューを追加

### Phase 5: VLM・音声・高度タグ

- Ollama / LM Studio 経由のローカル VLM
- JSON Schema / Pydantic による構造化出力
- faster-whisper による音声タグ
- 字幕・OCR タグ
- クラウド VLM の opt-in 高精度モード

## 12. 実装リスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| Python 3.13 / Windows で ML wheel が不安定 | インストール失敗 | モデル層を差し替え可能にし、ONNX Runtime も候補にする |
| GPU なし環境で VLM が遅い | 高精度タグが非実用 | 軽量モードをデフォルトにする |
| 大量動画で UI が固まる | UX 悪化 | QThreadPool / worker / cancel flag を必須にする |
| 自動タグが誤る | 信頼性低下 | 推定タグと確定タグを分ける |
| 同義語統合ミス | タグ体系が壊れる | 自動統合は候補提示に留め、確定はユーザー確認 |
| 文字起こしに個人情報が含まれる | プライバシーリスク | 全文保存はオプション、一時ファイル削除設定を用意 |
| クラスタ名が分かりにくい | UI で使われない | 代表サムネイル表示とユーザー編集名を優先 |
| モデル更新で埋め込み互換性が消える | キャッシュ不整合 | `model_name` / `model_version` で invalidation |

## 13. requirements 追加候補

MVP と拡張で分けて導入します。

```text
# MVP
pillow>=10.0
numpy
scikit-learn>=1.5
av

# 画像埋め込み
torch>=2.4
transformers>=4.49
open_clip_torch>=2.32
onnxruntime>=1.20

# シーン検出
scenedetect[opencv]>=0.6.7

# クラスタリング・近傍探索
umap-learn>=0.5.7
hdbscan>=0.8.40
hnswlib>=0.8.0

# タグ生成・構造化出力
pydantic>=2.5
ollama>=0.4.0

# 音声
faster-whisper>=1.1

# 重複検出
videohash
```

Python 3.13 では各パッケージの wheel 対応を確認してから導入します。特に `torch`, `hdbscan`, `hnswlib`, `av` は Windows 環境で事前検証が必要です。

## 14. 推奨 MVP 結論

最初に実装する価値が高い順序は以下です。

1. キーフレーム抽出
2. CLIP/SigLIP 系画像埋め込み
3. 動画単位平均 embedding
4. cosine 類似検索
5. サムネイルグリッドで類似動画表示
6. K-Means / Agglomerative で仮クラスタ
7. タグチップとタグフィルタ
8. 後から scene embedding + HDBSCAN + VLM タグへ拡張

この順序なら、ローカルファイルマネージャとして早期に価値を出しつつ、将来的に複数クラスタ所属、テキスト検索、重複検出、音声・字幕タグへ自然に拡張できます。

## 15. 参考資料

### 埋め込み・画像モデル

- [OpenAI CLIP](https://github.com/openai/CLIP)
- [mlfoundations/open_clip](https://github.com/mlfoundations/open_clip)
- [SigLIP 2 paper](https://arxiv.org/html/2502.14786v1)
- [google/siglip2-base-patch16-naflex](https://huggingface.co/google/siglip2-base-patch16-naflex)

### 動画処理

- [PySceneDetect CLI](https://www.scenedetect.com/docs/head/cli.html)
- [PySceneDetect API](https://www.scenedetect.com/api/)

### クラスタリング・近傍探索

- [HDBSCAN soft clustering](https://hdbscan.readthedocs.io/en/latest/soft_clustering_explanation.html)
- [UMAP clustering guide](https://umap-learn.readthedocs.io/en/latest/clustering.html)
- [hnswlib](https://github.com/nmslib/hnswlib)
- [FAISS](https://faiss.ai/)
- [scikit-learn silhouette score](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html)

### VLM / 構造化出力

- [Ollama Vision](https://docs.ollama.com/capabilities/vision)
- [LM Studio Structured Output](https://lmstudio.ai/docs/app/api/structured-output)
- [Qwen2.5-VL Technical Report](https://arxiv.org/abs/2502.13923)
- [LLaVA-NeXT Video](https://github.com/LLaVA-VL/LLaVA-NeXT/blob/main/docs/LLaVA-NeXT-Video.md)

### 音声・重複検出

- [Whisper](https://github.com/openai/whisper)
- [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)
- [videohash](https://github.com/akamhy/videohash)
