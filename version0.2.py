# version0.2.py
import sys
import os
import ctypes
import psutil
import json
import re
import math
import time
import uuid
import threading
from datetime import datetime
from urllib.request import urlopen
import pyautogui
try:
    import pygetwindow as gw
except Exception:
    gw = None
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QAbstractItemView,
    QListWidgetItem,
    QFileIconProvider,
    QStyle,
    QMenu,
    QInputDialog,
    QFileDialog,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer, QSize, QRectF, QFileInfo, QPoint, QRect
from PyQt5.QtGui import (
    QFontDatabase,
    QFont,
    QBitmap,
    QPixmap,
    QPainter,
    QPen,
    QBrush,
    QColor,
    QLinearGradient,
    QRadialGradient,
    QPainterPath,
    QRegion,
    QGuiApplication,
    QIcon,
)
from ui_components import (
    MessageBubble,
    AuthorizationPromptWidget,
    ChatInputTextEdit,
    TitleBar,
    GlassRail,
    ScreenShareOverlay,
    FeedbackRow,
    ThinkingIndicator,
    FileCard,
)
from windows_agent import WindowsAgent
from worker import WorkerThread, VoiceInputThread

def _find_latest_version(base_dir):
    """Return the latest 'app-x.y.z' subdirectory name inside base_dir, or ''."""
    try:
        entries = [e for e in os.listdir(base_dir) if e.startswith("app-") and os.path.isdir(os.path.join(base_dir, e))]
        if entries:
            entries.sort(reverse=True)
            return entries[0]
    except Exception:
        pass
    return ""
class AIAgentWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        app_dir = self._get_data_dir()
        resource_dir = self._get_resource_dir()
        self.conversation_log_file = os.path.join(app_dir, "logs", "conversation.log")
        self.security_audit_file = os.path.join(app_dir, "logs", "security_audit.jsonl")
        self.chat_sessions_file = os.path.join(app_dir, "memory", "chat_sessions.json")
        self.task_sessions_file = os.path.join(app_dir, "memory", "task_sessions.json")
        self.max_chat_sessions = 100
        self.chat_sessions = []
        self.task_sessions = []
        self.current_conversation = []       # chat mode history
        self.current_task_conversation = []  # task mode history
        self.current_session_id = None
        self.current_task_session_id = None
        self.current_conversation_dirty = False
        self._drag_active = False
        self._drag_offset = QPoint()
        self._resize_active = False
        self._resize_margin = 8
        self._resize_edges = set()
        self._resize_start_geo = QRect()
        self._resize_start_pos = QPoint()
        
        # Window settings - open like a right-side Copilot panel.
        self.setWindowTitle("AI Agent")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)
        app_icon_path = self._resolve_asset_path("Opuntia logo 500px.png")
        if os.path.exists(app_icon_path):
            self.setWindowIcon(QIcon(app_icon_path))
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            panel_width = min(980, max(760, int(available.width() * 0.56)))
            panel_height = min(980, max(700, int(available.height() * 0.92)))
            panel_x = available.x() + available.width() - panel_width - 12
            panel_y = available.y() + 12
            self.setGeometry(panel_x, panel_y, panel_width, panel_height)
        else:
            self.setGeometry(100, 100, 980, 900)
        self.setMinimumSize(620, 520)  # Keep usable on smaller sizes
        
        # Colors - glassmorphism palette
        self.bg_color = "#07091a"
        self.glass_bg = "rgba(255, 255, 255, 0.08)"
        self.glass_border = "1px solid rgba(255, 255, 255, 0.16)"
        self.sidebar_color = self.glass_bg
        self.text_primary = "#FFFFFF"
        self.text_secondary = "#8A8A9A"
        self.input_bg = "rgba(255, 255, 255, 0.08)"
        self.glass_angle_deg = -45
        self.glass_intensity = 0.80
        self.glass_reflection = 1.0
        self.glass_depth = 1.3
        self.glass_dispersion = 1.0
        self.glass_frost = 1.25
        self.glass_splay = 1.0
        self.glass_opacity = 0.82
        self.bg_anim_phase = 0.0
        self.bg_anim_speed = 0.006
        
        # Load Poppins and force Medium globally across the UI.
        self.ui_font_family = "Poppins"
        loaded_families = []
        base_dir = resource_dir
        font_candidates = [
            os.path.join(base_dir, "Poppins-Regular.ttf"),
            os.path.join(base_dir, "Poppins-Medium.ttf"),
            os.path.join(base_dir, "fonts", "Poppins-Regular.ttf"),
            os.path.join(base_dir, "fonts", "Poppins-Medium.ttf"),
        ]
        for font_path in font_candidates:
            if not os.path.exists(font_path):
                continue
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                loaded_families.extend(QFontDatabase.applicationFontFamilies(font_id))
        if loaded_families:
            self.ui_font_family = loaded_families[0]
        else:
            print(
                "WARNING: Poppins font files not found. Add "
                "'Poppins-Regular.ttf' and 'Poppins-Medium.ttf' next to ui_agent.py "
                "or inside a ./fonts folder."
            )
        self.adamina_font_family = "Adamina"
        adamina_candidates = [
            os.path.join(base_dir, "Adamina", "Adamina-Regular.ttf"),
            os.path.join(base_dir, "Adamina-Regular.ttf"),
            os.path.join(base_dir, "fonts", "Adamina-Regular.ttf"),
        ]
        for font_path in adamina_candidates:
            if not os.path.exists(font_path):
                continue
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id == -1:
                continue
            fams = QFontDatabase.applicationFontFamilies(font_id)
            if fams:
                self.adamina_font_family = fams[0]
                break
        app = QApplication.instance()
        if app is not None:
            medium_font = QFont(self.ui_font_family, 10)
            medium_font.setStyleName("Medium")
            medium_font.setWeight(QFont.Medium)
            app.setFont(medium_font)
            base_qss = f"* {{ font-family: '{self.ui_font_family}'; font-weight: 500; }}"
            liquid_qss = """
            QDialog, QMessageBox, QFileDialog, QInputDialog {
                background-color: rgba(10, 12, 16, 220);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 16px;
            }
            QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {
                color: #F2F2F2;
                font-size: 13px;
            }
            QLineEdit, QTextEdit, QPlainTextEdit {
                background-color: rgba(0, 0, 0, 0.35);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
                padding: 6px 10px;
            }
            QMenu {
                background-color: rgba(10, 12, 16, 245);
                color: #F2F2F2;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 14px;
                padding: 6px;
            }
            QMenu::item {
                padding: 8px 14px;
                margin: 2px 4px;
                border-radius: 8px;
            }
            QMenu::item:selected {
                background-color: rgba(255, 255, 255, 0.12);
            }
            QMessageBox QPushButton, QDialog QPushButton, QFileDialog QPushButton {
                background-color: rgba(255, 255, 255, 0.10);
                color: #FFFFFF;
                border: none;
                border-radius: 10px;
                padding: 6px 14px;
            }
            QMessageBox QPushButton:hover, QDialog QPushButton:hover, QFileDialog QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.18);
            }
            """
            app.setStyleSheet(base_qss + "\n" + liquid_qss)

        
        # Initialize agent
        self.agent = WindowsAgent()
        self.worker = None
        self.send_btn = None
        self.input_container = None
        self.conversation_list = None
        self.apps_list = None
        self.rail_apps_list = None
        self.sidebar_widget = None
        self.sidebar_toggle_btn = None
        self.rail_toggle_btn = None
        self.outside_toggle_btn = None
        self.sidebar_is_open = True
        self.sidebar_expanded_width = 390
        self.sidebar_collapsed_width = 66
        self.compact_mode_active = False
        self.small_window_radius = 10
        self.sidebar_detail_widgets = []
        self.current_mode = "chat"  # "chat" or "task"
        self.new_chat_btn = None
        self.new_chat_icon_lbl = None
        self.new_chat_icon_pix = QPixmap()
        self.new_task_icon_pix = QPixmap()
        self.center_top_spacer = None
        self.center_bottom_spacer = None
        self.smart_header_gap = None
        self.smart_header_label = None
        self._weather_snapshot = None
        self._last_weather_fetch_ts = 0.0
        self._weather_fetch_inflight = False
        self.content_widget = None
        self.beta_label = None
        self.icon_provider = QFileIconProvider()
        self.pending_sensitive_command = None
        self.pending_auth_widget = None
        self.screen_share_enabled = False
        self.screen_share_overlay = None
        self.latest_screen_path = ""
        self.screen_capture_dir = os.path.join(app_dir, "memory", "screen_share")
        try:
            os.makedirs(os.path.join(app_dir, "logs"), exist_ok=True)
            os.makedirs(os.path.join(app_dir, "memory"), exist_ok=True)
        except Exception:
            pass
        self.share_btn = None
        self.voice_btn = None
        self.attach_btn = None
        self.memory_btn = None
        self.private_btn = None
        self.attachments_label = None
        self.pending_attachments = []
        self.voice_thread = None
        self.voice_listening = False
        self.ai_status_label = None
        # Hidden by default to keep the UI clean.
        self.show_ai_status = False
        self.chat_activity_indicator = None
        self.task_activity_indicator = None
        self.last_user_bubble_chat = None
        self.last_user_bubble_task = None
        self._phase_timer = None
        self._pending_phase_label = None
        self._phase_hold_until = 0.0
        self._phase_min_ms = 380
        self._phase_lock_until = 0.0
        self._gen_label_re = re.compile(r"\b(generate|generation|create|write|build|make|produce|draft|compose|summarize|summarise)\b", re.I)
        self.pre_share_geometry = None
        self.pre_share_topmost = False
        self.pre_share_min_size = None
        self.pre_share_sidebar_open = None
        self.last_screen_capture_ts = 0.0
        self.screen_capture_max_w = int(os.getenv("SCREEN_CAPTURE_MAX_W", "1920"))
        self.screen_capture_max_h = int(os.getenv("SCREEN_CAPTURE_MAX_H", "1080"))
        self.screen_capture_format = (os.getenv("SCREEN_CAPTURE_FORMAT", "png") or "png").strip().lower()
        self.screen_capture_jpeg_quality = int(os.getenv("SCREEN_CAPTURE_JPEG_QUALITY", "88"))
        self._last_sys_text = ""
        self._last_disk_refresh_ts = 0.0
        self._cached_disk_usage = None
        self._last_feedback_ts = 0.0
        self._last_apps_refresh_ts = 0.0
        self.apps_refresh_interval_sec = 6.0
        self._last_apps_signature = ()
        self._icon_cache = {}
        self.load_chat_sessions()
        self.load_task_sessions()
        
        # Timer for updates
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_system_info)
        
        self.init_ui()
        # Apply native Windows corner preference once the HWND is ready.
        QTimer.singleShot(0, self._apply_window_round_mask)
        QTimer.singleShot(0, self._apply_windows_blur)
        self.timer.start(2200)

    def _get_app_dir(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _get_data_dir(self):
        if getattr(sys, "frozen", False):
            base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or self._get_app_dir()
            return os.path.join(base, "Opuntia Beta0.2")
        return self._get_app_dir()

    def _get_resource_dir(self):
        return getattr(sys, "_MEIPASS", self._get_app_dir())

    def _resolve_asset_path(self, filename):
        base_dir = self._get_resource_dir()
        candidates = [
            os.path.join(base_dir, "Vector images & icons", filename),
            os.path.join(base_dir, filename),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[0]

    def init_ui(self):
        assets_dir = self._get_resource_dir()

        def _icon_pixmap_from_file(filename, size, tint_hex=None):
            path = self._resolve_asset_path(filename)
            pix = QPixmap(path)
            if pix.isNull():
                return QPixmap()
            pix = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not tint_hex:
                return pix
            tinted = QPixmap(pix.size())
            tinted.fill(Qt.transparent)
            painter = QPainter(tinted)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.drawPixmap(0, 0, pix)
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(tinted.rect(), QColor(tint_hex))
            painter.end()
            return tinted

        def chat_icon_pixmap(size=20):
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor("#FFFFFF"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(size * 0.18, size * 0.78)
            path.cubicTo(size * 0.25, size * 0.56, size * 0.30, size * 0.35, size * 0.50, size * 0.24)
            path.cubicTo(size * 0.69, size * 0.14, size * 0.86, size * 0.19, size * 0.90, size * 0.30)
            path.cubicTo(size * 0.79, size * 0.35, size * 0.65, size * 0.45, size * 0.56, size * 0.58)
            path.cubicTo(size * 0.46, size * 0.72, size * 0.32, size * 0.81, size * 0.18, size * 0.78)
            painter.drawPath(path)
            painter.end()
            return pix

        def system_icon_pixmap(size=18):
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor("#FFFFFF"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            rect = QRectF(1.5, size * 0.22, size - 3.0, size * 0.62)
            painter.drawRoundedRect(rect, 2.8, 2.8)
            painter.end()
            return pix

        def apps_icon_pixmap(size=18):
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor("#FFFFFF"), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            cell = size * 0.34
            gap = size * 0.12
            x0 = (size - (cell * 2 + gap)) / 2
            y0 = (size - (cell * 2 + gap)) / 2
            for row in range(2):
                for col in range(2):
                    x = x0 + col * (cell + gap)
                    y = y0 + row * (cell + gap)
                    painter.drawRoundedRect(QRectF(x, y, cell, cell), 1.8, 1.8)
            painter.end()
            return pix

        def mic_icon_pixmap(size=16, color="#FFFFFF"):
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor(color), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            # Head
            head = QRectF(size * 0.32, size * 0.14, size * 0.36, size * 0.46)
            painter.drawRoundedRect(head, 3, 3)
            # Stem
            painter.drawLine(int(size * 0.5), int(size * 0.60), int(size * 0.5), int(size * 0.82))
            # Base arc + line
            painter.drawArc(int(size * 0.25), int(size * 0.48), int(size * 0.50), int(size * 0.40), 200 * 16, 140 * 16)
            painter.drawLine(int(size * 0.34), int(size * 0.88), int(size * 0.66), int(size * 0.88))
            painter.end()
            return pix

        # Main widget
        main = QWidget()
        self.main_widget = main
        main.setAutoFillBackground(False)
        main.setStyleSheet(f"""
            background: transparent;
            font-family: '{self.ui_font_family}';
        """)
        self.setCentralWidget(main)

        
        # Root vertical layout
        root_layout = QVBoxLayout(main)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Full-width top bar
        self.title_bar = TitleBar(self)
        root_layout.addWidget(self.title_bar)

        # Body widget for sidebar and content
        body_widget = QWidget()
        self.body_widget = body_widget
        main_layout = QHBoxLayout(body_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # === LEFT SIDEBAR: app rail + features panel ===
        sidebar = QWidget()
        sidebar.setFixedWidth(self.sidebar_expanded_width)
        sidebar.setStyleSheet(f"background-color: {self.sidebar_color};")
        self.sidebar_widget = sidebar
        
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        sidebar_shell = QHBoxLayout()
        sidebar_shell.setContentsMargins(0, 0, 0, 0)
        sidebar_shell.setSpacing(0)
        sidebar_layout.addLayout(sidebar_shell)

        # Left rail: running apps icons only.
        app_rail = GlassRail(self)
        app_rail.setFixedWidth(66)
        app_rail_layout = QVBoxLayout(app_rail)
        app_rail_layout.setContentsMargins(10, 10, 10, 14)
        app_rail_layout.setSpacing(10)

        app_rail_layout.addSpacing(8)

        rail_apps_icon = QLabel()
        rail_apps_icon.setAlignment(Qt.AlignCenter)
        apps_icon_pix = _icon_pixmap_from_file("Vector apps.png", 20)
        if not apps_icon_pix.isNull():
            rail_apps_icon.setPixmap(apps_icon_pix)
        app_rail_layout.addWidget(rail_apps_icon, 0, Qt.AlignHCenter)

        self.rail_apps_list = QListWidget()
        self.rail_apps_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.rail_apps_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.rail_apps_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.rail_apps_list.setIconSize(QSize(40, 40))
        self.rail_apps_list.setFocusPolicy(Qt.NoFocus)
        self.rail_apps_list.setCursor(Qt.PointingHandCursor)
        self.rail_apps_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                min-height: 52px;
                padding: 6px 0px;
                border-radius: 10px;
            }
            QListWidget::item:hover { background-color: rgba(255, 255, 255, 0.10); }
            QListWidget::item:selected { background-color: rgba(255, 255, 255, 0.13); }
            QScrollBar:vertical {
                background: transparent;
                width: 0px;
                margin: 0px;
            }
        """)
        self.rail_apps_list.itemClicked.connect(self.on_running_app_clicked)
        app_rail_layout.addWidget(self.rail_apps_list, 1)

        # Right panel: non-app features.
        panel = QWidget()
        panel.setStyleSheet("background-color: transparent; border-right: none;")
        self.sidebar_panel_widget = panel
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 11, 18, 20)
        panel_layout.setSpacing(0)

        sidebar_shell.addWidget(app_rail, 0)
        sidebar_shell.addWidget(panel, 1)
        self.sidebar_detail_widgets.append(panel)

        # Sidebar top row
        sidebar_top_row = QWidget()
        sidebar_top_layout = QHBoxLayout(sidebar_top_row)
        sidebar_top_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_top_layout.setSpacing(0)

        self.beta_label = QLabel("")
        sidebar_top_layout.addStretch()
        panel_layout.addWidget(sidebar_top_row)
        panel_layout.addSpacing(18)
        
        # New chat row aligned to the same icon/text columns as System info.
        new_chat_row = QWidget()
        new_chat_layout = QHBoxLayout(new_chat_row)
        new_chat_layout.setContentsMargins(0, 0, 0, 12)
        new_chat_layout.setSpacing(10)
        new_chat_icon_lbl = QLabel()
        new_chat_icon_lbl.setFixedSize(20, 20)
        new_chat_icon_lbl.setAlignment(Qt.AlignCenter)
        new_chat_icon = _icon_pixmap_from_file("Vector New chat.png", 20, "#FFFFFF")
        self.new_chat_icon_pix = new_chat_icon if not new_chat_icon.isNull() else chat_icon_pixmap(20)
        new_task_icon = _icon_pixmap_from_file("Vector new task.png", 20, "#FFFFFF")
        self.new_task_icon_pix = new_task_icon if not new_task_icon.isNull() else self.new_chat_icon_pix
        new_chat_icon_lbl.setPixmap(self.new_chat_icon_pix)
        self.new_chat_icon_lbl = new_chat_icon_lbl
        self.new_chat_btn = QPushButton("New chat")
        new_chat_btn = self.new_chat_btn
        new_chat_btn.setCursor(Qt.PointingHandCursor)
        new_chat_btn.setFixedHeight(28)
        new_chat_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #FFFFFF;
                font-family: 'Poppins';
                font-size: 15px;
                font-weight: 500;
                text-align: left;
                padding: 0px;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: rgba(255, 255, 255, 0.08); }
        """)
        new_chat_btn.clicked.connect(self._new_chat_or_task)
        new_chat_layout.addWidget(new_chat_icon_lbl, 0)
        new_chat_layout.addWidget(new_chat_btn, 1)
        panel_layout.addWidget(new_chat_row)
        self.sidebar_detail_widgets.append(new_chat_row)

        # Saved conversations list
        self.conversation_list = QListWidget()
        self.conversation_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.conversation_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.conversation_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.conversation_list.setFocusPolicy(Qt.NoFocus)
        self.conversation_list.setCursor(Qt.PointingHandCursor)
        self.conversation_list.setMinimumHeight(0)
        self.conversation_list.setMaximumHeight(0)
        self.conversation_list.setVisible(False)
        self.conversation_list.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                color: {self.text_primary};
                font-family: 'Poppins';
                font-size: 13px;
                font-weight: 500;
                border: none;
                margin-left: 0px;
                margin-bottom: 10px;
            }}
            QListWidget::item {{ padding: 6px 2px; border-radius: 6px; }}
            QListWidget::item:hover {{ background-color: rgba(255, 255, 255, 0.09); }}
            QListWidget::item:selected {{ background-color: rgba(255, 255, 255, 0.12); }}
            QScrollBar:vertical {{ width: 0px; background: transparent; }}
        """)
        self.conversation_list.itemClicked.connect(self.on_conversation_clicked)
        panel_layout.addWidget(self.conversation_list)
        self.sidebar_detail_widgets.append(self.conversation_list)
        
        # System info header (no emoji - just text)
        sys_header_row = QWidget()
        sys_header_layout = QHBoxLayout(sys_header_row)
        sys_header_layout.setContentsMargins(0, 0, 0, 8)
        sys_header_layout.setSpacing(10)
        sys_icon = QLabel()
        sys_icon_pix = _icon_pixmap_from_file("Vector system info.png", 18, "#FFFFFF")
        if not sys_icon_pix.isNull():
            sys_icon.setPixmap(sys_icon_pix)
        else:
            sys_icon.setPixmap(system_icon_pixmap(18))
        sys_icon.setFixedSize(20, 20)
        sys_icon.setAlignment(Qt.AlignCenter)
        sys_header = QLabel("System info")
        sys_header.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                color: #FFFFFF;
                font-family: 'Poppins';
                font-size: 15px;
                font-weight: 500;
            }}
        """)
        sys_header_layout.addWidget(sys_icon)
        sys_header_layout.addWidget(sys_header)
        sys_header_layout.addStretch()
        panel_layout.addWidget(sys_header_row)
        
        # System details - EXACT format
        self.sys_details = QLabel()
        self.sys_details.setWordWrap(True)
        self.sys_details.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                color: {self.text_secondary};
                font-family: 'Poppins';
                font-size: 13px;
                font-weight: 400;
                line-height: 18px;
                margin-left: 0px;
                margin-bottom: 20px;
            }}
        """)
        panel_layout.addWidget(self.sys_details)
        self.sidebar_detail_widgets.append(sys_header_row)
        self.sidebar_detail_widgets.append(self.sys_details)

        panel_layout.addStretch()
        
        # === MAIN CONTENT (RESIZABLE) ===
        content = QWidget()
        self.content_widget = content
        content.setStyleSheet("background-color: transparent;")
        
        # Main content layout
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(40, 20, 40, 20)
        content_layout.setSpacing(12)

        # Top center mode buttons (Chat / Tasks)
        mode_row = QWidget()
        mode_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(10)

        self.chat_mode_btn = QPushButton("Chat")
        self.tasks_mode_btn = QPushButton("Task")
        self.code_mode_btn = QPushButton("Code")
        self.wallet_mode_btn = QPushButton("Wallet")
        for btn in (self.chat_mode_btn, self.tasks_mode_btn, self.code_mode_btn, self.wallet_mode_btn):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(44)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.08);
                    color: rgba(255, 255, 255, 0.80);
                    border: none;
                    border-radius: 22px;
                    padding: 0 22px;
                    font-family: 'Poppins';
                    font-size: 14px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.14);
                    color: rgba(255, 255, 255, 0.95);
                    border: none;
                }
            """)

        # Corner badge after sidebar (same row as buttons).
        beta_corner = QLabel("Beta")
        beta_corner.setStyleSheet("""
            QLabel {
                color: #7D7D7D;
                font-family: 'Poppins';
                font-size: 16px;
                font-weight: 500;
                padding: 0px;
                margin: 0px;
            }
        """)
        mode_layout.addWidget(beta_corner, 0, Qt.AlignLeft)
        mode_layout.addStretch()
        mode_layout.addWidget(self.chat_mode_btn)
        mode_layout.addWidget(self.tasks_mode_btn)
        mode_layout.addWidget(self.code_mode_btn)
        mode_layout.addWidget(self.wallet_mode_btn)
        mode_layout.addStretch()
        content_layout.addWidget(mode_row, 0)

        # Connect mode buttons
        self.chat_mode_btn.clicked.connect(lambda: self._switch_mode("chat"))
        self.tasks_mode_btn.clicked.connect(lambda: self._switch_mode("task"))

        # Mark Chat as active on startup
        self._apply_mode_button_styles()

        # Chat area (scrollable) - TAKES AVAILABLE SPACE
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 10px;
                margin: 2px 2px 2px 2px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #5d5d5d;
                border-radius: 5px;
                min-height: 80px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #6a6a6a;
            }
            QScrollBar::sub-line:vertical {
                background: transparent;
                height: 0px;
                subcontrol-origin: margin;
                subcontrol-position: top;
            }
            QScrollBar::add-line:vertical {
                background: transparent;
                height: 0px;
                subcontrol-origin: margin;
                subcontrol-position: bottom;
            }
            QScrollBar::up-arrow:vertical {
                width: 0px;
                height: 0px;
                background: transparent;
                border: none;
            }
            QScrollBar::down-arrow:vertical {
                width: 0px;
                height: 0px;
                background: transparent;
                border: none;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        
        self.chat_widget = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.addStretch()

        self.task_widget = QWidget()
        self.task_widget.setStyleSheet("background-color: transparent;")
        self.task_layout = QVBoxLayout(self.task_widget)
        self.task_layout.addStretch()

        # AI activity indicators (chat + task)
        self.chat_activity_indicator = ThinkingIndicator()
        self.task_activity_indicator = ThinkingIndicator()
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, self.chat_activity_indicator)
        self.task_layout.insertWidget(self.task_layout.count() - 1, self.task_activity_indicator)
        self.chat_activity_indicator.set_active(False)
        self.task_activity_indicator.set_active(False)
        self._phase_timer = QTimer(self)
        self._phase_timer.setSingleShot(True)
        self._phase_timer.timeout.connect(self._flush_pending_phase)

        self.scroll_area = scroll_area
        scroll_area.setWidget(self.chat_widget)  # start in chat mode
        content_layout.addWidget(scroll_area, 1)  # Takes all available space

        self.center_top_spacer = QWidget()
        self.center_top_spacer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.center_top_spacer.setVisible(False)
        content_layout.addWidget(self.center_top_spacer, 1)

        self.smart_header_label = QLabel("")
        self.smart_header_label.setVisible(False)
        self.smart_header_label.setWordWrap(True)
        self.smart_header_label.setTextFormat(Qt.PlainText)
        self.smart_header_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.smart_header_label.setMaximumWidth(980)
        self.smart_header_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.smart_header_label.setStyleSheet(f"""
            QLabel {{
                color: rgba(245, 245, 245, 0.96);
                font-family: '{self.adamina_font_family}';
                font-size: 24px;
                font-weight: 400;
                line-height: 1.35;
            }}
        """)
        content_layout.addWidget(self.smart_header_label, 0, Qt.AlignHCenter)

        self.smart_header_gap = QWidget()
        self.smart_header_gap.setFixedHeight(52)
        self.smart_header_gap.setVisible(False)
        content_layout.addWidget(self.smart_header_gap, 0)
        
        # Rebuilt chat input bar from scratch.
        input_container = QWidget()
        self.input_container = input_container
        input_container.setObjectName("input_container")
        input_container.setFixedWidth(870)
        input_container.setFixedHeight(130)
        input_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        input_container.setStyleSheet(f"""
            QWidget#input_container {{
                background: {self.glass_bg};
                border-radius: 20px;
                border: none;
            }}
        """)

        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(24, 16, 24, 14)
        input_layout.setSpacing(10)

        self.input_field = ChatInputTextEdit()
        self.input_field.setPlaceholderText("Ask me anything")
        # Prevent QTextEdit from inserting dropped file:// URLs
        self.input_field.setAcceptDrops(False)
        try:
            self.input_field.viewport().setAcceptDrops(False)
        except Exception:
            pass
        self.input_field.setFixedHeight(72)
        self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input_field.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                color: #F2F2F2;
                font-family: 'Poppins';
                font-size: 17px;
                font-weight: 500;
                border: none;
                padding: 0px;
            }}
            QTextEdit[placeholderText]:empty {{
                color: #9a9a9a;
            }}
            QTextEdit:focus {{
                border: none;
            }}
        """)
        self.input_field.sendRequested.connect(self.send_message)
        self.input_field.textChanged.connect(self.update_send_button_state)
        self.input_field.textChanged.connect(self._update_input_bar_height)
        
        self.send_btn = QPushButton("")
        self.send_btn.setFixedSize(44, 44)
        self.send_btn.setCursor(Qt.PointingHandCursor)
        send_icon_pix = _icon_pixmap_from_file("Vector arrow send.png", 16, "#FFFFFF")
        if not send_icon_pix.isNull():
            self.send_btn.setIcon(QIcon(send_icon_pix))
            self.send_btn.setIconSize(QSize(16, 16))
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.18);
                color: {self.text_primary};
                font-family: 'Poppins';
                font-weight: 500;
                border: none;
                border-radius: 22px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.26);
                border: none;
            }}
            QPushButton:disabled {{
                background-color: rgba(255, 255, 255, 0.05);
                border: none;
                color: rgba(255, 255, 255, 0.30);
            }}
        """)
        self.send_btn.clicked.connect(self.send_message)

        self.share_btn = QPushButton("Live")
        self.share_btn.setFixedSize(80, 44)
        self.share_btn.setCursor(Qt.PointingHandCursor)
        self.share_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.09);
                color: {self.text_primary};
                font-family: 'Poppins';
                font-size: 13px;
                font-weight: 500;
                border: none;
                border-radius: 22px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.15);
                border: none;
            }}
        """)
        self.share_btn.clicked.connect(self.toggle_screen_share)
        self.share_btn.setVisible(self.current_mode == "task")

        self.voice_btn = QPushButton("")
        self.voice_btn.setFixedSize(44, 44)
        self.voice_btn.setCursor(Qt.PointingHandCursor)
        mic_icon_file = _icon_pixmap_from_file("Vector mic.png", 16, "#FFFFFF")
        if not mic_icon_file.isNull():
            self.voice_btn.setIcon(QIcon(mic_icon_file))
        else:
            self.voice_btn.setIcon(QIcon(mic_icon_pixmap(16, "#FFFFFF")))
        self.voice_btn.setIconSize(QSize(16, 16))
        self.voice_btn.setToolTip("Start microphone")
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.09);
                border: none;
                border-radius: 22px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                border: none;
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 0.04);
                border: none;
            }
        """)
        self.voice_btn.clicked.connect(self.toggle_voice_input)

        self.attach_btn = QPushButton("")
        self.attach_btn.setFixedSize(44, 44)
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.setToolTip("Add files or folders")
        add_icon_pix = _icon_pixmap_from_file("Vector add.png", 16, "#FFFFFF")
        if not add_icon_pix.isNull():
            self.attach_btn.setIcon(QIcon(add_icon_pix))
            self.attach_btn.setIconSize(QSize(16, 16))
        self.attach_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.09);
                color: {self.text_primary};
                font-family: 'Poppins';
                font-size: 12px;
                font-weight: 500;
                border: none;
                border-radius: 22px;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.15);
                border: none;
            }}
            QPushButton:disabled {{
                background-color: rgba(255, 255, 255, 0.04);
                color: rgba(255, 255, 255, 0.30);
                border: none;
            }}
        """)
        self.attach_btn.clicked.connect(self.open_attachment_menu)

        # Input field takes remaining space
        input_layout.addWidget(self.input_field, 1)

        # Buttons at the bottom right
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addWidget(self.attach_btn, 0, Qt.AlignLeft)
        button_layout.addStretch()
        button_layout.addWidget(self.share_btn)
        button_layout.addWidget(self.voice_btn)
        button_layout.addWidget(self.send_btn)
        input_layout.addLayout(button_layout)

        self.attachments_label = QLabel("")
        self.attachments_label.setVisible(False)
        self.attachments_label.setStyleSheet("""
            QLabel {
                color: #5f5f5f;
                font-family: 'Poppins';
                font-size: 11px;
                font-weight: 400;
                padding-left: 2px;
            }
        """)
        input_layout.addWidget(self.attachments_label, 0, Qt.AlignLeft)

        self.ai_status_label = QLabel("Model: local/rules")
        self.ai_status_label.setVisible(self.show_ai_status)
        self.ai_status_label.setStyleSheet("""
            QLabel {
                color: #7f7f7f;
                font-family: 'Poppins';
                font-size: 11px;
                font-weight: 400;
                padding-left: 2px;
            }
        """)
        input_layout.addWidget(self.ai_status_label, 0, Qt.AlignLeft)
        
        # Center with same rail alignment as conversation messages.
        input_center_layout = QHBoxLayout()
        input_center_layout.setContentsMargins(0, 0, 0, 0)
        input_center_layout.addStretch()
        input_center_layout.addWidget(input_container)
        input_center_layout.addStretch()
        content_layout.addLayout(input_center_layout)

        self.center_bottom_spacer = QWidget()
        self.center_bottom_spacer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.center_bottom_spacer.setVisible(False)
        content_layout.addWidget(self.center_bottom_spacer, 1)
        
        # Add sidebar and content to main layout
        main_layout.addWidget(sidebar)
        main_layout.addWidget(content, 1)  # Content takes remaining space

        # Add body widget to root layout
        root_layout.addWidget(body_widget, 1)

        # Initial update
        self.update_system_info()
        self.update_send_button_state()
        self._update_input_bar_height()
        self.refresh_conversation_list()
        self._update_centered_composer_state(force_weather=True)
        self._update_compact_layout()

    def _position_window_controls(self):
        """Re-position title bar after resize (not needed with layout-based approach)."""
        pass

    def _apply_window_round_mask(self):
        if self.isMaximized() or self.isFullScreen():
            self.clearMask()
            self._set_native_corner_preference(False)
            return
        radius = self.small_window_radius
        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), radius, radius)
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)
        self._set_native_corner_preference(True)

    def _extend_frame_into_client_area(self):
        if os.name != "nt":
            return
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        try:
            class MARGINS(ctypes.Structure):
                _fields_ = [("cxLeftWidth", ctypes.c_int),
                            ("cxRightWidth", ctypes.c_int),
                            ("cyTopHeight", ctypes.c_int),
                            ("cyBottomHeight", ctypes.c_int)]
            margins = MARGINS(-1, -1, -1, -1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
                ctypes.c_void_p(hwnd), ctypes.byref(margins)
            )
        except Exception:
            pass

    def _set_native_corner_preference(self, rounded=True):
        if os.name != "nt":
            return
        try:
            hwnd = int(self.winId())
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_DONOTROUND = 1
            DWMWCP_ROUND = 2
            value = ctypes.c_int(DWMWCP_ROUND if rounded else DWMWCP_DONOTROUND)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:
            # Older Windows versions may not support this attribute.
            pass

    def _apply_windows_blur(self):
        if os.name != "nt":
            return
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        try:
            class ACCENT_POLICY(ctypes.Structure):
                _fields_ = [
                    ("AccentState",   ctypes.c_int),
                    ("AccentFlags",   ctypes.c_int),
                    ("GradientColor", ctypes.c_int),
                    ("AnimationId",   ctypes.c_int),
                ]

            class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
                _fields_ = [
                    ("Attribute",  ctypes.c_int),
                    ("Data",       ctypes.c_void_p),
                    ("SizeOfData", ctypes.c_size_t),
                ]

            accent = ACCENT_POLICY()
            accent.AccentState   = 4          # ACCENT_ENABLE_ACRYLICBLURBEHIND
            accent.AccentFlags   = 0
            accent.GradientColor = 0x00000000 # transparent tint — corners blend naturally
            accent.AnimationId   = 0
            data = WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute  = 19              # WCA_ACCENT_POLICY
            data.Data       = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)
            data.SizeOfData = ctypes.sizeof(accent)
            ctypes.windll.user32.SetWindowCompositionAttribute(
                ctypes.c_void_p(hwnd), ctypes.byref(data)
            )
        except Exception:
            pass
        self._extend_frame_into_client_area()

    def _update_blur_region(self):
        pass  # no-op — blur is handled by _apply_windows_blur

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_compact_layout()
        self._apply_window_round_mask()
        self._reflow_smart_header_layout()

    def changeEvent(self, event):
        if event.type() == event.WindowStateChange:
            self._update_compact_layout()
            self._apply_window_round_mask()
            if hasattr(self, "title_bar") and self.title_bar is not None:
                if self.isMaximized():
                    self.title_bar.max_btn.setIcon(QIcon(self.title_bar._window_btn_icon("restore", 16)))
                else:
                    self.title_bar.max_btn.setIcon(QIcon(self.title_bar._window_btn_icon("max", 16)))
        super().changeEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        panel_rect = self.rect()
        radius = 0 if (self.isMaximized() or self.isFullScreen()) else self.small_window_radius
        panel_path = QPainterPath()
        panel_path.addRoundedRect(QRectF(panel_rect), radius, radius)

        # Erase entire surface to transparent first — corners become truly see-through.
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(panel_rect, Qt.transparent)

        # Paint the frosted glass fill only inside the rounded path.
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setClipPath(panel_path)
        painter.fillRect(panel_rect, QColor(30, 30, 32, 195))

        # No border stroke to avoid extra top/bottom hairlines.


    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.isMaximized():
                edges = self._detect_resize_edges(event.pos())
                if edges:
                    self._resize_active = True
                    self._resize_edges = edges
                    self._resize_start_geo = self.geometry()
                    self._resize_start_pos = event.globalPos()
                elif event.pos().y() <= 42:
                    # Allow dragging from top strip area in frameless mode.
                    self._drag_active = True
                    self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_active and (event.buttons() & Qt.LeftButton) and not self.isMaximized():
            delta = event.globalPos() - self._resize_start_pos
            geo = QRect(self._resize_start_geo)
            min_w = self.minimumWidth()
            min_h = self.minimumHeight()

            if "left" in self._resize_edges:
                new_left = geo.left() + delta.x()
                max_left = geo.right() - min_w + 1
                geo.setLeft(min(new_left, max_left))
            if "right" in self._resize_edges:
                new_width = max(min_w, self._resize_start_geo.width() + delta.x())
                geo.setWidth(new_width)
            if "top" in self._resize_edges:
                new_top = geo.top() + delta.y()
                max_top = geo.bottom() - min_h + 1
                geo.setTop(min(new_top, max_top))
            if "bottom" in self._resize_edges:
                new_height = max(min_h, self._resize_start_geo.height() + delta.y())
                geo.setHeight(new_height)

            self.setGeometry(geo)
            self._position_window_controls()
        elif self._drag_active and (event.buttons() & Qt.LeftButton) and not self.isMaximized():
            self.move(event.globalPos() - self._drag_offset)
        elif not self.isMaximized():
            self._apply_resize_cursor(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_active = False
        self._resize_active = False
        self._resize_edges = set()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if not self._resize_active and not self._drag_active:
            self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() <= 42:
            if self.isMaximized():
                self.showNormal()
                if hasattr(self, "title_bar") and self.title_bar is not None:
                    self.title_bar.max_btn.setText("▢")
            else:
                self.showMaximized()
                if hasattr(self, "title_bar") and self.title_bar is not None:
                    self.title_bar.max_btn.setText("❐")
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            event.ignore()
            return
        paths = []
        for url in mime.urls():
            try:
                if not url.isLocalFile():
                    continue
                local_path = url.toLocalFile()
                if local_path:
                    paths.append(local_path)
            except Exception:
                continue
        if paths:
            self._add_attachments(paths)
            self.update_send_button_state()
            event.acceptProposedAction()
            return
        event.ignore()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
            event.accept()
            return
        super().keyPressEvent(event)

    def _detect_resize_edges(self, pos):
        edges = set()
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = self._resize_margin
        if x <= m:
            edges.add("left")
        elif x >= w - m:
            edges.add("right")
        if y <= m:
            edges.add("top")
        elif y >= h - m:
            edges.add("bottom")
        return edges

    def _apply_resize_cursor(self, pos):
        edges = self._detect_resize_edges(pos)
        if edges == {"left"} or edges == {"right"}:
            self.setCursor(Qt.SizeHorCursor)
        elif edges == {"top"} or edges == {"bottom"}:
            self.setCursor(Qt.SizeVerCursor)
        elif edges == {"left", "top"} or edges == {"right", "bottom"}:
            self.setCursor(Qt.SizeFDiagCursor)
        elif edges == {"right", "top"} or edges == {"left", "bottom"}:
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def log_conversation(self, role, text):
        """Print and persist conversation to PowerShell/file."""
        def _redact_secrets(value):
            s = str(value or "")
            # Redact common API key patterns and bearer tokens.
            s = re.sub(r"\bsk-[A-Za-z0-9_\-]{12,}\b", "[REDACTED_API_KEY]", s)
            s = re.sub(
                r"\b(?:GROQ_API_KEY|DEEPSEEK_API_KEY|ALIBABA_MODEL_STUDIO_API_KEY|DASHSCOPE_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY)\s*=\s*([^\s\"']+)",
                lambda m: m.group(0).split("=")[0] + "=[REDACTED]",
                s,
                flags=re.IGNORECASE,
            )
            s = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9_\-\.=]+\b", "Bearer [REDACTED]", s)
            return s

        safe_text = _redact_secrets(text)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {role}: {safe_text}"
        print(line)
        try:
            os.makedirs(os.path.dirname(self.conversation_log_file), exist_ok=True)
            with open(self.conversation_log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"[{timestamp}] LOG_ERROR: {e}")

    def update_send_button_state(self):
        """Enable send only when there is text and input is editable."""
        if self.send_btn is None:
            return
        has_text = bool(self.input_field.toPlainText().strip())
        has_attachments = bool(self.pending_attachments)
        self.send_btn.setEnabled((has_text or has_attachments) and self.input_field.isEnabled())

    def _update_input_bar_height(self):
        if self.input_container is None or self.input_field is None:
            return
        doc_height = self.input_field.document().size().height()
        pad_top_bottom = 12
        min_text_h = 66
        max_text_h = 180
        target_text_h = int(min(max(doc_height + pad_top_bottom, min_text_h), max_text_h))
        if self.input_field.height() != target_text_h:
            self.input_field.setFixedHeight(target_text_h)

        extra_ui = 64  # buttons + labels spacing
        min_container_h = 130
        max_container_h = 240
        target_container_h = int(min(max(target_text_h + extra_ui, min_container_h), max_container_h))
        if self.input_container.height() != target_container_h:
            self.input_container.setFixedHeight(target_container_h)
    
    def add_message(self, text, is_user=True):
        """Add message to active mode layout"""
        bubble = MessageBubble(text, is_user)
        active_layout = self.task_layout if self.current_mode == "task" else self.chat_layout
        active_layout.insertWidget(active_layout.count() - 1, bubble)
        if is_user:
            if self.current_mode == "task":
                self.last_user_bubble_task = bubble
            else:
                self.last_user_bubble_chat = bubble
            self._place_activity_indicator()
        # Scroll to bottom
        QTimer.singleShot(100, self.scroll_to_bottom)
        return bubble

    def _clear_layout_preserve_indicator(self, layout, indicator):
        preserved = None
        while layout.count() > 1:
            item = layout.takeAt(0)
            w = item.widget()
            if w is None:
                continue
            if indicator is not None and w is indicator:
                preserved = w
                continue
            w.deleteLater()
        if preserved is not None:
            layout.insertWidget(layout.count() - 1, preserved)

    def _last_user_message_text(self):
        active_conv = self.current_task_conversation if self.current_mode == "task" else self.current_conversation
        for msg in reversed(active_conv):
            if msg.get("role") == "user":
                return msg.get("text", "")
        return ""

    def _submit_feedback(self, rating, assistant_text, row=None, correction_text=""):
        if not bool(getattr(self.agent, "feedback_enabled", True)):
            return
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "rating": rating,
            "assistant": assistant_text,
            "user": self._last_user_message_text(),
            "correction": correction_text or "",
            "session_id": self.current_task_session_id if self.current_mode == "task" else self.current_session_id,
        }
        ok = False
        if hasattr(self.agent, "record_feedback"):
            try:
                ok = self.agent.record_feedback(payload)
            except Exception:
                ok = False
        if ok and row is not None:
            row.set_selected(rating)

    def add_authorization_prompt(self, command):
        self.clear_authorization_prompt()
        prompt = AuthorizationPromptWidget(
            command=command,
            on_allow=self.on_sensitive_operation_allowed,
            on_deny=self.on_sensitive_operation_denied,
        )
        self.pending_auth_widget = prompt
        active_layout = self.task_layout if self.current_mode == "task" else self.chat_layout
        active_layout.insertWidget(active_layout.count() - 1, prompt)
        QTimer.singleShot(100, self.scroll_to_bottom)

    def clear_authorization_prompt(self):
        if self.pending_auth_widget is not None:
            self.pending_auth_widget.deleteLater()
            self.pending_auth_widget = None

    def on_sensitive_operation_allowed(self):
        command = self.pending_sensitive_command
        self.pending_sensitive_command = None
        self.clear_authorization_prompt()
        if not command:
            return
        self.log_conversation("SYSTEM", f"Authorized sensitive operation: {command}")
        # Auto-switch to task mode if the command is a task (same logic as send_message)
        if self.current_mode == "chat" and self._detect_task_command(command):
            self._switch_mode("task")
        # Prepend MODE_TASK:: so agent knows mode context, then AUTH_OK:: for permission
        if self.current_mode == "task":
            self.run_worker_command("MODE_TASK::AUTH_OK::" + command)
        else:
            self.run_worker_command("AUTH_OK::" + command)

    def on_sensitive_operation_denied(self):
        command = self.pending_sensitive_command
        self.pending_sensitive_command = None
        self.clear_authorization_prompt()
        self.add_message("Sensitive operation denied.", False)
        if command:
            self.log_conversation("SYSTEM", f"Denied sensitive operation: {command}")

    def _place_activity_indicator(self):
        if self.chat_activity_indicator is None or self.task_activity_indicator is None:
            return
        if self.current_mode == "task":
            indicator = self.task_activity_indicator
            layout = self.task_layout
            anchor = self.last_user_bubble_task
        else:
            indicator = self.chat_activity_indicator
            layout = self.chat_layout
            anchor = self.last_user_bubble_chat

        if indicator is None or layout is None:
            return

        try:
            layout.removeWidget(indicator)
        except Exception:
            pass

        insert_index = layout.count() - 1
        if anchor is not None:
            idx = layout.indexOf(anchor)
            if idx >= 0:
                insert_index = idx + 1
        try:
            layout.insertWidget(insert_index, indicator)
        except RuntimeError:
            # Indicator might have been deleted during layout reset; recreate and insert.
            if self.current_mode == "task":
                self.task_activity_indicator = ThinkingIndicator()
                indicator = self.task_activity_indicator
            else:
                self.chat_activity_indicator = ThinkingIndicator()
                indicator = self.chat_activity_indicator
            indicator.set_active(False)
            layout.insertWidget(insert_index, indicator)

    def _set_phase_label(self, label):
        if self.current_mode == "task":
            self.task_activity_indicator.set_phrase(label)
        else:
            self.chat_activity_indicator.set_phrase(label)
        self._phase_hold_until = time.time() + (self._phase_min_ms / 1000.0)

    def _flush_pending_phase(self):
        if self._pending_phase_label:
            self._set_phase_label(self._pending_phase_label)
            self._pending_phase_label = None

    def _allow_generating_label(self):
        if self.current_mode == "task":
            return True
        last_text = self._last_user_message_text()
        return bool(self._gen_label_re.search(last_text or ""))

    def _queue_phase_label(self, label):
        now = time.time()
        if label != "Thinking" and now < self._phase_lock_until:
            self._pending_phase_label = label
            delay_ms = max(10, int((self._phase_lock_until - now) * 1000))
            self._phase_timer.start(delay_ms)
            return
        if now < self._phase_hold_until:
            self._pending_phase_label = label
            delay_ms = max(10, int((self._phase_hold_until - now) * 1000))
            self._phase_timer.start(delay_ms)
            return
        self._set_phase_label(label)

    def _set_activity_indicator(self, active):
        if self.chat_activity_indicator is None or self.task_activity_indicator is None:
            return
        if not active:
            self.chat_activity_indicator.set_active(False)
            self.task_activity_indicator.set_active(False)
            self.chat_activity_indicator.set_phrase(None)
            self.task_activity_indicator.set_phrase(None)
            self._pending_phase_label = None
            if self._phase_timer:
                self._phase_timer.stop()
            return
        if self.current_mode == "task":
            self.task_activity_indicator.set_active(True)
            self.chat_activity_indicator.set_active(False)
        else:
            self.chat_activity_indicator.set_active(True)
            self.task_activity_indicator.set_active(False)
        if self.current_mode == "task":
            self._set_phase_label("Thinking")
        else:
            self._set_phase_label("Thinking")
        self._phase_lock_until = time.time() + 1.4
        self._place_activity_indicator()
        QTimer.singleShot(80, self.scroll_to_bottom)

    def _refresh_activity_indicator_on_mode_change(self):
        worker_busy = self.worker is not None and self.worker.isRunning()
        self._set_activity_indicator(worker_busy)

    def run_worker_command(self, worker_command):
        self.input_field.setEnabled(False)
        self.update_send_button_state()
        self._set_activity_indicator(True)
        if self.ai_status_label is not None and self.show_ai_status:
            self.ai_status_label.setText("Model: processing...")
        # Mute mic while AI is generating — prevents hallucinations from background or TTS echo
        if self.voice_thread is not None and self.voice_thread.isRunning():
            self.voice_thread.mute_for(60)  # released (with cooldown) once response arrives
        self.worker = WorkerThread(self.agent, worker_command)
        self.worker.finished.connect(self.on_response)
        self.worker.runtime_meta.connect(self.on_worker_runtime_meta)
        self.worker.start()

    def on_worker_runtime_meta(self, meta):
        phase = (meta or {}).get("phase")
        if phase:
            phase_map = {
                "thinking": "Thinking",
            }
            label = phase_map.get(phase, None)
            if label:
                self._queue_phase_label(label)
        if self.ai_status_label is None or not self.show_ai_status:
            return
        provider = (meta or {}).get("provider", "unknown")
        model = (meta or {}).get("model", "unknown")
        status = (meta or {}).get("status", "")
        if status and status != "ok":
            self.ai_status_label.setText(f"Model: {provider}/{model} ({status})")
            return
        self.ai_status_label.setText(f"Model: {provider}/{model}")

    def _set_voice_button_state(self, listening):
        if self.voice_btn is None:
            return
        if listening:
            self.voice_btn.setEnabled(True)
            self.voice_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a1f1f;
                    border: none;
                    border-radius: 22px;
                }
                QPushButton:hover {
                    background-color: #4a2a2a;
                }
            """)
            self.voice_btn.setToolTip("Stop microphone")
        else:
            self.voice_btn.setEnabled(True)
            self.voice_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1f1f1f;
                    border: none;
                    border-radius: 22px;
                }
                QPushButton:hover {
                    background-color: #2a2a2a;
                }
                QPushButton:disabled {
                    background-color: #1b1b1b;
                    border: none;
                }
            """)
            self.voice_btn.setToolTip("Start microphone")

    def toggle_voice_input(self):
        if self.voice_thread is not None and self.voice_thread.isRunning():
            self.stop_voice_input()
            return
        self.start_voice_input()

    def open_data_folder(self):
        data_dir = self._get_data_dir()
        try:
            os.makedirs(data_dir, exist_ok=True)
            os.startfile(data_dir)
        except Exception as exc:
            msg = QMessageBox(self)
            msg.setWindowTitle("Open Data Folder")
            msg.setIcon(QMessageBox.Warning)
            msg.setText("Could not open the data folder.")
            msg.setInformativeText(str(exc))
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()

    def open_attachment_menu(self):
        if self.attach_btn is None:
            return
        menu = QMenu(self)
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint)
        add_files = menu.addAction("Add files...")
        add_folder = menu.addAction("Add folder...")
        clear_all = menu.addAction("Clear attachments")
        action = menu.exec_(self.attach_btn.mapToGlobal(self.attach_btn.rect().bottomLeft()))
        if action == add_files:
            self.add_files()
        elif action == add_folder:
            self.add_folder()
        elif action == clear_all:
            self.clear_attachments()

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select files",
            os.path.expanduser("~"),
            "All Files (*.*)",
        )
        if paths:
            self._add_attachments(paths)

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select folder",
            os.path.expanduser("~"),
        )
        if folder:
            self._add_attachments([folder])

    def clear_attachments(self):
        self.pending_attachments = []
        self._update_attachments_label()

    def _add_attachments(self, paths):
        for p in paths:
            if p and p not in self.pending_attachments:
                self.pending_attachments.append(p)
        self._update_attachments_label()

    def _update_attachments_label(self):
        if self.attachments_label is None:
            return
        if not self.pending_attachments:
            self.attachments_label.setVisible(False)
            self.attachments_label.setText("")
            return
        names = [os.path.basename(p.rstrip("\\/")) or p for p in self.pending_attachments]
        display = ", ".join(names[:4])
        if len(names) > 4:
            display += f" … (+{len(names) - 4})"
        self.attachments_label.setText(f"Attachments: {display}")
        self.attachments_label.setVisible(True)

    def start_voice_input(self):
        if self.voice_thread is not None and self.voice_thread.isRunning():
            return
        self.voice_listening = True
        self._set_voice_button_state(True)
        self.voice_thread = VoiceInputThread(timeout=2.0, phrase_time_limit=20, agent=self.agent)
        self.voice_thread.transcribed.connect(self.on_voice_transcribed)
        self.voice_thread.error.connect(self.on_voice_error)
        self.voice_thread.finished.connect(self.on_voice_finished)
        self.voice_thread.start()

    def stop_voice_input(self):
        if self.voice_thread is not None and self.voice_thread.isRunning():
            try:
                self.voice_thread.stop_listening()
            except Exception:
                pass
        self.voice_listening = False
        self._set_voice_button_state(False)

    def on_voice_transcribed(self, text):
        spoken = (text or "").strip()
        if not spoken:
            return
        existing = self.input_field.toPlainText().strip()
        if existing:
            self.input_field.setPlainText(existing + " " + spoken)
        else:
            self.input_field.setPlainText(spoken)
        self.input_field.setFocus()
        self.update_send_button_state()

    def on_voice_error(self, message):
        self.add_message(message or "Voice input failed.", False)

    def on_voice_finished(self):
        self.voice_listening = False
        self._set_voice_button_state(False)
        self.voice_thread = None

    def _capture_shared_screen_frame(self, force=False):
        try:
            now = time.time()
            if (not force) and self.latest_screen_path and (now - self.last_screen_capture_ts < 1.6):
                return self.latest_screen_path
            os.makedirs(self.screen_capture_dir, exist_ok=True)
            ext = "jpg" if self.screen_capture_format in {"jpg", "jpeg"} else "png"
            path = os.path.join(self.screen_capture_dir, f"latest.{ext}")
            img = pyautogui.screenshot()
            # Keep higher detail for text readability during shared-screen reasoning.
            max_w, max_h = self.screen_capture_max_w, self.screen_capture_max_h
            if hasattr(img, "thumbnail"):
                img.thumbnail((max_w, max_h))
            if ext == "jpg":
                img.save(
                    path,
                    format="JPEG",
                    quality=max(60, min(95, self.screen_capture_jpeg_quality)),
                    optimize=True,
                )
            else:
                img.save(path, format="PNG", optimize=True)
            self.latest_screen_path = path
            self.last_screen_capture_ts = now
            return path
        except Exception as e:
            self.log_conversation("SYSTEM", f"Screen share capture failed: {e}")
            return ""

    def _set_screen_share_ui_state(self):
        if self.share_btn is None:
            return
        if self.screen_share_enabled:
            self.share_btn.setText("Live off")
            self.share_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0f3b22;
                    color: #ffffff;
                    font-family: 'Poppins';
                    font-size: 13px;
                    font-weight: 500;
                    border: none;
                    border-radius: 20px;
                }
                QPushButton:hover { background-color: #14512f; }
            """)
        else:
            self.share_btn.setText("Live")
            self.share_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1f1f1f;
                    color: #ffffff;
                    font-family: 'Poppins';
                    font-size: 13px;
                    font-weight: 500;
                    border: none;
                    border-radius: 20px;
                }
                QPushButton:hover { background-color: #2a2a2a; }
            """)

    def toggle_screen_share(self):
        self.screen_share_enabled = not self.screen_share_enabled
        if self.screen_share_enabled:
            self.enable_compact_chat_mode()
            QApplication.processEvents()
            if self.screen_share_overlay is None:
                self.screen_share_overlay = ScreenShareOverlay()
            self.screen_share_overlay.cover_primary_screen()
            self.screen_share_overlay.show()
            self.screen_share_overlay.start_animation()
            self.screen_share_overlay.raise_()
            self._capture_shared_screen_frame(force=True)
            self.add_message("Screen sharing enabled. Green border means live share is active.", False)
            self.log_conversation("SYSTEM", "Screen sharing enabled.")
        else:
            self.disable_screen_share()
            return
        self._set_screen_share_ui_state()

    def disable_screen_share(self):
        self.screen_share_enabled = False
        if self.screen_share_overlay is not None:
            self.screen_share_overlay.stop_animation()
            self.screen_share_overlay.hide()
        self.disable_compact_chat_mode()
        self._set_screen_share_ui_state()
        self.add_message("Screen sharing stopped.", False)
        self.log_conversation("SYSTEM", "Screen sharing disabled.")

    def _set_always_on_top(self, enabled):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(enabled))
        self.show()

    def _update_compact_layout(self):
        is_small = self.compact_mode_active or self.width() <= 980
        if self.sidebar_widget is not None:
            self.sidebar_widget.setVisible(not is_small)
        if self.input_container is not None:
            # Keep chat bar fully visible at every size.
            sidebar_w = self.sidebar_expanded_width if (self.sidebar_widget is not None and self.sidebar_widget.isVisible()) else 0
            available = self.width() - sidebar_w - 96
            target_width = max(300, min(870, available))
            self.input_container.setFixedWidth(target_width)
        if self.main_widget is not None:
            self.main_widget.setStyleSheet(
                f"font-family: '{self.ui_font_family}';"
            )
        self._apply_window_round_mask()
        self.update()

    def enable_compact_chat_mode(self):
        if self.pre_share_geometry is None:
            self.pre_share_geometry = self.geometry()
            self.pre_share_topmost = bool(self.windowFlags() & Qt.WindowStaysOnTopHint)
            self.pre_share_min_size = self.minimumSize()
            self.pre_share_sidebar_open = bool(self.sidebar_is_open)
        self.compact_mode_active = True
        self.setMinimumSize(420, 360)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            width = min(500, max(430, int(avail.width() * 0.28)))
            height = min(620, max(380, int(avail.height() * 0.48)))
            x = avail.x() + avail.width() - width - 18
            y = avail.y() + 18
            self.setGeometry(x, y, width, height)
        self._update_compact_layout()
        self._set_always_on_top(True)

    def disable_compact_chat_mode(self):
        self._set_always_on_top(self.pre_share_topmost)
        self.compact_mode_active = False
        if self.pre_share_geometry is not None:
            self.setGeometry(self.pre_share_geometry)
        if self.pre_share_min_size is not None:
            self.setMinimumSize(self.pre_share_min_size)
        self.pre_share_geometry = None
        self.pre_share_topmost = False
        self.pre_share_min_size = None
        self.pre_share_sidebar_open = None
        self._update_compact_layout()
    
    def scroll_to_bottom(self):
        """Scroll chat to bottom"""
        scroll_area = self.findChild(QScrollArea)
        if scroll_area:
            scroll_area.verticalScrollBar().setValue(
                scroll_area.verticalScrollBar().maximum()
            )

    def _sidebar_toggle_icon_pixmap(self, size=16, is_open=True):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        icon_color = QColor("#8A8A8A")
        pen = QPen(icon_color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        outer = QRectF(1.5, 1.5, size - 3.0, size - 3.0)
        painter.drawRoundedRect(outer, 3.0, 3.0)
        bar_w = max(3.0, size * 0.22)
        x = 2.5 if is_open else (size - 2.5 - bar_w)
        painter.fillRect(QRectF(x, 2.5, bar_w, size - 5.0), icon_color)
        painter.end()
        return pix

    def load_chat_sessions(self):
        try:
            if os.path.exists(self.chat_sessions_file):
                with open(self.chat_sessions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.chat_sessions = data[-self.max_chat_sessions:]
                    changed = False
                    for s in self.chat_sessions:
                        if isinstance(s, dict) and not s.get("id"):
                            s["id"] = str(uuid.uuid4())
                            changed = True
                    if changed:
                        self.save_chat_sessions()
        except Exception:
            self.chat_sessions = []

    def load_task_sessions(self):
        try:
            if os.path.exists(self.task_sessions_file):
                with open(self.task_sessions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.task_sessions = data[-self.max_chat_sessions:]
                    changed = False
                    for s in self.task_sessions:
                        if isinstance(s, dict) and not s.get("id"):
                            s["id"] = str(uuid.uuid4())
                            changed = True
                    if changed:
                        self.save_task_sessions()
        except Exception:
            self.task_sessions = []

    def save_chat_sessions(self):
        try:
            os.makedirs(os.path.dirname(self.chat_sessions_file), exist_ok=True)
            with open(self.chat_sessions_file, "w", encoding="utf-8") as f:
                json.dump(self.chat_sessions[-self.max_chat_sessions:], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def save_task_sessions(self):
        try:
            os.makedirs(os.path.dirname(self.task_sessions_file), exist_ok=True)
            with open(self.task_sessions_file, "w", encoding="utf-8") as f:
                json.dump(self.task_sessions[-self.max_chat_sessions:], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _conversation_title(self, messages, fallback_title="New chat"):
        if not messages:
            return fallback_title
        candidate = ""
        for msg in reversed(messages):
            if msg.get("role") == "user" and msg.get("text"):
                candidate = msg.get("text", "")
                break
        if not candidate:
            candidate = messages[-1].get("text", "")
        candidate = (candidate or "").strip().replace("\n", " ")
        return candidate[:60] if candidate else fallback_title

    def _archive_current_chat(self):
        if not self.current_conversation:
            return
        messages = [dict(m) for m in self.current_conversation]
        title = self._conversation_title(messages)
        now_ts = datetime.now().isoformat(timespec="seconds")

        if self.current_session_id and not self.current_conversation_dirty:
            return

        if self.current_session_id:
            for idx, s in enumerate(self.chat_sessions):
                if s.get("id") == self.current_session_id:
                    self.chat_sessions[idx]["title"] = title
                    self.chat_sessions[idx]["saved_at"] = now_ts
                    self.chat_sessions[idx]["messages"] = messages
                    updated = self.chat_sessions.pop(idx)
                    self.chat_sessions.insert(0, updated)
                    self.chat_sessions = self.chat_sessions[: self.max_chat_sessions]
                    self.save_chat_sessions()
                    self.refresh_conversation_list()
                    self.current_conversation_dirty = False
                    return

        new_id = str(uuid.uuid4())
        self.chat_sessions.insert(
            0,
            {
                "id": new_id,
                "title": title,
                "saved_at": now_ts,
                "messages": messages,
            },
        )
        self.current_session_id = new_id
        self.chat_sessions = self.chat_sessions[: self.max_chat_sessions]
        self.save_chat_sessions()
        self.refresh_conversation_list()
        self.current_conversation_dirty = False

    def _archive_current_task(self):
        if not self.current_task_conversation:
            return
        messages = [dict(m) for m in self.current_task_conversation]
        title = self._conversation_title(messages, "New task")
        now_ts = datetime.now().isoformat(timespec="seconds")

        if self.current_task_session_id and not self.current_conversation_dirty:
            return

        if self.current_task_session_id:
            for idx, s in enumerate(self.task_sessions):
                if s.get("id") == self.current_task_session_id:
                    self.task_sessions[idx]["title"] = title
                    self.task_sessions[idx]["saved_at"] = now_ts
                    self.task_sessions[idx]["messages"] = messages
                    updated = self.task_sessions.pop(idx)
                    self.task_sessions.insert(0, updated)
                    self.task_sessions = self.task_sessions[: self.max_chat_sessions]
                    self.save_task_sessions()
                    self.refresh_conversation_list()
                    self.current_conversation_dirty = False
                    return

        new_id = str(uuid.uuid4())
        self.task_sessions.insert(
            0,
            {
                "id": new_id,
                "title": title,
                "saved_at": now_ts,
                "messages": messages,
            },
        )
        self.current_task_session_id = new_id
        self.task_sessions = self.task_sessions[: self.max_chat_sessions]
        self.save_task_sessions()
        self.refresh_conversation_list()
        self.current_conversation_dirty = False

    def _find_session_index(self, session_id):
        sessions = self.task_sessions if self.current_mode == "task" else self.chat_sessions
        if not session_id:
            return None
        for idx, s in enumerate(sessions):
            if s.get("id") == session_id:
                return idx
        return None

    def refresh_conversation_list(self):
        if self.conversation_list is None:
            return
        sessions = self.task_sessions if self.current_mode == "task" else self.chat_sessions
        default_title = "New task" if self.current_mode == "task" else "New chat"
        self.conversation_list.clear()
        for s in sessions:
            sid = s.get("id")
            item = QListWidgetItem()
            item.setData(Qt.UserRole, sid)
            item.setSizeHint(QSize(0, 38))
            self.conversation_list.addItem(item)

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 0, 2, 0)
            row_layout.setSpacing(6)
            title_lbl = QLabel(s.get("title", default_title))
            title_lbl.setStyleSheet(f"color: {self.text_primary}; font-family: 'Poppins'; font-size: 13px; font-weight: 500;")

            menu_btn = QPushButton("...")
            menu_btn.setCursor(Qt.PointingHandCursor)
            menu_btn.setFocusPolicy(Qt.NoFocus)
            menu_btn.setFixedSize(28, 24)
            menu_btn.setStyleSheet(
                "QPushButton { background: transparent; color: #fff; border: none; border-radius: 6px; }"
                "QPushButton:hover { background: #2a2a2a; }"
            )
            menu_btn.clicked.connect(lambda _=False, sid=sid, btn=menu_btn: self.show_conversation_actions(sid, btn))
            row_layout.addWidget(title_lbl, 1)
            row_layout.addWidget(menu_btn, 0, Qt.AlignRight)
            self.conversation_list.setItemWidget(item, row)

        count = self.conversation_list.count()
        if count <= 0 or not self.sidebar_is_open:
            self.conversation_list.setVisible(False)
            self.conversation_list.setMinimumHeight(0)
            self.conversation_list.setMaximumHeight(0)
            return
        row_h = self.conversation_list.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 28
        h = (row_h * min(count, 5)) + (self.conversation_list.frameWidth() * 2) + 2
        self.conversation_list.setVisible(True)
        self.conversation_list.setMinimumHeight(h)
        self.conversation_list.setMaximumHeight(h)

    def on_conversation_clicked(self, item):
        if item is None:
            return
        idx = self._find_session_index(item.data(Qt.UserRole))
        if idx is None:
            return
        if self.current_mode == "task":
            messages = self.task_sessions[idx].get("messages", [])
            self._clear_layout_preserve_indicator(self.task_layout, self.task_activity_indicator)
            self.last_user_bubble_task = None
            self.current_task_conversation = []
            self.current_task_session_id = self.task_sessions[idx].get("id")
        else:
            messages = self.chat_sessions[idx].get("messages", [])
            self._clear_layout_preserve_indicator(self.chat_layout, self.chat_activity_indicator)
            self.last_user_bubble_chat = None
            self.current_conversation = []
            self.current_session_id = self.chat_sessions[idx].get("id")
        self.current_conversation_dirty = False
        for msg in messages:
            txt = msg.get("text", "")
            if txt:
                is_user = msg.get("role") == "user"
                self.add_message(txt, is_user)
                entry = {"role": "user" if is_user else "assistant", "text": txt, "time": msg.get("time", "")}
                if self.current_mode == "task":
                    self.current_task_conversation.append(entry)
                else:
                    self.current_conversation.append(entry)
        self._update_centered_composer_state()

    def show_conversation_actions(self, session_id, button):
        idx = self._find_session_index(session_id)
        if idx is None:
            return
        menu = QMenu(self)
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint)
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec_(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen == rename_action:
            self.rename_conversation(session_id)
        elif chosen == delete_action:
            self.delete_conversation(session_id)

    def rename_conversation(self, session_id):
        idx = self._find_session_index(session_id)
        if idx is None:
            return
        sessions = self.task_sessions if self.current_mode == "task" else self.chat_sessions
        current_title = sessions[idx].get("title", "New task" if self.current_mode == "task" else "New chat")
        new_title, ok = QInputDialog.getText(self, "Rename Conversation", "Conversation name:", text=current_title)
        if not ok:
            return
        new_title = (new_title or "").strip()
        if not new_title:
            return
        sessions[idx]["title"] = new_title[:60]
        sessions[idx]["saved_at"] = datetime.now().isoformat(timespec="seconds")
        if self.current_mode == "task":
            self.save_task_sessions()
        else:
            self.save_chat_sessions()
        self.refresh_conversation_list()

    def delete_conversation(self, session_id):
        idx = self._find_session_index(session_id)
        if idx is None:
            return
        sessions = self.task_sessions if self.current_mode == "task" else self.chat_sessions
        removed = sessions.pop(idx)
        if self.current_mode == "task":
            self.save_task_sessions()
        else:
            self.save_chat_sessions()
        self.refresh_conversation_list()
        if self.current_mode == "task":
            if removed.get("id") == self.current_task_session_id:
                self._clear_layout_preserve_indicator(self.task_layout, self.task_activity_indicator)
                self.last_user_bubble_task = None
                self.current_task_conversation = []
                self.current_task_session_id = None
                self.current_conversation_dirty = False
        else:
            if removed.get("id") == self.current_session_id:
                self._clear_layout_preserve_indicator(self.chat_layout, self.chat_activity_indicator)
                self.last_user_bubble_chat = None
                self.current_conversation = []
                self.current_session_id = None
                self.current_conversation_dirty = False
        self._update_centered_composer_state(force_weather=True)

    def toggle_sidebar(self):
        # Sidebar collapsing was removed by request.
        return

    def _looks_like_file_operation(self, command):
        text = (command or "").strip().lower()
        if not text:
            return False
        text = re.sub(r"^\s*(can you|could you|would you|please|pls|plz)\s+", "", text, flags=re.IGNORECASE)
        patterns = [
            r"^(list|show)\s+(all\s+)?files",
            r"^(list|show|see)\s+(all\s+)?(files|folders|items).*(desktop)",
            r"^what('?s| is)\s+on\s+.*desktop",
            r"^(read|open|show)\s+file\s+",
            r"^(create|make)\s+(file|folder|directory)\s+",
            r"^(create|make)\s+(a|an)\s+(file|folder|directory)\s+",
            r"^(create|make)\s+(a|an)\s+new\s+(file|folder|directory)\s+",
            r"^(delete|remove)\s+(file|folder|directory)?\s*",
            r"^(write|overwrite|replace)\s+(to\s+)?file\s+",
            r"^(append|add)\s+(to\s+)?file\s+",
            r"^(rename)\s+(file|folder|directory)?\s*.+\s+to\s+.+",
            r"^(move|copy)\s+(file|folder|directory)?\s*.+\s+to\s+.+",
        ]
        return any(re.match(p, text, flags=re.IGNORECASE) for p in patterns)

    def _needs_sensitive_fs_authorization(self, command):
        raw_lower = (command or "").strip().lower()
        if not raw_lower:
            return False
        lower = re.sub(r"^\s*(can you|could you|would you|please|pls|plz)\s+", "", raw_lower, flags=re.IGNORECASE)

        def _has_explicit_target(text):
            if re.search(r'["\']\s*[^"\']+\s*["\']', text):
                return True
            if re.search(r'\b(named|called|titled?|file\s+name|folder\s+name)\b', text):
                return True
            if re.search(r'[a-zA-Z]:\\', text):
                return True
            if re.search(r'\.[a-z0-9]{2,5}\b', text):
                return True
            if re.search(r'\b(on|in|inside|into)\s+(the\s+)?(desktop|documents|downloads|folder|drive|c:|d:|e:)\b', text):
                return True
            return False

        is_question = bool(
            re.search(r'^\s*(can you|could you|would you|are you able to|is it possible to)\b', raw_lower)
            or raw_lower.endswith("?")
        )
        if is_question and not _has_explicit_target(lower):
            return False

        # Always gate app-closing commands.
        if re.search(r"\b(close|quit|exit|terminate|kill)\b", lower):
            return True

        # Always gate create/delete file-system operations.
        if re.search(r"\b(create|make)\b", lower) and re.search(r"\b(file|folder|directory)\b", lower):
            return True
        # Gate any file-generation command: pdf, word, pptx, txt, etc.
        _doc_verbs = r"\b(create|make|write|generate|save|produce|build|export|prepare|draft|give|put|turn|convert)\b"
        _doc_types = r"\b(word|docx?|document|pdf|pptx?|pow[a-z]*oint|presentation|slides?|slide\s+deck|txt|note\s+file|text\s+file|xlsx?|excell?|spreadsheet|spread\s+sheet|google\s+sheets?|gsheet)\b"
        _last_ref  = r"\b(what\s+(you|i|we)\s+(have\s+)?(sent|said|wrote|given)|the\s+last\s+response|your\s+last|last\s+message)\b"
        if re.search(_doc_verbs, lower) and (re.search(_doc_types, lower) or re.search(_last_ref, lower)):
            return True
        if re.search(r"\b(delete|remove)\b", lower):
            return True

        # Keep previous behavior for other file operations targeting sensitive paths.
        if not self._looks_like_file_operation(command):
            return False
        return ("desktop" in lower) or bool(re.search(r"[a-zA-Z]:\\", command or ""))

    def _confirm_sensitive_fs_operation(self, command):
        msg = QMessageBox(self)
        msg.setWindowTitle("Authorization Required")
        msg.setIcon(QMessageBox.Warning)
        msg.setText("Allow this sensitive file operation?")
        msg.setInformativeText((command or "").strip()[:300])
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        msg.button(QMessageBox.Yes).setText("Allow")
        msg.button(QMessageBox.No).setText("Deny")
        return msg.exec_() == QMessageBox.Yes

    def _normalize_for_icon_lookup(self, app_name):
        if hasattr(self, "agent") and hasattr(self.agent, "_normalize_app_name"):
            return self.agent._normalize_app_name(app_name)
        cleaned = re.sub(r"\.(exe|lnk|url|appref-ms)$", "", (app_name or "").lower().strip())
        cleaned = re.sub(r"[\(\)\[\]\{\}\-_,.:]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _resolve_running_app_icon_path(self, app_name):
        target = self._normalize_for_icon_lookup(app_name)
        if not target:
            return None

        aliases = {target}
        alias_map = {
            "google chrome": ["chrome"],
            "microsoft edge": ["edge", "msedge"],
            "vs code": ["code", "vscode"],
            "file explorer": ["explorer"],
            "command prompt": ["cmd"],
            "windows terminal": ["wt", "terminal"],
        }
        for alias in alias_map.get(target, []):
            aliases.add(alias)
        # Heuristic aliases for noisy window-title names.
        token_aliases = {
            "chrome": ["chrome", "google chrome"],
            "edge": ["edge", "msedge", "microsoft edge"],
            "firefox": ["firefox", "mozilla firefox"],
            "brave": ["brave"],
            "cursor": ["cursor"],
            "visual studio code": ["code", "vscode", "vs code"],
            "code": ["code", "vscode", "vs code"],
            "discord": ["discord"],
            "telegram": ["telegram"],
            "whatsapp": ["whatsapp"],
            "explorer": ["explorer", "file explorer"],
            "powershell": ["powershell"],
            "pwsh": ["powershell"],
            "terminal": ["wt", "terminal", "windows terminal"],
            "wt": ["wt", "terminal", "windows terminal"],
            "spotify": ["spotify"],
            "slack": ["slack"],
            "teams": ["teams", "microsoft teams"],
            "zoom": ["zoom"],
            "figma": ["figma"],
            "notepad": ["notepad"],
            "calculator": ["calculator", "calc"],
            "calc": ["calculator", "calc"],
            "settings": ["settings", "systemsettings"],
            "systemsettings": ["settings"],
            "steam": ["steam"],
            "vlc": ["vlc"],
            "copilot": ["copilot"],
            "outlook": ["outlook", "microsoft outlook"],
            "winword": ["word", "microsoft word"],
            "excel": ["excel", "microsoft excel"],
            "powerpnt": ["powerpoint", "microsoft powerpoint"],
            "photoshop": ["photoshop", "adobe photoshop"],
        }
        for token, values in token_aliases.items():
            if token in target:
                aliases.update(values)

        # Prefer known executable paths for apps with unstable process/window names.
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        win_dir = os.environ.get("WINDIR", r"C:\Windows")
        sys32 = os.path.join(win_dir, "System32")

        known_icon_paths = []

        # Browsers
        if any(a in aliases for a in {"google chrome", "chrome"}):
            known_icon_paths.extend([
                os.path.join(prog_files, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(prog_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            ])
        if any(a in aliases for a in {"microsoft edge", "edge", "msedge"}):
            known_icon_paths.extend([
                os.path.join(prog_files, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(prog_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            ])
        if any(a in aliases for a in {"mozilla firefox", "firefox"}):
            known_icon_paths.extend([
                os.path.join(prog_files, "Mozilla Firefox", "firefox.exe"),
                os.path.join(prog_files_x86, "Mozilla Firefox", "firefox.exe"),
            ])
        if any(a in aliases for a in {"brave"}):
            known_icon_paths.extend([
                os.path.join(local_appdata, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ])

        # Chat / Social
        if any(a in aliases for a in {"whatsapp"}):
            known_icon_paths.extend([
                os.path.join(local_appdata, "WhatsApp", "WhatsApp.exe"),
                os.path.join(local_appdata, "Programs", "WhatsApp", "WhatsApp.exe"),
                os.path.join(appdata, "WhatsApp", "WhatsApp.exe"),
            ])
        if any(a in aliases for a in {"discord"}):
            known_icon_paths.extend([
                os.path.join(local_appdata, "Discord", "app-" + _find_latest_version(os.path.join(local_appdata, "Discord")), "Discord.exe")
                if os.path.isdir(os.path.join(local_appdata, "Discord")) else "",
                os.path.join(local_appdata, "Discord", "Discord.exe"),
            ])
        if any(a in aliases for a in {"telegram"}):
            known_icon_paths.extend([
                os.path.join(appdata, "Telegram Desktop", "Telegram.exe"),
                os.path.join(local_appdata, "Telegram Desktop", "Telegram.exe"),
            ])
        if any(a in aliases for a in {"slack"}):
            known_icon_paths.extend([
                os.path.join(local_appdata, "slack", "slack.exe"),
                os.path.join(prog_files, "Slack", "slack.exe"),
            ])
        if any(a in aliases for a in {"microsoft teams", "teams"}):
            known_icon_paths.extend([
                os.path.join(local_appdata, "Microsoft", "Teams", "current", "Teams.exe"),
                os.path.join(prog_files, "Microsoft", "Teams", "current", "Teams.exe"),
                os.path.join(prog_files_x86, "Microsoft", "Teams", "current", "Teams.exe"),
            ])
        if any(a in aliases for a in {"zoom"}):
            known_icon_paths.extend([
                os.path.join(appdata, "Zoom", "bin", "Zoom.exe"),
                os.path.join(prog_files, "Zoom", "bin", "Zoom.exe"),
            ])

        # Dev tools
        if any(a in aliases for a in {"vs code", "vscode", "code", "visual studio code"}):
            known_icon_paths.extend([
                os.path.join(local_appdata, "Programs", "Microsoft VS Code", "Code.exe"),
                os.path.join(prog_files, "Microsoft VS Code", "Code.exe"),
            ])
        if any(a in aliases for a in {"cursor"}):
            known_icon_paths.extend([
                os.path.join(local_appdata, "Programs", "cursor", "Cursor.exe"),
                os.path.join(local_appdata, "cursor", "Cursor.exe"),
            ])
        if any(a in aliases for a in {"powershell"}):
            known_icon_paths.extend([
                os.path.join(sys32, "WindowsPowerShell", "v1.0", "powershell.exe"),
                os.path.join(prog_files, "PowerShell", "7", "pwsh.exe"),
            ])
        if any(a in aliases for a in {"windows terminal", "terminal", "wt"}):
            known_icon_paths.extend([
                os.path.join(local_appdata, "Microsoft", "WindowsApps", "wt.exe"),
            ])
        if any(a in aliases for a in {"command prompt", "cmd"}):
            known_icon_paths.append(os.path.join(sys32, "cmd.exe"))

        # Media / Creative
        if any(a in aliases for a in {"spotify"}):
            known_icon_paths.extend([
                os.path.join(appdata, "Spotify", "Spotify.exe"),
                os.path.join(local_appdata, "Microsoft", "WindowsApps", "Spotify.exe"),
            ])
        if any(a in aliases for a in {"vlc"}):
            known_icon_paths.extend([
                os.path.join(prog_files, "VideoLAN", "VLC", "vlc.exe"),
                os.path.join(prog_files_x86, "VideoLAN", "VLC", "vlc.exe"),
            ])
        if any(a in aliases for a in {"figma"}):
            known_icon_paths.extend([
                os.path.join(local_appdata, "Figma", "Figma.exe"),
                os.path.join(local_appdata, "Programs", "Figma", "Figma.exe"),
            ])
        if any(a in aliases for a in {"adobe photoshop", "photoshop"}):
            for yr in range(2030, 2019, -1):
                known_icon_paths.append(
                    os.path.join(prog_files, "Adobe", f"Adobe Photoshop {yr}", "Photoshop.exe")
                )

        # Windows built-ins
        if any(a in aliases for a in {"notepad"}):
            known_icon_paths.append(os.path.join(sys32, "notepad.exe"))
            known_icon_paths.append(os.path.join(win_dir, "notepad.exe"))
        if any(a in aliases for a in {"calculator", "calc"}):
            known_icon_paths.append(os.path.join(sys32, "calc.exe"))
        if any(a in aliases for a in {"settings"}):
            known_icon_paths.extend([
                os.path.join(win_dir, "ImmersiveControlPanel", "SystemSettings.exe"),
                os.path.join(sys32, "SystemSettingsBroker.exe"),
            ])
        if any(a in aliases for a in {"file explorer", "explorer"}):
            known_icon_paths.append(os.path.join(win_dir, "explorer.exe"))
        if any(a in aliases for a in {"microsoft outlook", "outlook"}):
            for yr in ["2016", "2019", "2021", "root"]:
                known_icon_paths.append(
                    os.path.join(prog_files, "Microsoft Office", f"root" if yr == "root" else f"Office{yr}", "OUTLOOK.EXE")
                )
        if any(a in aliases for a in {"microsoft word", "word", "winword"}):
            known_icon_paths.extend([
                os.path.join(prog_files, "Microsoft Office", "root", "Office16", "WINWORD.EXE"),
                os.path.join(prog_files_x86, "Microsoft Office", "root", "Office16", "WINWORD.EXE"),
            ])
        if any(a in aliases for a in {"microsoft excel", "excel"}):
            known_icon_paths.extend([
                os.path.join(prog_files, "Microsoft Office", "root", "Office16", "EXCEL.EXE"),
                os.path.join(prog_files_x86, "Microsoft Office", "root", "Office16", "EXCEL.EXE"),
            ])
        if any(a in aliases for a in {"microsoft powerpoint", "powerpoint", "powerpnt"}):
            known_icon_paths.extend([
                os.path.join(prog_files, "Microsoft Office", "root", "Office16", "POWERPNT.EXE"),
                os.path.join(prog_files_x86, "Microsoft Office", "root", "Office16", "POWERPNT.EXE"),
            ])
        if any(a in aliases for a in {"steam"}):
            known_icon_paths.extend([
                os.path.join(prog_files_x86, "Steam", "steam.exe"),
                os.path.join(prog_files, "Steam", "steam.exe"),
            ])
        if any(a in aliases for a in {"copilot"}):
            known_icon_paths.extend([
                os.path.join(local_appdata, "Microsoft", "WindowsApps", "Copilot.exe"),
            ])

        for path in known_icon_paths:
            if path and os.path.exists(path):
                return path

        # Best source for logo: real executable path of the running process.
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                exe_path = (proc.info.get("exe") or "").strip()
                proc_name = (proc.info.get("name") or "").strip()
                if not exe_path:
                    continue
                norm_base = self._normalize_for_icon_lookup(os.path.splitext(proc_name)[0])
                if any(a == norm_base or a in norm_base or norm_base in a for a in aliases):
                    if os.path.exists(exe_path):
                        return exe_path
            except Exception:
                continue

        if hasattr(self, "agent") and hasattr(self.agent, "_build_app_launch_index"):
            try:
                self.agent._build_app_launch_index()
                match_key = self.agent._find_best_index_match(target, self.agent.app_launch_index)
                if match_key:
                    candidate = self.agent.app_launch_index.get(match_key)
                    if candidate and os.path.exists(candidate):
                        return candidate
            except Exception:
                pass

        return None

    def _icon_for_running_app(self, app_name):
        cache_key = self._normalize_for_icon_lookup(app_name)
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]
        icon_path = self._resolve_running_app_icon_path(app_name)
        if icon_path:
            icon = self.icon_provider.icon(QFileInfo(icon_path))
            if not icon.isNull():
                hi = icon.pixmap(128, 128)
                if not hi.isNull():
                    resolved = QIcon(hi)
                    self._icon_cache[cache_key] = resolved
                    return resolved
                self._icon_cache[cache_key] = icon
                return icon
        style = self.style()
        fallback = style.standardIcon(QStyle.SP_FileIcon) if style else QIcon()
        self._icon_cache[cache_key] = fallback
        return fallback

    def _normalize_running_apps(self, apps):
        cleaned = []
        seen = set()
        for raw in (apps or []):
            name = (raw or "").strip()
            if not name:
                continue
            key = self._normalize_for_icon_lookup(name)
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(name)
        cleaned.sort(key=lambda s: s.lower())
        return cleaned[:30]

    def _populate_running_apps_list(self, apps):
        if self.rail_apps_list is None:
            return
        self.rail_apps_list.clear()
        for app in (apps or []):
            item = QListWidgetItem("")
            item.setData(Qt.UserRole, app)
            item.setToolTip(app)
            item.setIcon(self._icon_for_running_app(app))
            item.setSizeHint(QSize(0, 52))
            self.rail_apps_list.addItem(item)

    def _weather_code_to_text(self, code):
        groups = {
            "Clear skies": {0},
            "Mainly clear": {1},
            "Partly cloudy": {2},
            "Overcast": {3},
            "Fog": {45, 48},
            "Light drizzle": {51},
            "Drizzle": {53},
            "Heavy drizzle": {55},
            "Freezing drizzle": {56, 57},
            "Light rain": {61},
            "Rain": {63},
            "Heavy rain": {65},
            "Freezing rain": {66, 67},
            "Light snow": {71},
            "Snow": {73, 75},
            "Snow grains": {77},
            "Rain showers": {80, 81, 82},
            "Snow showers": {85, 86},
            "Thunderstorm": {95, 96, 99},
        }
        try:
            value = int(code)
        except Exception:
            return "Clear"
        for label, values in groups.items():
            if value in values:
                return label
        return "Clear"

    def _fetch_local_weather_snapshot(self):
        lat = None
        lon = None
        city = ""
        country = ""
        try:
            with urlopen("https://ipapi.co/json/", timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            lat = data.get("latitude")
            lon = data.get("longitude")
            city = (data.get("city") or "").strip()
            country = (data.get("country_name") or "").strip()
        except Exception:
            pass

        if (lat is None or lon is None) and hasattr(self, "agent") and self.agent:
            try:
                loc = self.agent._resolve_location_coords("weather now")
                if loc:
                    lat = loc.get("lat")
                    lon = loc.get("lon")
                    city = city or (loc.get("name") or "")
                    country = country or (loc.get("country") or "")
            except Exception:
                pass

        if lat is None or lon is None:
            return None

        try:
            weather_url = (
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation"
                "&timezone=auto"
            )
            with urlopen(weather_url, timeout=6) as resp:
                wdata = json.loads(resp.read().decode("utf-8", errors="ignore"))
            current = wdata.get("current") or {}
            temp = current.get("temperature_2m")
            feels = current.get("apparent_temperature")
            humidity = current.get("relative_humidity_2m")
            wind = current.get("wind_speed_10m")
            precip = current.get("precipitation")
            code = current.get("weather_code")
            condition = self._weather_code_to_text(code)
            location = city or "your area"
            if country:
                location = f"{location}, {country}"
            return {
                "location": location,
                "temp_c": temp,
                "feels_c": feels,
                "humidity": humidity,
                "wind_kmh": wind,
                "precip_mm": precip,
                "condition": condition,
            }
        except Exception:
            return None

    def _reflow_smart_header_layout(self):
        if self.smart_header_label is None:
            return
        available = 980
        if self.content_widget is not None:
            available = max(420, self.content_widget.width() - 120)
        target_w = min(1200, available)
        self.smart_header_label.setFixedWidth(target_w)
        # Keep greeting block height stable so greeting + chat bar stay fixed in center.
        self.smart_header_label.setFixedHeight(150)
        self.smart_header_label.updateGeometry()
        parent = self.smart_header_label.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().invalidate()
            parent.layout().activate()

    def _refresh_smart_header_text(self):
        if self.smart_header_label is None:
            return
        now_dt = datetime.now()
        hour = now_dt.hour
        if hour < 12:
            salutation = "Good morning"
        elif hour < 18:
            salutation = "Good afternoon"
        else:
            salutation = "Good evening"

        time_str = now_dt.strftime("%H:%M")
        date_str = now_dt.strftime("%B %d, %Y").replace(" 0", " ")
        short_date = now_dt.strftime("%d %b")
        weather_part = "Weather unavailable"
        snap = self._weather_snapshot or {}
        if snap:
            location = snap.get("location") or "your area"
            if "," in location:
                location = location.split(",")[0].strip() or location
            condition = snap.get("condition") or "Clear skies"
            temp = snap.get("temp_c")
            feels = snap.get("feels_c")
            temp_text = f"{float(temp):.1f}" if isinstance(temp, (int, float)) else "N/A"
            feels_text = f"{float(feels):.1f}" if isinstance(feels, (int, float)) else "N/A"
            weather_part = f"{location} {temp_text}°C ({condition})"

        if self.current_mode == "task":
            text = f"{salutation}. {time_str}, {short_date}. {weather_part}. What should we do?"
        else:
            text = f"{salutation}. {time_str}, {short_date}. {weather_part}. How can I help?"
        self.smart_header_label.setText(text)
        self._reflow_smart_header_layout()

    def _start_weather_fetch_for_header(self, force=False):
        now_ts = time.time()
        if self._weather_fetch_inflight:
            return
        if (not force) and self._weather_snapshot and (now_ts - self._last_weather_fetch_ts) < 300:
            return

        self._weather_fetch_inflight = True

        def _worker():
            snap = self._fetch_local_weather_snapshot()
            self._weather_snapshot = snap
            self._last_weather_fetch_ts = time.time()
            self._weather_fetch_inflight = False
            QTimer.singleShot(0, self._refresh_smart_header_text)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def _update_centered_composer_state(self, force_weather=False):
        if self.scroll_area is None or self.input_container is None:
            return
        active_conv = self.current_task_conversation if self.current_mode == "task" else self.current_conversation
        show_centered = len(active_conv) == 0

        self.scroll_area.setVisible(not show_centered)
        if self.smart_header_label is not None:
            self.smart_header_label.setVisible(show_centered)
        if self.center_top_spacer is not None:
            self.center_top_spacer.setVisible(show_centered)
        if self.center_bottom_spacer is not None:
            self.center_bottom_spacer.setVisible(show_centered)
        if self.smart_header_gap is not None:
            self.smart_header_gap.setVisible(show_centered)
        self._reflow_smart_header_layout()
        self._refresh_smart_header_text()
        if show_centered:
            self._start_weather_fetch_for_header(force=force_weather)

    def update_system_info(self):
        """Update system information"""
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            now = time.monotonic()
            if self._cached_disk_usage is None or (now - self._last_disk_refresh_ts) >= 10.0:
                self._cached_disk_usage = psutil.disk_usage('/')
                self._last_disk_refresh_ts = now
            disk = self._cached_disk_usage
            battery = psutil.sensors_battery()
            
            mem_used = mem.used / (1024**3)
            mem_total = mem.total / (1024**3)
            disk_free = disk.free / (1024**3)
            
            bat_text = f"BAT: {battery.percent}%" if battery else "BAT: --"
            
            sys_text = f"CPU: {cpu:.1f}% MEM: {mem.percent:.1f}% ({mem_used:.2f}/{mem_total:.2f}GB) DSK: {disk.percent:.1f}% ({disk_free:.2f}GB free) {bat_text}"
            if sys_text != self._last_sys_text:
                self.sys_details.setText(sys_text)
                self._last_sys_text = sys_text
            
            # Get running apps less frequently to avoid UI stalls.
            worker_busy = self.worker is not None and self.worker.isRunning()
            if (not worker_busy) and ((now - self._last_apps_refresh_ts) >= self.apps_refresh_interval_sec):
                if hasattr(self.agent, 'get_running_apps'):
                    apps = self.agent.get_running_apps()
                else:
                    apps = []
                    for proc in psutil.process_iter(['name']):
                        try:
                            name = proc.info['name']
                            if name and not any(x in name.lower() for x in ['svchost', 'system']):
                                apps.append(name.replace('.exe', ''))
                        except Exception:
                            continue
                apps = self._normalize_running_apps(apps)
                signature = tuple(apps)
                if signature != self._last_apps_signature:
                    self._populate_running_apps_list(apps)
                    self._last_apps_signature = signature
                self._last_apps_refresh_ts = now
            if self.screen_share_enabled and self.screen_share_overlay is not None:
                self.screen_share_overlay.cover_primary_screen()
            if self.smart_header_label is not None and self.smart_header_label.isVisible():
                self._refresh_smart_header_text()
            
        except Exception as e:
            print(f"Error updating stats: {e}")

    def focus_or_open_app(self, app_name):
        """Bring a running app window to front, otherwise open it."""
        target = (app_name or "").strip()
        if not target:
            return False

        normalized = target.lower()
        # Canonical title hints for better window matching.
        title_tokens = {
            "google chrome": ["chrome"],
            "chrome": ["chrome"],
            "brave": ["brave"],
            "framer": ["framer"],
            "discord": ["discord"],
            "telegram": ["telegram"],
            "whatsapp": ["whatsapp"],
            "vs code": ["visual studio code", "code"],
            "cursor": ["cursor"],
            "figma": ["figma"],
            "copilot": ["copilot"],
            "command prompt": ["command prompt", "cmd"],
            "powershell": ["powershell"],
            "windows terminal": ["windows terminal", "terminal"],
            "file explorer": ["file explorer", "explorer"],
            "notion": ["notion"],
        }
        tokens = title_tokens.get(normalized, [normalized])

        if gw is not None:
            try:
                matched = []
                for w in gw.getAllWindows():
                    title = (w.title or "").strip()
                    if not title:
                        continue
                    lower_title = title.lower()
                    if any(tok in lower_title for tok in tokens):
                        matched.append(w)

                for w in matched:
                    try:
                        if getattr(w, "isMinimized", False):
                            w.restore()
                        w.activate()
                        return True
                    except Exception:
                        continue
            except Exception:
                pass

        # Fallback: launch/open app.
        try:
            result = self.agent.open_app(target)
            return bool(result)
        except Exception:
            return False

    def on_running_app_clicked(self, item):
        """Handle click on running app name in sidebar."""
        app_name = (item.data(Qt.UserRole) or item.text() or "").strip()
        if not app_name:
            return
        if not self.focus_or_open_app(app_name):
            self.log_conversation("SYSTEM", f"Could not focus/open {app_name}")
    
    def closeEvent(self, event):
        """Save active conversations before the window closes."""
        self._archive_current_chat()
        self._archive_current_task()
        event.accept()

    def new_chat(self):
        """Clear chat conversation"""
        self._archive_current_chat()
        # Tell the agent to forget chat context but keep training data
        if hasattr(self, "agent") and self.agent:
            self.agent.start_new_session()
        self._clear_layout_preserve_indicator(self.chat_layout, self.chat_activity_indicator)
        self.last_user_bubble_chat = None
        self.current_conversation = []
        self.current_session_id = None
        self.current_conversation_dirty = False
        if self.conversation_list is not None:
            self.conversation_list.clearSelection()
        self._update_centered_composer_state(force_weather=True)

    def new_task(self):
        """Clear task conversation"""
        self._archive_current_task()
        if hasattr(self, "agent") and self.agent:
            # Reset agent's task history
            if hasattr(self.agent, "task_conversation_history"):
                self.agent.task_conversation_history = []
        self._clear_layout_preserve_indicator(self.task_layout, self.task_activity_indicator)
        self.last_user_bubble_task = None
        self.current_task_conversation = []
        self.current_task_session_id = None
        self.current_conversation_dirty = False
        self._update_centered_composer_state(force_weather=True)

    def _new_chat_or_task(self):
        """Route new-chat/new-task button to the right handler based on current mode."""
        if self.current_mode == "task":
            self.new_task()
        else:
            self.new_chat()

    # ── Mode switching ─────────────────────────────────────────────────────────

    def _apply_mode_button_styles(self):
        """Style mode buttons — active gets white fill, inactive stays subtle."""
        _btn_active = """
            QPushButton {
                background: rgba(255, 255, 255, 0.18);
                color: rgba(255, 255, 255, 0.95);
                border: none;
                border-radius: 22px;
                padding: 0 22px;
                font-family: 'Poppins';
                font-size: 14px;
                font-weight: 500;
            }
        """
        _btn_inactive = """
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: rgba(255, 255, 255, 0.60);
                border: none;
                border-radius: 22px;
                padding: 0 22px;
                font-family: 'Poppins';
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.14);
                color: rgba(255, 255, 255, 0.95);
            }
        """
        is_chat = self.current_mode == "chat"
        is_task = self.current_mode == "task"
        self.chat_mode_btn.setStyleSheet(_btn_active if is_chat else _btn_inactive)
        self.tasks_mode_btn.setStyleSheet(_btn_active if is_task else _btn_inactive)
        self.code_mode_btn.setStyleSheet(_btn_inactive)
        self.wallet_mode_btn.setStyleSheet(_btn_inactive)

    def _switch_mode(self, mode):
        """Switch between chat and task modes."""
        if self.current_mode == mode:
            return
        self.current_mode = mode
        self._apply_mode_button_styles()

        # Update sidebar "New chat" ↔ "New task"
        if self.new_chat_btn:
            self.new_chat_btn.setText("New task" if mode == "task" else "New chat")
        if self.new_chat_icon_lbl:
            self.new_chat_icon_lbl.setPixmap(
                self.new_task_icon_pix if mode == "task" else self.new_chat_icon_pix
            )
        self.refresh_conversation_list()

        # Update input placeholder
        if self.input_field:
            self.input_field.setPlaceholderText(
                "Tell me what to do" if mode == "task" else "Ask me anything"
            )

        # Swap the scroll area to show the mode-specific message widget.
        # takeWidget() detaches the current widget WITHOUT deleting it (setWidget would delete it).
        if hasattr(self, "scroll_area"):
            old = self.scroll_area.takeWidget()
            if old is not None:
                old.setParent(self)
                old.hide()
            if mode == "task":
                self.scroll_area.setWidget(self.task_widget)
                self.task_widget.show()
            else:
                self.scroll_area.setWidget(self.chat_widget)
                self.chat_widget.show()
            QTimer.singleShot(80, self.scroll_to_bottom)

        # Notify the agent of the mode change
        if hasattr(self, "agent") and self.agent:
            self.agent.input_mode = mode
        self._refresh_activity_indicator_on_mode_change()
        if self.share_btn:
            self.share_btn.setVisible(mode == "task")
        self._update_centered_composer_state(force_weather=True)

    def send_message(self):
        """Send message to AI"""
        if self.pending_sensitive_command:
            self.add_message("Please choose Allow or Deny for the pending sensitive operation first.", False)
            return

        command = self.input_field.toPlainText().strip()
        if not command and not self.pending_attachments:
            return
        if not command and self.pending_attachments:
            command = "Analyze the attached files."
        
        # Auto-switch to Task mode BEFORE adding message so bubble goes in correct layout
        if self.current_mode == "chat" and self._detect_task_command(command):
            self._switch_mode("task")

        # Add user message (add_message routes to active mode layout automatically)
        self.add_message(command, True)
        _msg_entry = {
            "role": "user",
            "text": command,
            "time": datetime.now().isoformat(timespec="seconds"),
        }
        if self.current_mode == "task":
            self.current_task_conversation.append(_msg_entry)
        else:
            self.current_conversation.append(_msg_entry)
        self.current_conversation_dirty = True
        self._update_centered_composer_state()
        self.log_conversation("You", command)
        self.input_field.clear()
        self.update_send_button_state()

        if self._needs_sensitive_fs_authorization(command):
            self.pending_sensitive_command = command
            self.add_authorization_prompt(command)
            return

        worker_command = command
        # Tag command with current mode so the agent routes correctly
        if self.current_mode == "task":
            worker_command = f"MODE_TASK::{worker_command}"
        if self.screen_share_enabled:
            snapshot_path = self._capture_shared_screen_frame(force=False)
            if snapshot_path:
                worker_command = f"SCREEN_SHARE::{snapshot_path}::{worker_command}"
            else:
                # Capture failed — warn user and stop so AI doesn't search instead
                self.add_message(
                    "⚠️ Screen capture failed — cannot read your screen right now. "
                    "Check that the app has permission to write to its folder.",
                    False,
                )
                self.input_field.setEnabled(True)
                self.update_send_button_state()
                return
        if self.pending_attachments:
            attachment_blob = "|".join(p.replace("|", "_") for p in self.pending_attachments)
            worker_command = f"ATTACHMENTS::{attachment_blob}::{worker_command}"
            self.pending_attachments = []
            self._update_attachments_label()
        self.run_worker_command(worker_command)
    
    def _extract_file_card_from_response(self, response):
        """
        Scan an AI response for a 'Saved and opened `filename`' pattern.
        Returns (file_path, file_name, file_size, ext) or None if not found.
        """
        # Pattern: **Saved and opened** `name.ext` on your Desktop
        #          **Saved and opened** `name.ext` in `folder`
        #          **Word document created** and opened: `name.ext`
        #          **Analytics Excel saved:** `name.ext` on your Desktop
        #          **Chart saved:** `name.ext` on your Desktop
        m = re.search(
            r'(?:'
            r'\*\*Saved and opened\*\*'
            r'|\*\*Word document created\*\*[^`]*?:'
            r'|\*\*Analytics Excel saved:\*\*'
            r'|\*\*Chart saved:\*\*'
            r'|\*\*[A-Za-z ]+(?:saved|created|generated)[:\*]*\*\*[^`]*?'
            r')'
            r'\s*`([^`]+)`'
            r'(?:\s+in\s+`([^`]+)`)?',
            response, re.IGNORECASE,
        )
        if not m:
            return None
        file_name = m.group(1).strip()
        folder_hint = (m.group(2) or "").strip()
        # Resolve folder
        if folder_hint and os.path.isdir(folder_hint):
            folder = folder_hint
        else:
            folder = os.path.join(os.path.expanduser("~"), "Desktop")
        file_path = os.path.normpath(os.path.join(folder, file_name))
        if not os.path.exists(file_path):
            return None
        ext = os.path.splitext(file_name)[1].lower().lstrip(".")
        size_bytes = os.path.getsize(file_path)
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes / 1024 / 1024:.1f} MB"
        return file_path, file_name, size_str, ext

    def on_response(self, response):
        """Handle AI response"""
        self._set_activity_indicator(False)
        if (response or "").strip() == "__APP_EXIT__":
            self.add_message("Closing app now.", False)
            self.log_conversation("AI", "Closing app now.")
            QTimer.singleShot(80, self.close)
            return
        bubble = self.add_message(response, False)
        # ── File card attachment ────────────────────────────────────────────
        _fc_info = self._extract_file_card_from_response(response)
        if _fc_info is not None:
            try:
                card = FileCard(*_fc_info)
                if hasattr(bubble, "set_footer"):
                    bubble.set_footer(card)
            except Exception:
                pass
        # ───────────────────────────────────────────────────────────────────
        self._add_feedback_row(response, bubble)
        _resp_entry = {
            "role": "assistant",
            "text": response,
            "time": datetime.now().isoformat(timespec="seconds"),
        }
        if self.current_mode == "task":
            self.current_task_conversation.append(_resp_entry)
        else:
            self.current_conversation.append(_resp_entry)
        self.current_conversation_dirty = True
        self.log_conversation("AI", response)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
        self.update_send_button_state()
        # Re-enable mic with a 1.5s cooldown so TTS echo/room reverb fades before listening again
        if self.voice_thread is not None and self.voice_thread.isRunning():
            self.voice_thread.unmute(cooldown=1.5)

    def _add_feedback_row(self, assistant_text, bubble=None):
        row = FeedbackRow()

        def on_good():
            self._submit_feedback("good", assistant_text, row=row)

        def on_bad():
            self._submit_feedback("bad", assistant_text, row=row)

        row.set_handlers(on_good=on_good, on_bad=on_bad)
        if bubble is not None and hasattr(bubble, "set_footer"):
            bubble.set_footer(row)
        else:
            active_layout = self.task_layout if self.current_mode == "task" else self.chat_layout
            active_layout.insertWidget(active_layout.count() - 1, row)
        QTimer.singleShot(100, self.scroll_to_bottom)

    _TASK_CMD_RE = re.compile(
        r"^(open|launch|start|run|close|kill|quit|exit|create|make|build|delete|remove"
        r"|rename|move|copy|click|type|press|scroll|take\s+screenshot|screenshot"
        r"|volume|brightness|download|install|uninstall|turn\s+(on|off)|enable|disable"
        r"|maximize|minimize|resize|drag|focus|switch\s+to|go\s+to\s+desktop"
        r"|empty\s+trash|pin|unpin|restart|shutdown|lock|sleep"
        r"|generate|produce|export|convert|write|save|send|fetch|search|research"
        r"|browse|analyze|analyse|plot|capture|compose|draft|prepare)\b",
        re.IGNORECASE,
    )

    # Topics that are ALWAYS a task regardless of how the sentence is phrased
    _ALWAYS_TASK_RE = re.compile(
        r"\b("
        r"weather|forecast|temperature|rain|sunny|celsius|fahrenheit|humidity"
        r"|prayer\s+time|salat|salah|athan|adhan"
        r"|bitcoin|btc|ethereum|eth|crypto(?:currency)?|coin\s+price|crypto\s+price"
        r"|latest\s+news|news\s+(?:about|today)|headlines?"
        r"|cpu\s+usage|ram\s+usage|disk\s+(?:usage|space)|memory\s+usage"
        r"|battery\s+(?:level|status|percent|life)"
        r"|system\s+(?:info|stats?|status|specs?)"
        r"|wifi|wi.?fi|bluetooth|airplane\s+mode"
        r"|screenshot|screen\s+capture|screen\s+record|snip\s+tool"
        r"|\.pdf|\.docx?|\.xlsx?|\.pptx?|\.csv"
        r")\b",
        re.IGNORECASE,
    )

    # Nouns that turn an ambiguous "show/give/tell me" into a task
    _TASK_NOUN_RE = re.compile(
        r"\b(pdf|docx?|word|excel|xlsx?|spreadsheet|presentation|pptx?|powerpoint"
        r"|slides?|file|folder|desktop|document|report|chart|graph|plot|histogram"
        r"|data|csv|download|install|uninstall|search|browse|internet|web|url|link"
        r"|website|research|email|volume|brightness|screenshot|capture|weather"
        r"|crypto|bitcoin|btc|price|prayer|salat|cpu|ram|memory|disk|battery)\b",
        re.IGNORECASE,
    )

    def _detect_task_command(self, text):
        """
        Return True if text is a task (desktop action, file generation, data
        analysis, web search, live data fetch, etc.) rather than pure conversation.
        """
        t = (text or "").strip()
        tl = t.lower()

        # 1. Always-task topics regardless of phrasing
        if self._ALWAYS_TASK_RE.search(tl):
            return True

        # 2. Pure question openers with no task nouns → stay in chat
        _is_pure_q = bool(re.match(
            r"^(what|who|when|where|why|how|is|are|can|could|do|does|did|will|would)\b",
            tl,
        ))
        if _is_pure_q and not self._TASK_NOUN_RE.search(tl):
            return False

        # 3. Action verb at start
        if self._TASK_CMD_RE.match(t):
            return True

        # 4. File / document generation
        if re.search(
            r"\b(generate|create|make|produce|build|write|save|export|draft"
            r"|prepare|convert|compose|put|give\s+me)\b", tl
        ) and re.search(
            r"\b(pdf|docx?|word(?:\s+doc(?:ument)?)?|excel|xlsx?|spreadsheet"
            r"|pptx?|powerpoint|presentation|slides?|slide\s+deck|csv"
            r"|document|report|note\s+file|text\s+file|folder)\b", tl
        ):
            return True

        # 5. Data analysis / visualization
        if re.search(
            r"\b(analyz[ei]|analyse|visuali[sz]e?|plot|chart|graph|statistics"
            r"|stats\b|correlat[ei]|regression|histogram|scatter|heatmap"
            r"|boxplot|pie\s+chart|bar\s+chart|line\s+chart|summarize|summarise"
            r"|describe\s+(?:the\s+)?data|explore\s+(?:the\s+)?data)\b", tl
        ):
            return True

        # 6. Web search / research
        if re.search(
            r"\b(search(?:\s+(?:for|about|on|the|web|internet|online))?"
            r"|google(?:\s+(?:for|about|this))?"
            r"|look\s+up|find\s+(?:info(?:rmation)?|results?|articles?|data)"
            r"|research(?:\s+(?:about|on|for|the))?"
            r"|browse(?:\s+(?:the\s+)?(?:web|internet))?"
            r"|fetch\s+(?:data|info(?:rmation)?|results?)"
            r"|get\s+(?:the\s+)?(?:latest|live|real.?time))\b", tl
        ):
            return True

        # 7. URL mentioned → open in browser is a task
        if re.search(r"https?://", tl) or re.search(
            r"\b(open|visit|go\s+to|browse\s+to)\b.{0,30}\b(link|url|website|page|site)\b", tl
        ):
            return True

        # 8. Named app management
        if re.search(r"\b(open|launch|start|close|quit|exit|kill|stop|run)\b", tl) and re.search(
            r"\b(app(?:lication)?|program|software|window|browser|chrome|firefox"
            r"|edge|excel|word|notepad|calculator|spotify|discord|whatsapp"
            r"|telegram|vscode|visual\s+studio|photoshop|vlc|teams|zoom|skype"
            r"|outlook|powerpoint|paint|7.?zip|winrar)\b", tl
        ):
            return True

        # 9. "show/give/tell/get me" + task noun → task
        if re.search(
            r"\b(show\s+me|give\s+me|get\s+me|tell\s+me|bring\s+me"
            r"|fetch\s+me|find\s+me|check\s+(?:the\s+)?|pull\s+up)\b", tl
        ) and self._TASK_NOUN_RE.search(tl):
            return True

        return False

def main():
    app = QApplication(sys.argv)

    window = AIAgentWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
