# ツールバー設定：利用可能なアイテム一覧
TOOLBAR_ALL_ITEMS = [
    {"id": "up",           "label": "↑ 上へ"},
    {"id": "refresh",      "label": "↻ 更新"},
    {"id": "copy",         "label": "📋 コピー"},
    {"id": "cut",          "label": "✂ 切り取り"},
    {"id": "paste",        "label": "📌 貼り付け"},
    {"id": "delete",       "label": "🗑 削除"},
    {"id": "rename",       "label": "✏ 名前変更"},
    {"id": "new_folder",   "label": "📁 新規フォルダ"},
    {"id": "view_mode",    "label": "□ 表示モード"},
    {"id": "sort",         "label": "↕ ソート"},
    {"id": "search_box",   "label": "🔎 検索ボックス"},
    {"id": "foreign_filter","label": "外国語名フィルター"},
    {"id": "search",       "label": "🔍 ファイル検索"},
    {"id": "hidden",       "label": "👁 隠しファイル"},
    {"id": "disk_analysis","label": "📊 ディスク分析"},
    {"id": "dup_videos",   "label": "🎬 重複動画"},
    {"id": "similar_files","label": "📄 類似ファイル名"},
    {"id": "same_size",    "label": "⚖ 同サイズ"},
    {"id": "video_player", "label": "▶ 動画再生"},
    {"id": "trash",        "label": "🗑️ ゴミ箱"},
    {"id": "settings",     "label": "⚙ 設定"},
]

TOOLBAR_DEFAULT_ORDER = (
    "up,refresh,SEP,"
    "copy,cut,paste,delete,rename,SEP,"
    "new_folder,SEP,"
    "view_mode,sort,SEP,"
    "search_box,foreign_filter,search,SEP,"
    "hidden,SEP,"
    "settings,SEP,"
    "disk_analysis,dup_videos,similar_files,same_size,video_player,SEP,"
    "trash"
)


def normalize_toolbar_order(order_value, fallback=TOOLBAR_DEFAULT_ORDER):
    """保存済みツールバー順を検証し、空/不正なら既定順へ戻す。"""
    valid_ids = {item["id"] for item in TOOLBAR_ALL_ITEMS}

    if isinstance(order_value, (list, tuple)):
        raw_tokens = [str(token).strip() for token in order_value]
    else:
        raw_tokens = [token.strip() for token in str(order_value or "").split(",")]

    tokens = []
    used_ids = set()
    has_visible_item = False
    for token in raw_tokens:
        if not token:
            continue
        if token == "SEP":
            tokens.append(token)
            continue
        if token in valid_ids and token not in used_ids:
            tokens.append(token)
            used_ids.add(token)
            has_visible_item = True

    if not has_visible_item:
        if order_value == fallback:
            return fallback
        return normalize_toolbar_order(fallback, fallback)

    return ",".join(tokens)
