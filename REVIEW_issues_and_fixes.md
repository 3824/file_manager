## 概要

このドキュメントはリポジトリ内のコードレビューに基づき、現状で確認した不具合・改善ポイントと具体的な改修方針をまとめたものです。まずは優先度の高い項目（設定ダイアログのクラッシュ、類似動画検出の遅さ）を中心に対処案を提示します。

## 発見した主な不具合 / 改善ポイント（抜粋）

- SettingsDialog を `OK` (accept) で閉じるとアプリがクラッシュするケース
  - 発生箇所: `src/file_manager/file_manager.py` の `SettingsDialog` 周り（`accept` 実装や親ウィジェットへのアクセス時）
  - 問題: 親ウィジェットが `None`、または期待する属性を持たない場合に例外が発生している。

- 類似（重複）動画検出が遅い
  - 発生箇所: `src/file_manager/video_duplicates.py` / `video_duplicates_dialog.py`
  - 問題: 全ファイルを順次フルハッシュして比較する実装だと大容量フォルダで非常に遅くなる。

- 設定・環境依存の import（例: `winshell`）が存在し、未インストール時にクラッシュする箇所
  - 発生箇所: `src/file_manager/file_manager.py` のゴミ箱操作周り

- 動画ダイジェストダイアログ、ディスク分析スレッド等で親やスレッド参照が None の時に cleanup/close で落ちる
  - 発生箇所: `video_digest_dialog.py`, `disk_analysis_dialog.py`, `file_manager.py` の LeftPaneWidget 等

- ファイル一覧チェックボックスの選択が効かない / 編集トリガーが不足
  - 発生箇所: `CustomFileSystemModel.flags` / `setData`、および `list_view` の editTriggers

（注）上記のうち、チェックボックスの修正や一部の None ガード処理は既にパッチを適用済みです。残りは優先度順に対応を推奨します。

## 優先対応: `SettingsDialog` のクラッシュ防止

目的: 設定ダイアログで `OK` を押したときに、親ウィジェットが None または期待するメソッド/属性を持たなくても例外を発生させず、設定保存と UI 更新を安全に行う。

具体的改修案:

- `SettingsDialog.accept` / `_apply_settings` 内で親に対する直接呼び出しを行う前に厳密にチェックする
  - 例: `if hasattr(self.parent(), 'update_visible_columns'):` で存在確認してから呼ぶ
  - 更に try/except で保護し、失敗してもユーザーには最小限のエラーメッセージを出すかログに残して処理を継続する

- QSettings の保存は必ず成功するように `sync()` を呼び、ファイルIOでの例外は捕捉してエラーハンドリングする

- ダイアログの accept() は保存処理が致命的失敗でない限り呼び出す（UI が固まるよりは保存失敗を通知して閉じる方が安全）

推奨パッチ（要点）:

- `src/file_manager/file_manager.py` の `SettingsDialog.accept`:
  - 親呼び出しを try/except でラップ
  - `self.settings.sync()` を明示
  - `_show_save_success_message` の呼び出しも `try/except` で保護

テスト案:

- `tests/test_features.py` に「親が None の時にも accept が例外を投げない」ユニットテストを追加
- QSettings を一時ディレクトリに向けることで保存例外ケースもシミュレート可能

## 優先対応: 類似動画（重複）検出の高速化

目的: 大量ファイル・大容量ファイルを扱った際の検出時間を現実的な範囲に短縮する。

改善方針（段階的）:

1. フィルタリング（早期除外）
   - サイズでグループ化: サイズが異なるファイルは重複にならないため最初にバケット分け
   - 拡張子や拡張子のないファイルの扱いをオプション化

2. サンプリングハッシュ（多段ハッシュ）
   - まず先頭と末尾など数か所の固定長バイト列をハッシュ（または軽量なチェックサム）して候補を絞る
   - 候補グループのみで完全ハッシュ（SHA256, BLAKE2）を行う

3. チャンク / ストリーム処理 & 並列化
   - ファイルをメモリに全部読み込まずにチャンク単位でハッシュ
   - CPU と I/O を考慮したスレッド/プロセスプールで並列処理（`concurrent.futures.ThreadPoolExecutor` や `ProcessPoolExecutor`）

4. 高速ハッシュライブラリの検討（オプション）
   - `xxhash` や `blake3` などを導入すると大幅に高速化可能（ただし追加依存）

5. 進捗・キャンセル性の改善
   - `progress_callback` を細かく呼び出し、UI 側で早めに反映
   - `stop_callback` を頻繁にチェックしてキャンセルを即時反映

具体的修正箇所:

- `src/file_manager/video_duplicates.py`:
  - `find_duplicate_videos` を上記アルゴリズムに合わせてリファクタ
  - `progress_callback`, `stop_callback` の呼び出しポイントを追加

- `src/file_manager/video_duplicates_dialog.py`:
  - Worker 側でキャンセルフラグの共有、進捗粒度の改善
  - UI 側で「高速モード（サンプリングのみ）」などオプションを追加

ベンチマーク / テスト案:

- 小中規模（数百ファイル, 合計数GB 程度）での実行時間を測定するベンチテスト（pytest ベース）
- `stop_callback` の動作確認ユニットテスト（早期停止できること）

## その他の改善候補（簡潔）

- 外部依存の import ガード
  - `winshell` 等は ImportError を捕まえてフォールバックを用意する（既に一部対応済み）

- スレッド/ワーカーの安全なクリーンアップ
  - `cleanup_worker()` で `None` チェックや `isRunning()` 存在チェックを追加済みだが、全 Worker に対して統一的なユーティリティ関数を用意すると安全性が上がる

- GUI レスポンス改善
  - 長時間処理は必ず非同期化し、UI 側ではキャンセル/進捗を明示

- ログ出力の整備
  - try/except で握る箇所は最低限ログを残す（開発時は DEBUG レベルでスタックトレース）

## 契約（小さな仕様）

- 入力: ユーザーの操作（設定変更、重複検出開始）、任意のフォルダパス
- 出力: 設定が QSettings に安全に保存されること、重複検出がタイムアウト/キャンセル可能であること
- エラーモード: 親が None、外部モジュールが存在しない、IO エラー等は UI をクラッシュさせない。ユーザーへは非侵襲的に通知（ダイアログやステータスバー）する。

## 優先度と次の作業（推奨）

1. SettingsDialog.accept の堅牢化（高） — 単一パッチで完了可能
2. find_duplicate_videos の多段ハッシュ化＋並列化（高） — リファクタとベンチが必要
3. Worker のクリーンアップと None ガードの整理（中）
4. 外部依存のフォールバック整理とログ強化（中）
5. テスト追加（unit + integration）（高）

## 参考：実装イメージ（小さなコードスニペット）

- SettingsDialog.accept の要点（擬似コード）

```py
try:
    # QSettings に保存
    self.settings.setValue(...)
    self.settings.sync()
except Exception:
    # ログ出力
    print('設定の保存に失敗しました')

# 親へ反映する場合は存在チェック
parent = self.parent()
if parent is not None and hasattr(parent, 'update_visible_columns'):
    try:
        parent.update_visible_columns(visible_columns)
    except Exception:
        print('親ウィジェットへの反映に失敗しました')

self.accept()
```

## 次に私ができること

- ご希望なら `SettingsDialog.accept` の保護パッチを作成して適用します。また、`find_duplicate_videos` のプロトタイプ実装（サンプリング→完全ハッシュの流れ）を作ってベンチを回せます。どちらを先に進めますか？
