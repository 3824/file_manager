import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QDialog, QFormLayout, QSpinBox, QCheckBox,
    QGroupBox, QTabWidget, QPushButton, QColorDialog, QLabel,
    QComboBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QStyledItemDelegate, QStyle,
)
from PySide6.QtCore import Qt, QTimer, QSettings, QSize
from PySide6.QtGui import QFont, QColor, QPalette, QFontDatabase

from .constants import TOOLBAR_ALL_ITEMS, TOOLBAR_DEFAULT_ORDER, normalize_toolbar_order
from .logger import logger
from .utils import coerce_bool, coerce_color, silent_information, silent_warning, silent_critical


class _FontNameDelegate(QStyledItemDelegate):
    """各フォント名をそのフォントで描画するデリゲート。"""

    _PREVIEW_PT = 11
    _ROW_H = 28

    def paint(self, painter, option, index):
        family = index.data(Qt.DisplayRole)
        opt = option.__class__(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        QApplication.style().drawControl(QStyle.CE_ItemViewItem, opt, painter)
        painter.save()
        painter.setFont(QFont(family, self._PREVIEW_PT))
        if option.state & QStyle.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())
        painter.drawText(option.rect.adjusted(8, 0, -4, 0), Qt.AlignVCenter, family)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(200, self._ROW_H)


class FontPreviewComboBox(QComboBox):
    """インストール済みフォントをそのフォントで表示するコンボボックス。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(_FontNameDelegate(self))
        for family in sorted(QFontDatabase.families()):
            self.addItem(family)

    def currentFont(self) -> QFont:
        return QFont(self.currentText())

    def setCurrentFont(self, font: QFont):
        idx = self.findText(font.family())
        if idx >= 0:
            self.setCurrentIndex(idx)

# 動的インポートの処理
try:
    from .ui_theme import apply_theme as _apply_ui_theme
    _UI_THEME_AVAILABLE = True
except ImportError:
    _UI_THEME_AVAILABLE = False

try:
    from .video_digest import OPENCV_AVAILABLE
    VIDEO_DIGEST_AVAILABLE = True
except ImportError:
    VIDEO_DIGEST_AVAILABLE = False
    OPENCV_AVAILABLE = False

try:
    from .video_digest_cache import VideoDigestCache
except ImportError:
    VideoDigestCache = None

class SettingsDialog(QDialog):
    """設定ダイアログ"""
    
    def __init__(self, parent, settings, visible_columns):
        real_parent = parent if isinstance(parent, QWidget) else None
        super().__init__(real_parent)
        self._logical_parent = parent
        self.settings = settings if settings is not None else QSettings("FileManager", "Settings")
        try:
            self.settings.sync()
        except Exception:
            pass
        self.visible_columns = visible_columns.copy()
        
        defaults = {
            "name": True, "size": True, "type": True, "modified": True,
            "permissions": True, "created": True, "attributes": True,
            "extension": True, "owner": True, "group": True,
        }
        for k, v in defaults.items():
            self.visible_columns.setdefault(k, v)
            
        self.current_colors = {
            "hidden": "#808080",
            "readonly": "#0000FF",
            "system": "#FF0000",
            "normal": "#000000"
        }
        self.init_ui()
        self.load_current_settings()
    
    def init_ui(self):
        """UIの初期化"""
        self.setWindowTitle("設定")
        self.setModal(True)
        self.resize(450, 400)
        
        layout = QVBoxLayout(self)
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)
        
        # --- フォントタブ ---
        font_tab = QWidget()
        font_layout = QFormLayout(font_tab)
        
        tree_font_group = QGroupBox("左ペイン（フォルダツリー）")
        tree_font_group_layout = QFormLayout(tree_font_group)
        self.tree_font_combo = FontPreviewComboBox()
        self.tree_font_size = QSpinBox()
        self.tree_font_size.setRange(8, 24)
        tree_font_group_layout.addRow("フォント:", self.tree_font_combo)
        tree_font_group_layout.addRow("サイズ:", self.tree_font_size)
        font_layout.addWidget(tree_font_group)

        list_font_group = QGroupBox("右ペイン（ファイル一覧）")
        list_font_group_layout = QFormLayout(list_font_group)
        self.list_font_combo = FontPreviewComboBox()
        self.list_font_size = QSpinBox()
        self.list_font_size.setRange(8, 24)
        list_font_group_layout.addRow("フォント:", self.list_font_combo)
        list_font_group_layout.addRow("サイズ:", self.list_font_size)
        font_layout.addWidget(list_font_group)
        
        tab_widget.addTab(font_tab, "フォント")
        
        # --- 表示タブ ---
        display_tab = QWidget()
        display_layout = QFormLayout(display_tab)
        column_group = QGroupBox("詳細表示で表示する項目")
        column_layout = QFormLayout(column_group)
        
        self.name_checkbox = QCheckBox("ファイル名")
        self.name_checkbox.setChecked(True)
        self.name_checkbox.setEnabled(False)
        
        self.size_checkbox = QCheckBox("サイズ")
        self.type_checkbox = QCheckBox("種類")
        self.modified_checkbox = QCheckBox("更新日時")
        self.permissions_checkbox = QCheckBox("権限")
        self.created_checkbox = QCheckBox("作成日時")
        self.attributes_checkbox = QCheckBox("属性")
        self.extension_checkbox = QCheckBox("拡張子")
        self.owner_checkbox = QCheckBox("所有者")
        self.group_checkbox = QCheckBox("グループ")
        
        for cb in [self.name_checkbox, self.size_checkbox, self.type_checkbox, self.modified_checkbox,
                   self.permissions_checkbox, self.created_checkbox, self.attributes_checkbox,
                   self.extension_checkbox, self.owner_checkbox, self.group_checkbox]:
            column_layout.addRow(cb)
        
        display_layout.addWidget(column_group)
        tab_widget.addTab(display_tab, "表示")

        # --- 色設定タブ ---
        color_tab = QWidget()
        color_layout = QFormLayout(color_tab)
        color_group = QGroupBox("ファイル属性の色設定")
        color_group_layout = QFormLayout(color_group)

        self.hidden_color_button = self._create_color_button('hidden')
        self.readonly_color_button = self._create_color_button('readonly')
        self.system_color_button = self._create_color_button('system')
        self.normal_color_button = self._create_color_button('normal')

        color_group_layout.addRow("隠しファイル:", self.hidden_color_button)
        color_group_layout.addRow("読み込み専用:", self.readonly_color_button)
        color_group_layout.addRow("システムファイル:", self.system_color_button)
        color_group_layout.addRow("通常ファイル:", self.normal_color_button)

        color_layout.addWidget(color_group)
        tab_widget.addTab(color_tab, "色設定")

        # --- 動画ダイジェストタブ ---
        video_tab = QWidget()
        video_layout = QFormLayout(video_tab)
        video_group = QGroupBox("動画ダイジェスト設定")
        video_group_layout = QFormLayout(video_group)

        if not VIDEO_DIGEST_AVAILABLE:
            warning_label = QLabel("⚠️ 動画ダイジェスト機能が利用できません。")
            warning_label.setStyleSheet("color: red; font-weight: bold;")
            video_group_layout.addRow(warning_label)
        elif not OPENCV_AVAILABLE:
            info_label = QLabel("ℹ️ OpenCV 未インストール。プレースホルダーを使用します。")
            info_label.setStyleSheet("color: #b36b00;")
            video_group_layout.addRow(info_label)

        self.thumbnail_count_spin = QSpinBox()
        self.thumbnail_count_spin.setRange(1, 12)
        self.digest_max_frames_spin = QSpinBox()
        self.digest_max_frames_spin.setRange(1, 60)
        
        size_layout = QHBoxLayout()
        self.thumbnail_width_spin = QSpinBox()
        self.thumbnail_width_spin.setRange(80, 400)
        self.thumbnail_height_spin = QSpinBox()
        self.thumbnail_height_spin.setRange(60, 300)
        size_layout.addWidget(QLabel("幅:")); size_layout.addWidget(self.thumbnail_width_spin)
        size_layout.addWidget(QLabel("高さ:")); size_layout.addWidget(self.thumbnail_height_spin)
        
        self.digest_trigger_combo = QComboBox()
        self.digest_trigger_combo.addItem("無効", "none")
        self.digest_trigger_combo.addItem("左クリック", "left")
        self.digest_trigger_combo.addItem("中クリック", "middle")

        self.digest_burst_combo = QComboBox()
        self.digest_burst_combo.addItem("なし（高速・推奨）", 0)
        self.digest_burst_combo.addItem("前後 1 フレーム", 1)
        self.digest_burst_combo.addItem("前後 2 フレーム", 2)
        self.digest_burst_combo.addItem("前後 3 フレーム", 3)
        self.digest_burst_combo.setToolTip(
            "各サムネイルの前後に追加フレームを取得してアニメーション表示します。\n"
            "「なし」が最も高速です。大量の動画を扱う場合は「なし」を推奨します。"
        )

        self.hover_thumbnail_checkbox = QCheckBox("マウスオーバーでサムネイル生成")
        self.video_digest_cache_size_spin = QSpinBox()
        self.video_digest_cache_size_spin.setRange(1, 2048)
        self.video_digest_cache_info_label = QLabel("キャッシュ使用量: -")
        self.clear_cache_button = QPushButton("キャッシュをクリア")
        self.clear_cache_button.clicked.connect(self.clear_video_digest_cache)

        self.video_player_enabled_checkbox = QCheckBox("別ウィンドウ動画プレーヤーを有効にする")
        self.video_player_muted_checkbox = QCheckBox("既定でミュート")
        self.video_player_autoplay_checkbox = QCheckBox("起動後にミュートで再生開始")
        self.video_player_speed_combo = QComboBox()
        for label, value in [("1.0x", 1.0), ("1.5x", 1.5), ("2.0x", 2.0)]:
            self.video_player_speed_combo.addItem(label, value)

        video_group_layout.addRow("マウスオーバー サムネイル数:", self.thumbnail_count_spin)
        video_group_layout.addRow("ダイジェスト フレーム数:", self.digest_max_frames_spin)
        video_group_layout.addRow("サムネイルサイズ:", size_layout)
        video_group_layout.addRow("ダイジェスト表示トリガー:", self.digest_trigger_combo)
        video_group_layout.addRow("前後フレーム補完（バースト）:", self.digest_burst_combo)
        video_group_layout.addRow(self.hover_thumbnail_checkbox)
        video_group_layout.addRow("キャッシュ上限:", self.video_digest_cache_size_spin)
        video_group_layout.addRow(self.video_digest_cache_info_label)
        video_group_layout.addRow(self.clear_cache_button)

        player_group = QGroupBox("別ウィンドウ動画プレーヤー")
        player_group_layout = QFormLayout(player_group)
        player_group_layout.addRow(self.video_player_enabled_checkbox)
        player_group_layout.addRow("既定の再生速度:", self.video_player_speed_combo)
        player_group_layout.addRow(self.video_player_muted_checkbox)
        player_group_layout.addRow(self.video_player_autoplay_checkbox)

        video_layout.addWidget(video_group)
        video_layout.addWidget(player_group)
        tab_widget.addTab(video_tab, "動画ダイジェスト")

        # --- 外観タブ ---
        appearance_tab = QWidget()
        appearance_layout = QFormLayout(appearance_tab)
        appearance_group = QGroupBox("テーマ")
        appearance_group_layout = QFormLayout(appearance_group)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("ライト", "light")
        self.theme_combo.addItem("ダーク", "dark")
        self.theme_combo.addItem("システム設定に従う", "system")
        
        self.accent_mode_combo = QComboBox()
        self.accent_mode_combo.addItem("デフォルト (Fluent)", "default")
        self.accent_mode_combo.addItem("Windows システムカラー", "system")
        self.accent_mode_combo.addItem("カスタム", "custom")
        self.accent_mode_combo.currentIndexChanged.connect(self._on_accent_mode_changed)

        self.accent_custom_button = QPushButton()
        self.accent_custom_button.setFixedSize(50, 25)
        self.accent_custom_button.clicked.connect(self._choose_accent_color)
        
        appearance_group_layout.addRow("テーマ:", self.theme_combo)
        appearance_group_layout.addRow("アクセントカラー:", self.accent_mode_combo)
        appearance_group_layout.addRow("カスタム色:", self.accent_custom_button)
        appearance_layout.addWidget(appearance_group)
        tab_widget.addTab(appearance_tab, "外観")

        # --- ツールバータブ ---
        toolbar_tab = QWidget()
        toolbar_tab_layout = QVBoxLayout(toolbar_tab)
        self.toolbar_list = QListWidget()
        self.toolbar_list.setDragDropMode(QAbstractItemView.InternalMove)
        toolbar_tab_layout.addWidget(QLabel("ドラッグで並べ替え、チェックで表示切り替え"))
        toolbar_tab_layout.addWidget(self.toolbar_list)
        
        btn_layout = QHBoxLayout()
        for label, func in [("▲", self._toolbar_move_up), ("▼", self._toolbar_move_down), 
                            ("セパレーター追加", self._toolbar_add_separator), ("削除", self._toolbar_remove_item), 
                            ("リセット", self._toolbar_reset_to_default)]:
            btn = QPushButton(label)
            btn.clicked.connect(func)
            btn_layout.addWidget(btn)
        toolbar_tab_layout.addLayout(btn_layout)
        tab_widget.addTab(toolbar_tab, "ツールバー")

        # --- フッターボタン ---
        button_layout = QHBoxLayout()
        self._apply_feedback_label = QLabel("")
        self._apply_feedback_label.setStyleSheet("color: green;")
        button_layout.addWidget(self._apply_feedback_label)
        button_layout.addStretch()
        self.ok_button = QPushButton("保存")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self.accept)
        self.apply_button = QPushButton("適用")
        self.apply_button.clicked.connect(self.apply_settings)
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

    def _create_color_button(self, attr):
        btn = QPushButton()
        btn.setFixedSize(50, 25)
        btn.clicked.connect(lambda: self.choose_color(attr))
        return btn

    def load_current_settings(self):
        """現在の設定をロード"""
        try:
            self.settings.sync()
        except Exception:
            pass

        # フォント
        self.tree_font_combo.setCurrentFont(QFont(self.settings.value("tree_font_family", "Arial")))
        self.tree_font_size.setValue(int(self.settings.value("tree_font_size", 10)))
        self.list_font_combo.setCurrentFont(QFont(self.settings.value("list_font_family", "Arial")))
        self.list_font_size.setValue(int(self.settings.value("list_font_size", 10)))
        
        # 表示列
        saved_columns = {
            "size": coerce_bool(self.settings.value("show_size", self.visible_columns.get("size", True)), True),
            "type": coerce_bool(self.settings.value("show_type", self.visible_columns.get("type", True)), True),
            "modified": coerce_bool(self.settings.value("show_modified", self.visible_columns.get("modified", True)), True),
            "permissions": coerce_bool(self.settings.value("show_permissions", self.visible_columns.get("permissions", False)), False),
            "created": coerce_bool(self.settings.value("show_created", self.visible_columns.get("created", False)), False),
            "attributes": coerce_bool(self.settings.value("show_attributes", self.visible_columns.get("attributes", False)), False),
            "extension": coerce_bool(self.settings.value("show_extension", self.visible_columns.get("extension", False)), False),
            "owner": coerce_bool(self.settings.value("show_owner", self.visible_columns.get("owner", False)), False),
            "group": coerce_bool(self.settings.value("show_group", self.visible_columns.get("group", False)), False),
        }
        self.visible_columns.update(saved_columns)
        self.size_checkbox.setChecked(self.visible_columns.get("size", True))
        self.type_checkbox.setChecked(self.visible_columns.get("type", True))
        self.modified_checkbox.setChecked(self.visible_columns.get("modified", True))
        self.permissions_checkbox.setChecked(self.visible_columns.get("permissions", False))
        self.created_checkbox.setChecked(self.visible_columns.get("created", False))
        self.attributes_checkbox.setChecked(self.visible_columns.get("attributes", False))
        self.extension_checkbox.setChecked(self.visible_columns.get("extension", False))
        self.owner_checkbox.setChecked(self.visible_columns.get("owner", False))
        self.group_checkbox.setChecked(self.visible_columns.get("group", False))

        # 動画
        self.thumbnail_count_spin.setValue(int(self.settings.value("video_thumbnail_count", 6)))
        self.thumbnail_width_spin.setValue(int(self.settings.value("video_thumbnail_width", 160)))
        self.thumbnail_height_spin.setValue(int(self.settings.value("video_thumbnail_height", 90)))
        old_auto = self.settings.value("video_auto_show_digest", None)
        trigger_default = "left" if (old_auto is True or str(old_auto).lower() == "true") else "none"
        trigger = str(self.settings.value("video_digest_trigger", trigger_default))
        idx = self.digest_trigger_combo.findData(trigger)
        self.digest_trigger_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.hover_thumbnail_checkbox.setChecked(coerce_bool(self.settings.value("video_hover_thumbnail_enabled", False), False))
        self.digest_max_frames_spin.setValue(int(self.settings.value("video_digest_max_frames", 12)))
        burst = int(self.settings.value("video_digest_burst_count", 0))
        burst_idx = self.digest_burst_combo.findData(burst)
        self.digest_burst_combo.setCurrentIndex(max(0, burst_idx))
        self.video_digest_cache_size_spin.setValue(int(self.settings.value("video_digest_cache_size_mb", 200)))
        self.video_player_enabled_checkbox.setChecked(
            coerce_bool(self.settings.value("video_player_enabled", True), True)
        )
        self.video_player_muted_checkbox.setChecked(
            coerce_bool(self.settings.value("video_player_default_muted", True), True)
        )
        self.video_player_autoplay_checkbox.setChecked(
            coerce_bool(self.settings.value("video_player_autoplay", True), True)
        )
        try:
            speed = float(self.settings.value("video_player_default_speed", 1.0))
        except (TypeError, ValueError):
            speed = 1.0
        speed_idx = self.video_player_speed_combo.findData(speed)
        self.video_player_speed_combo.setCurrentIndex(speed_idx if speed_idx >= 0 else 0)
        self.update_video_digest_cache_usage_label()

        # ツールバー
        order_str = normalize_toolbar_order(
            self.settings.value("toolbar_order", TOOLBAR_DEFAULT_ORDER)
        )
        self._populate_toolbar_settings_list(order_str)

        # 外観
        theme = str(self.settings.value("ui/theme_mode", "light"))
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(theme))
        
        accent_mode = str(self.settings.value("ui/accent_mode", "default"))
        self.accent_mode_combo.setCurrentIndex(self.accent_mode_combo.findData(accent_mode))
        
        self._accent_custom_color = str(self.settings.value("ui/accent_color", "#0078D4"))
        self.accent_custom_button.setStyleSheet(f"background-color: {self._accent_custom_color};")
        self._on_accent_mode_changed()

        # 属性色 — まず保存済みの設定値を反映し、親が保持していればそれで上書きする
        self.current_colors = {
            "hidden": coerce_color(self.settings.value("color_hidden", "#808080"), "#808080"),
            "readonly": coerce_color(self.settings.value("color_readonly", "#0000FF"), "#0000FF"),
            "system": coerce_color(self.settings.value("color_system", "#FF0000"), "#FF0000"),
            "normal": coerce_color(self.settings.value("color_normal", "#000000"), "#000000"),
        }
        parent = self._logical_parent
        try:
            if parent and parent.attribute_colors:
                self.current_colors.update(parent.attribute_colors)
        except Exception:
            pass
        self.update_color_buttons()

    def update_color_buttons(self):
        self.hidden_color_button.setStyleSheet(f"background-color: {self.current_colors['hidden']}")
        self.readonly_color_button.setStyleSheet(f"background-color: {self.current_colors['readonly']}")
        self.system_color_button.setStyleSheet(f"background-color: {self.current_colors['system']}")
        self.normal_color_button.setStyleSheet(f"background-color: {self.current_colors['normal']}")

    def choose_color(self, attr):
        current = QColor(self.current_colors[attr])
        color = QColorDialog.getColor(current, self, f"{attr}ファイルの色を選択")
        if color.isValid():
            self.current_colors[attr] = color.name()
            self.update_color_buttons()

    def _on_accent_mode_changed(self):
        is_custom = self.accent_mode_combo.currentData() == "custom"
        self.accent_custom_button.setEnabled(is_custom)

    def _choose_accent_color(self):
        color = QColorDialog.getColor(QColor(self._accent_custom_color), self, "アクセントカラーを選択")
        if color.isValid():
            self._accent_custom_color = color.name()
            self.accent_custom_button.setStyleSheet(f"background-color: {self._accent_custom_color};")

    def update_video_digest_cache_usage_label(self):
        if VideoDigestCache is None:
            self.video_digest_cache_info_label.setText("使用量: 利用不可")
            return
        try:
            cache = VideoDigestCache(max_size_mb=self.video_digest_cache_size_spin.value())
            size_mb = cache.current_size_bytes() / (1024 * 1024)
            self.video_digest_cache_info_label.setText(f"使用量: {size_mb:.2f} MB")
        except Exception as e:
            logger.debug(f"Failed to get cache usage: {e}")

    def clear_video_digest_cache(self):
        if VideoDigestCache:
            try:
                VideoDigestCache(max_size_mb=self.video_digest_cache_size_spin.value()).clear()
                self.update_video_digest_cache_usage_label()
            except Exception as e:
                silent_warning(self, "エラー", f"キャッシュクリア失敗: {e}")

    def apply_settings(self):
        """設定を保存・反映し、ダイアログは開いたまま保持する（適用ボタン用）"""
        try:
            self._persist_settings()
            self._apply_feedback_label.setText("✔ 適用しました")
            QTimer.singleShot(2000, self._clear_apply_feedback)
        except Exception as e:
            logger.error(f"Failed to apply settings: {e}")
            silent_critical(self, "エラー", f"適用エラー: {e}")

    def _clear_apply_feedback(self):
        """適用フィードバックラベルをクリアする（ダイアログ閉後のC++オブジェクト削除に対応）"""
        try:
            self._apply_feedback_label.setText("")
        except RuntimeError:
            pass

    def _show_save_success_message(self):
        silent_information(self, "設定", "設定を保存しました。")

    def accept(self):
        try:
            self._persist_settings()
            super().accept()
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            silent_critical(self, "エラー", f"保存エラー: {e}")

    def _persist_settings(self):
        s = self.settings
        s.setValue("tree_font_family", self.tree_font_combo.currentFont().family())
        s.setValue("tree_font_size", self.tree_font_size.value())
        s.setValue("list_font_family", self.list_font_combo.currentFont().family())
        s.setValue("list_font_size", self.list_font_size.value())
        
        cols = ["size", "type", "modified", "permissions", "created", "attributes", "extension", "owner", "group"]
        for c in cols:
            val = getattr(self, f"{c}_checkbox").isChecked()
            self.visible_columns[c] = val
            s.setValue(f"show_{c}", val)
        
        s.setValue("video_thumbnail_count", self.thumbnail_count_spin.value())
        s.setValue("video_thumbnail_width", self.thumbnail_width_spin.value())
        s.setValue("video_thumbnail_height", self.thumbnail_height_spin.value())
        trigger = self.digest_trigger_combo.currentData()
        s.setValue("video_digest_trigger", trigger)
        s.setValue("video_auto_show_digest", trigger == "left")
        s.setValue("video_hover_thumbnail_enabled", self.hover_thumbnail_checkbox.isChecked())
        s.setValue("video_digest_max_frames", self.digest_max_frames_spin.value())
        s.setValue("video_digest_burst_count", self.digest_burst_combo.currentData())
        s.setValue("video_digest_cache_size_mb", self.video_digest_cache_size_spin.value())
        s.setValue("video_player_enabled", self.video_player_enabled_checkbox.isChecked())
        s.setValue("video_player_default_speed", self.video_player_speed_combo.currentData())
        s.setValue("video_player_default_muted", self.video_player_muted_checkbox.isChecked())
        s.setValue("video_player_autoplay", self.video_player_autoplay_checkbox.isChecked())
        
        s.setValue("toolbar_order", self._build_toolbar_order_string())
        s.setValue("ui/theme_mode", self.theme_combo.currentData())
        s.setValue("ui/accent_mode", self.accent_mode_combo.currentData())
        s.setValue("ui/accent_color", self._accent_custom_color)
        
        for k, v in self.current_colors.items():
            s.setValue(f"color_{k}", v)
        
        s.sync()
        
        # 親への反映
        try:
            parent = self._logical_parent
            if parent:
                if hasattr(parent, 'visible_columns'):
                    parent.visible_columns = self.visible_columns.copy()
                if hasattr(parent, 'attribute_colors'):
                    parent.attribute_colors = self.current_colors.copy()
                if hasattr(parent, 'video_player_enabled'):
                    parent.video_player_enabled = self.video_player_enabled_checkbox.isChecked()
                    parent.video_player_default_speed = float(self.video_player_speed_combo.currentData())
                    parent.video_player_default_muted = self.video_player_muted_checkbox.isChecked()
                    parent.video_player_autoplay = self.video_player_autoplay_checkbox.isChecked()

                for method in ['refresh_icons', 'update_column_visibility', 'apply_fonts', 'rebuild_toolbar']:
                    if hasattr(parent, method):
                        getattr(parent, method)()

                if hasattr(parent, 'file_system_model') and hasattr(parent.file_system_model, 'update_visible_columns'):
                    parent.file_system_model.update_visible_columns(self.visible_columns)
        except Exception:
            pass

        if _UI_THEME_AVAILABLE:
            app = QApplication.instance()
            if app: _apply_ui_theme(app)

    def _populate_toolbar_settings_list(self, order_str):
        self.toolbar_list.clear()
        all_ids = {item["id"] for item in TOOLBAR_ALL_ITEMS}
        label_map = {item["id"]: item["label"] for item in TOOLBAR_ALL_ITEMS}
        used = set()
        
        for token in [t.strip() for t in order_str.split(",") if t.strip()]:
            if token == "SEP":
                item = QListWidgetItem("── セパレーター ──")
                item.setData(Qt.UserRole, "SEP")
            elif token in all_ids:
                item = QListWidgetItem(label_map[token])
                item.setData(Qt.UserRole, token)
                item.setCheckState(Qt.Checked)
                used.add(token)
            else: continue
            self.toolbar_list.addItem(item)
            
        for info in TOOLBAR_ALL_ITEMS:
            if info["id"] not in used:
                item = QListWidgetItem(info["label"])
                item.setData(Qt.UserRole, info["id"])
                item.setCheckState(Qt.Unchecked)
                self.toolbar_list.addItem(item)

    def _build_toolbar_order_string(self):
        tokens = []
        visible_items = 0
        for i in range(self.toolbar_list.count()):
            li = self.toolbar_list.item(i)
            tid = li.data(Qt.UserRole)
            if tid == "SEP" or li.checkState() == Qt.Checked:
                tokens.append(tid)
                if tid != "SEP":
                    visible_items += 1
        if visible_items == 0:
            return TOOLBAR_DEFAULT_ORDER
        return normalize_toolbar_order(",".join(tokens))

    def _toolbar_move_up(self):
        row = self.toolbar_list.currentRow()
        if row > 0:
            item = self.toolbar_list.takeItem(row)
            self.toolbar_list.insertItem(row - 1, item)
            self.toolbar_list.setCurrentRow(row - 1)

    def _toolbar_move_down(self):
        row = self.toolbar_list.currentRow()
        if row < self.toolbar_list.count() - 1:
            item = self.toolbar_list.takeItem(row)
            self.toolbar_list.insertItem(row + 1, item)
            self.toolbar_list.setCurrentRow(row + 1)

    def _toolbar_add_separator(self):
        row = self.toolbar_list.currentRow()
        item = QListWidgetItem("── セパレーター ──")
        item.setData(Qt.UserRole, "SEP")
        self.toolbar_list.insertItem(row + 1 if row >= 0 else self.toolbar_list.count(), item)

    def _toolbar_remove_item(self):
        row = self.toolbar_list.currentRow()
        if row >= 0:
            item = self.toolbar_list.item(row)
            if item.data(Qt.UserRole) == "SEP":
                self.toolbar_list.takeItem(row)
            else:
                item.setCheckState(Qt.Unchecked)
                self.toolbar_list.addItem(self.toolbar_list.takeItem(row))

    def _toolbar_reset_to_default(self):
        self._populate_toolbar_settings_list(TOOLBAR_DEFAULT_ORDER)
