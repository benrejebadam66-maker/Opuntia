import html
import math
import os
import re
import sys

from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, QSize, QMimeData, QUrl, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QLinearGradient, QPainterPath, QRegion, QPixmap, QIcon, QImage, QDrag
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QMenu,
    QTextEdit,
    QFileDialog,
)


def _get_resource_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _resolve_resource_path(filename):
    base_dir = _get_resource_dir()
    candidates = [
        os.path.join(base_dir, "Vector images & icons", filename),
        os.path.join(base_dir, filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


class MessageBubble(QWidget):
    def __init__(self, text, is_user=True):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 10, 3)
        layout.setSpacing(0)

        rail = QWidget()
        rail.setMaximumWidth(860)
        rail.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        rail_layout = QHBoxLayout(rail)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        rail_layout.setSpacing(0)

        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(760)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        bubble.setContextMenuPolicy(Qt.CustomContextMenu)
        bubble.setProperty("raw_text", text or "")
        bubble.customContextMenuRequested.connect(lambda pos, lbl=bubble: self.show_text_context_menu(lbl, pos))

        if is_user:
            bubble.setStyleSheet(
                """
                QLabel {
                    background-color: rgba(255, 255, 255, 0.11);
                    color: #FFFFFF;
                    padding: 13px 18px;
                    border-radius: 18px;
                    font-family: 'Poppins';
                    font-size: 18px;
                    line-height: 1.35;
                    border: none;
                }
                """
            )
            rail_layout.addStretch()
            rail_layout.addWidget(bubble, 0, Qt.AlignRight)
        else:
            bubble.setText(self._format_ai_text(text))
            bubble.setTextFormat(Qt.RichText)
            bubble.setStyleSheet(
                """
                QLabel {
                    background-color: transparent;
                    color: #FFFFFF;
                    font-family: 'Poppins';
                    font-size: 18px;
                    line-height: 1.35;
                    border: none;
                    padding: 9px 0px;
                }
                """
            )
            stack = QWidget()
            stack_layout = QVBoxLayout(stack)
            stack_layout.setContentsMargins(0, 0, 0, 0)
            stack_layout.setSpacing(6)
            stack_layout.addWidget(bubble, 0, Qt.AlignLeft)
            self.footer_layout = QVBoxLayout()
            self.footer_layout.setContentsMargins(0, 4, 0, 0)
            self.footer_layout.setSpacing(4)
            stack_layout.addLayout(self.footer_layout)
            rail_layout.addWidget(stack, 0, Qt.AlignLeft)
            rail_layout.addStretch()

        layout.addStretch()
        layout.addWidget(rail, 1)
        layout.addStretch()

    def set_footer(self, widget):
        if hasattr(self, "footer_layout") and widget is not None:
            self.footer_layout.addWidget(widget, 0, Qt.AlignLeft)

    def _inline_md(self, escaped_text):
        """Apply inline markdown (bold, italic, code) to already HTML-escaped text."""
        result = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped_text)
        result = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", result)
        result = re.sub(
            r"`(.+?)`",
            r'<span style="background-color:rgba(255,255,255,0.10);font-family:monospace;'
            r'padding:1px 5px;border-radius:3px;">\1</span>',
            result,
        )
        return result

    def _format_ai_text(self, text):
        if not text:
            return ""
        raw_lines = text.splitlines()
        parts = []
        i = 0
        while i < len(raw_lines):
            line = raw_lines[i]
            stripped = line.strip()

            # ── Markdown table ──────────────────────────────────────────────
            if stripped.startswith("|") and stripped.endswith("|"):
                table_rows = []
                while i < len(raw_lines) and raw_lines[i].strip().startswith("|"):
                    table_rows.append(raw_lines[i].strip())
                    i += 1
                header_row = None
                data_rows = []
                for row in table_rows:
                    cells = [c.strip() for c in row.strip("|").split("|")]
                    if all(re.match(r"^[-:| ]+$", c) for c in cells if c.strip()):
                        continue
                    if header_row is None:
                        header_row = cells
                    else:
                        data_rows.append(cells)
                if header_row:
                    t = (
                        '<table style="border-collapse:collapse;margin:8px 0;'
                        'font-family:Poppins;font-size:16px;width:auto;">'
                    )
                    t += "<tr>"
                    for cell in header_row:
                        t += (
                            '<th style="background-color:rgba(255,255,255,0.14);'
                            "color:#FFFFFF;font-weight:700;padding:7px 16px;"
                            'border:1px solid rgba(255,255,255,0.18);text-align:left;">'
                            + self._inline_md(html.escape(cell))
                            + "</th>"
                        )
                    t += "</tr>"
                    for ri, row in enumerate(data_rows):
                        bg = "rgba(255,255,255,0.05)" if ri % 2 == 0 else "transparent"
                        t += f'<tr style="background-color:{bg};">'
                        for cell in row:
                            t += (
                                '<td style="color:#E0E6F0;padding:6px 16px;'
                                'border:1px solid rgba(255,255,255,0.10);">'
                                + self._inline_md(html.escape(cell))
                                + "</td>"
                            )
                        t += "</tr>"
                    t += "</table>"
                    parts.append(t)
                continue

            # ── Headings ────────────────────────────────────────────────────
            h1 = re.match(r"^#\s+(.+)", stripped)
            h2 = re.match(r"^##\s+(.+)", stripped)
            h3 = re.match(r"^###\s+(.+)", stripped)
            if h1 and not h2:
                parts.append(
                    '<br><span style="color:#FFFFFF;font-size:21px;font-weight:700;">'
                    + self._inline_md(html.escape(h1.group(1)))
                    + "</span><br>"
                )
                i += 1
                continue
            if h2 and not h3:
                parts.append(
                    '<br><span style="color:#FFFFFF;font-size:19px;font-weight:700;">'
                    + self._inline_md(html.escape(h2.group(1)))
                    + "</span><br>"
                )
                i += 1
                continue
            if h3:
                parts.append(
                    '<span style="color:#AACCFF;font-size:17px;font-weight:600;">'
                    + self._inline_md(html.escape(h3.group(1)))
                    + "</span><br>"
                )
                i += 1
                continue

            # ── Bullet points ───────────────────────────────────────────────
            bullet = re.match(r"^[*\-]\s+(.+)", stripped)
            if bullet:
                parts.append(
                    '<span style="color:#7BA7F5;">&#9679;</span>&nbsp;'
                    + self._inline_md(html.escape(bullet.group(1)))
                    + "<br>"
                )
                i += 1
                continue

            numbered = re.match(r"^(\d+)\.\s+(.+)", stripped)
            if numbered:
                parts.append(
                    f'<span style="color:#7BA7F5;font-weight:600;">{html.escape(numbered.group(1))}.</span>&nbsp;'
                    + self._inline_md(html.escape(numbered.group(2)))
                    + "<br>"
                )
                i += 1
                continue

            # ── Regular line ────────────────────────────────────────────────
            if not stripped:
                parts.append("<br>")
            else:
                escaped = html.escape(line)
                processed = self._inline_md(escaped)
                if stripped.endswith(":") and len(stripped) <= 90 and "**" not in line:
                    processed = f"<b>{html.escape(stripped)}</b>"
                parts.append(processed + "<br>")
            i += 1

        return "".join(parts)

    def show_text_context_menu(self, label, pos):
        menu = QMenu(self)
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        menu.setWindowFlags(
            menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        menu.setStyleSheet(
            """
            QMenu {
                background-color: #0f1113;
                color: #F2F2F2;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 12px;
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
            """
        )
        copy_action = menu.addAction("Copy")
        select_all_action = menu.addAction("Select all")
        chosen = menu.exec_(label.mapToGlobal(pos))
        if chosen == copy_action:
            selected = ""
            try:
                selected = label.selectedText()
            except Exception:
                selected = ""
            QApplication.clipboard().setText(selected or str(label.property("raw_text") or ""))
        elif chosen == select_all_action:
            try:
                label.selectAll()
            except Exception:
                pass


class ThinkingIndicator(QWidget):
    def __init__(self, phrases=None):
        super().__init__()
        self.phrases = phrases or [
            "Thinking",
            "Reasoning",
            "Working on it",
            "Composing",
            "Generating",
        ]
        self._phrase_index = 0
        self._dot_count = 0
        self._manual_phrase = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(0)

        rail = QWidget()
        rail.setMaximumWidth(860)
        rail.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        rail_layout = QHBoxLayout(rail)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        rail_layout.setSpacing(0)

        stack = QWidget()
        stack_layout = QVBoxLayout(stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.setSpacing(0)

        self.label = QLabel("")
        self.label.setStyleSheet(
            """
            QLabel {
                color: #8E8E9E;
                font-family: 'Poppins';
                font-size: 16px;
                font-weight: 500;
                padding: 9px 0px;
            }
            """
        )
        stack_layout.addWidget(self.label, 0, Qt.AlignLeft)
        rail_layout.addWidget(stack, 0, Qt.AlignLeft)
        rail_layout.addStretch()

        layout.addStretch()
        layout.addWidget(rail, 1)
        layout.addStretch()

        self._dot_timer = QTimer(self)
        self._dot_timer.timeout.connect(self._tick_dots)
        self._phrase_timer = QTimer(self)
        self._phrase_timer.timeout.connect(self._tick_phrase)
        self.setVisible(False)

    def set_active(self, active):
        if active:
            self._dot_count = 0
            self._phrase_index = self._phrase_index % len(self.phrases)
            self._update_text()
            try:
                if not self._dot_timer.isActive():
                    self._dot_timer.start(450)
                if self._manual_phrase is None and not self._phrase_timer.isActive():
                    self._phrase_timer.start(2600)
            except RuntimeError:
                return
            self.setVisible(True)
        else:
            try:
                self._dot_timer.stop()
                self._phrase_timer.stop()
            except RuntimeError:
                return
            self.setVisible(False)

    def _tick_dots(self):
        self._dot_count = (self._dot_count + 1) % 4
        self._update_text()

    def _tick_phrase(self):
        self._phrase_index = (self._phrase_index + 1) % len(self.phrases)
        self._update_text()

    def set_phrase(self, phrase):
        self._manual_phrase = phrase
        if phrase is not None:
            try:
                self._phrase_timer.stop()
            except RuntimeError:
                return
        self._update_text()

    def _update_text(self):
        try:
            if self._manual_phrase:
                dots = "." * self._dot_count
                self.label.setText(f"{self._manual_phrase}{dots}")
                return
            if not self.phrases:
                self.label.setText("")
                return
            dots = "." * self._dot_count
            self.label.setText(f"{self.phrases[self._phrase_index]}{dots}")
        except RuntimeError:
            return


class FeedbackRow(QWidget):
    def __init__(self):
        super().__init__()
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        def _btn_style():
            return (
                "QPushButton {"
                " background-color: rgba(255, 255, 255, 0.08);"
                " color: #E6E6E6;"
                " border: none;"
                " border-radius: 10px;"
                " padding: 3px 10px;"
                " font-family: 'Poppins';"
                " font-size: 11px;"
                " font-weight: 500;"
                " min-width: 28px;"
                "}"
                "QPushButton:hover { background-color: rgba(255, 255, 255, 0.14); }"
            )

        good_icon_path = _resolve_resource_path("Vector Good.png")
        bad_icon_path = _resolve_resource_path("Vector Bad.png")
        copy_icon_path = _resolve_resource_path("Vector copy icon.png")

        self.good_btn = QPushButton()
        self.good_btn.setCursor(Qt.PointingHandCursor)
        self.good_btn.setToolTip("Good")
        self.good_btn.setStyleSheet(_btn_style())
        if os.path.exists(good_icon_path):
            self.good_btn.setIcon(QIcon(QPixmap(good_icon_path)))
            self.good_btn.setIconSize(QSize(16, 16))

        self.bad_btn = QPushButton()
        self.bad_btn.setCursor(Qt.PointingHandCursor)
        self.bad_btn.setToolTip("Bad")
        self.bad_btn.setStyleSheet(_btn_style())
        if os.path.exists(bad_icon_path):
            self.bad_btn.setIcon(QIcon(QPixmap(bad_icon_path)))
            self.bad_btn.setIconSize(QSize(16, 16))

        self.copy_btn = QPushButton()
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setToolTip("Copy")
        self.copy_btn.setStyleSheet(_btn_style())
        if os.path.exists(copy_icon_path):
            self.copy_btn.setIcon(QIcon(QPixmap(copy_icon_path)))
            self.copy_btn.setIconSize(QSize(16, 16))

        row_layout.addWidget(self.good_btn)
        row_layout.addWidget(self.bad_btn)
        row_layout.addWidget(self.copy_btn)
        main = QHBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(row, 0, Qt.AlignLeft)

    def set_handlers(self, on_good=None, on_bad=None, on_copy=None):
        if on_good is not None:
            self.good_btn.clicked.connect(on_good)
        if on_bad is not None:
            self.bad_btn.clicked.connect(on_bad)
        if on_copy is not None:
            self.copy_btn.clicked.connect(on_copy)

    def set_selected(self, kind):
        if kind == "good":
            self.good_btn.setEnabled(False)
            self.bad_btn.setEnabled(False)
            self.good_btn.setStyleSheet(
                "QPushButton { background-color: #2f3a2f; color: #E6FFE6; border: none; border-radius: 10px; padding: 3px 10px; font-family: 'Poppins'; font-size: 11px; font-weight: 600; }"
            )
        elif kind == "bad":
            self.good_btn.setEnabled(False)
            self.bad_btn.setEnabled(False)
            self.bad_btn.setStyleSheet(
                "QPushButton { background-color: #3a2a2a; color: #FFECEC; border: none; border-radius: 10px; padding: 3px 10px; font-family: 'Poppins'; font-size: 11px; font-weight: 600; }"
            )


class AuthorizationPromptWidget(QWidget):
    def __init__(self, command, on_allow, on_deny):
        super().__init__()
        clean_command = (command or "").strip()
        prompt_text = f"Do you want to {clean_command}?" if clean_command else "Do you want to continue?"

        row = QHBoxLayout(self)
        row.setContentsMargins(20, 6, 20, 6)
        row.setSpacing(0)
        body = QLabel(prompt_text)
        body.setWordWrap(True)
        body.setStyleSheet("color: #FFFFFF; font-family: 'Poppins'; font-size: 13px; font-weight: 500; padding: 2px 0px;")

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addStretch()

        allow_btn = QPushButton("Allow")
        allow_btn.setCursor(Qt.PointingHandCursor)
        allow_btn.setFixedHeight(32)
        allow_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #FFFFFF;
                color: #111111;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-family: 'Poppins';
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover { background-color: #EAEAEA; }
            """
        )
        allow_btn.clicked.connect(on_allow)

        deny_btn = QPushButton("Deny")
        deny_btn.setCursor(Qt.PointingHandCursor)
        deny_btn.setFixedHeight(32)
        deny_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2C2C2C;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-family: 'Poppins';
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover { background-color: #383838; }
            """
        )
        deny_btn.clicked.connect(on_deny)

        actions.addWidget(allow_btn)
        actions.addWidget(deny_btn)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(6)
        container_layout.addWidget(body)
        container_layout.addLayout(actions)
        row.addWidget(container, 1)


class RoundedWidget(QWidget):
    def __init__(self, radius=50, parent=None):
        super().__init__(parent)
        self.radius = radius
        self.setAttribute(Qt.WA_StyledBackground, True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        effective_radius = min(self.radius, self.width() // 2, self.height() // 2)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), effective_radius, effective_radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))


class ChatInputTextEdit(QTextEdit):
    sendRequested = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            event.accept()
            self.sendRequested.emit()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        # Remove the Unicode control character submenu for a cleaner UI.
        for action in list(menu.actions()):
            if "Unicode control character" in action.text():
                menu.removeAction(action)
                break
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        menu.setWindowFlags(
            menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        )
        menu.setStyleSheet(
            """
            QMenu {
                background-color: #0f1113;
                color: #F2F2F2;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 12px;
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
            """
        )
        menu.exec_(event.globalPos())


class GlassRail(QWidget):
    """Left app-rail widget that paints with CompositionMode_Source to match TitleBar exactly."""
    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def _resolve_color(self):
        fallback = QColor(0, 0, 0, 51)
        glass_bg = getattr(self.window, "glass_bg", "")
        if isinstance(glass_bg, str):
            m = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)", glass_bg.strip())
            if m:
                r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                a = float(m.group(4))
                return QColor(r, g, b, max(0, min(255, int(a * 255))))
        return fallback

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), self._resolve_color())
        # Right border stroke.
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setPen(QPen(QColor(25, 25, 25), 1.0))
        w = self.rect().width()
        painter.drawLine(QPointF(w - 0.5, 0), QPointF(w - 0.5, self.rect().height()))
        painter.end()


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.drag_position = None
        self.bg_color = self._resolve_topbar_color()
        self.icon_color = QColor("#BBBBBB")

        self.setFixedHeight(44)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                color: #BBBBBB;
                border: none;
                border-radius: 0px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                font-weight: 300;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.10);
            }
            QPushButton#closeBtn:hover {
                background-color: #E81123;
                color: #FFFFFF;
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignVCenter)

        # Get the directory where the script is located
        logo_path = _resolve_resource_path("Opuntia logo 500px.png")

        self.logo_label = QLabel()
        self.logo_label.setStyleSheet("padding-left: 16px;")

        # Load and scale the logo
        if os.path.exists(logo_path):
            logo_pixmap = QPixmap(logo_path)
            scaled_logo = logo_pixmap.scaled(
                36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.logo_label.setPixmap(scaled_logo)

        layout.addWidget(self.logo_label)
        layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(0)

        self.min_btn = QPushButton("")
        self.min_btn.setFixedSize(50, 44)
        self.min_btn.setCursor(Qt.PointingHandCursor)
        self.min_btn.setIcon(QIcon(self._window_btn_icon("min", 16)))
        self.min_btn.setIconSize(QSize(16, 16))
        self.min_btn.clicked.connect(self.window.showMinimized)
        button_layout.addWidget(self.min_btn)

        self.max_btn = QPushButton("")
        self.max_btn.setFixedSize(50, 44)
        self.max_btn.setCursor(Qt.PointingHandCursor)
        self.max_btn.setIcon(QIcon(self._window_btn_icon("max", 16)))
        self.max_btn.setIconSize(QSize(16, 16))
        self.max_btn.clicked.connect(self._toggle_maximize)
        button_layout.addWidget(self.max_btn)

        self.close_btn = QPushButton("")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setFixedSize(50, 44)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setIcon(QIcon(self._window_btn_icon("close", 16)))
        self.close_btn.setIconSize(QSize(16, 16))
        self.close_btn.clicked.connect(self.window.close)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def _resolve_topbar_color(self):
        fallback = QColor(0, 0, 0, 51)  # matches dark glass palette
        glass_bg = getattr(self.window, "glass_bg", "")
        color_src = glass_bg or getattr(self.window, "sidebar_color", "")
        if isinstance(color_src, str):
            m = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([0-9.]+)\)", color_src.strip())
            if m:
                r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                a = float(m.group(4))
                return QColor(r, g, b, max(0, min(255, int(a * 255))))
        return fallback

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())

        # Match the sidebar glass tone.
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(rect, self.bg_color)
        # Bottom border stroke.
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setPen(QPen(QColor(25, 25, 25), 1.0))
        painter.drawLine(QPointF(0, rect.height() - 0.5), QPointF(rect.width(), rect.height() - 0.5))
        painter.end()

    def _window_btn_icon(self, kind, size=16):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self.icon_color, 1.45, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if kind == "min":
            y = int(size * 0.62)
            p.drawLine(3, y, size - 3, y)
        elif kind == "max":
            p.drawRect(QRectF(3.4, 3.4, size - 6.8, size - 6.8))
        elif kind == "restore":
            p.drawRect(QRectF(5.0, 3.0, 8.0, 8.0))
            p.drawRect(QRectF(3.0, 5.0, 8.0, 8.0))
        else:
            p.drawLine(4, 4, size - 4, size - 4)
            p.drawLine(size - 4, 4, 4, size - 4)
        p.end()
        return pix

    def _toggle_maximize(self):
        if self.window.isMaximized():
            self.window.showNormal()
            self.max_btn.setIcon(QIcon(self._window_btn_icon("max", 16)))
        else:
            self.window.showMaximized()
            self.max_btn.setIcon(QIcon(self._window_btn_icon("restore", 16)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.window.frameGeometry().topLeft()
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_position is not None:
            if not self.window.isMaximized():
                self.window.move(event.globalPos() - self.drag_position)
                event.accept()
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()
        super().mouseDoubleClickEvent(event)


class ScreenShareOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        )
        self._green = QColor(48, 210, 116, 225)
        self._anim_phase = 0.0
        self._anim_timer = QTimer(self)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._anim_timer.setInterval(70)
        self._anim_timer.timeout.connect(self._tick_animation)

    def cover_primary_screen(self):
        from PyQt5.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())

    def _tick_animation(self):
        self._anim_phase += 0.13
        if self._anim_phase > 1000:
            self._anim_phase = 0.0
        self.update()

    def start_animation(self):
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def stop_animation(self):
        if self._anim_timer.isActive():
            self._anim_timer.stop()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        pulse = (math.sin(self._anim_phase) + 1.0) * 0.5
        inset = 4
        rect = self.rect().adjusted(inset, inset, -inset, -inset)

        glow_alpha = int(52 + 56 * pulse)
        glow = QPen(QColor(52, 230, 126, glow_alpha), 3.4 + (0.8 * pulse))
        glow.setJoinStyle(Qt.RoundJoin)
        p.setPen(glow)
        p.drawRoundedRect(rect, 8, 8)

        edge = QPen(self._green, 1.0)
        edge.setJoinStyle(Qt.RoundJoin)
        p.setPen(edge)
        p.drawRoundedRect(rect, 8, 8)
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  FileCard  — shown in chat after a file is generated by Opuntia
# ══════════════════════════════════════════════════════════════════════════════

class FileCard(QWidget):
    """
    Compact file card widget displayed below an AI bubble after Opuntia
    generates a document.  Features:
      • Colour-coded icon per file type
      • File name + human-readable size
      • Open button   — opens the file with its default application
      • Save As button — lets the user copy the file to any location
      • Drag support  — drag the card onto a folder / Explorer window
    """

    # Map extension → (icon letter, background colour)
    _TYPE_MAP = {
        "pdf":  ("PDF",  "#E53E3E"),
        "docx": ("DOC",  "#2563EB"),
        "doc":  ("DOC",  "#2563EB"),
        "xlsx": ("XLS",  "#16A34A"),
        "xls":  ("XLS",  "#16A34A"),
        "csv":  ("CSV",  "#059669"),
        "pptx": ("PPT",  "#EA580C"),
        "ppt":  ("PPT",  "#EA580C"),
        "txt":  ("TXT",  "#6366F1"),
        "png":  ("IMG",  "#7C3AED"),
        "jpg":  ("IMG",  "#7C3AED"),
        "jpeg": ("IMG",  "#7C3AED"),
        "gif":  ("IMG",  "#7C3AED"),
        "mp4":  ("VID",  "#DB2777"),
        "mp3":  ("AUD",  "#B45309"),
        "zip":  ("ZIP",  "#475569"),
        "py":   ("PY",   "#0EA5E9"),
        "js":   ("JS",   "#CA8A04"),
    }

    def __init__(self, file_path, file_name=None, file_size=None, file_type=None, parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self._file_name = file_name or os.path.basename(file_path)
        self._file_size = file_size or self._calc_size(file_path)
        ext = (file_type or os.path.splitext(self._file_name)[1].lower().lstrip(".")).lower()
        icon_lbl, icon_color = self._TYPE_MAP.get(ext, ("FILE", "#64748B"))
        self._drag_start_pos = QPoint()
        self._dragging = False

        self.setFixedHeight(58)
        self.setMinimumWidth(220)
        self.setMaximumWidth(400)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setStyleSheet(
            "FileCard {"
            "  background-color: rgba(255,255,255,0.07);"
            "  border: 1px solid rgba(255,255,255,0.12);"
            "  border-radius: 14px;"
            "}"
            "FileCard:hover {"
            "  background-color: rgba(255,255,255,0.13);"
            "  border: 1px solid rgba(255,255,255,0.22);"
            "}"
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 0, 14, 0)
        root.setSpacing(10)

        # ── Coloured type icon ───────────────────────────────────────────────
        icon_box = QLabel(icon_lbl)
        icon_box.setFixedSize(38, 38)
        icon_box.setAlignment(Qt.AlignCenter)
        icon_box.setStyleSheet(
            f"QLabel {{"
            f"  background-color: {icon_color};"
            f"  color: #FFFFFF;"
            f"  font-family: 'Poppins';"
            f"  font-size: 9px;"
            f"  font-weight: 700;"
            f"  border-radius: 8px;"
            f"}}"
        )
        root.addWidget(icon_box, 0, Qt.AlignVCenter)

        # ── Name + size ──────────────────────────────────────────────────────
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(2)

        name_lbl = QLabel(self._file_name)
        name_lbl.setStyleSheet(
            "QLabel {"
            "  color: #FFFFFF;"
            "  font-family: 'Poppins';"
            "  font-size: 13px;"
            "  font-weight: 600;"
            "  background: transparent;"
            "  border: none;"
            "}"
        )
        name_lbl.setMaximumWidth(260)
        fm = name_lbl.fontMetrics()
        elided = fm.elidedText(self._file_name, Qt.ElideMiddle, 260)
        name_lbl.setText(elided)
        name_lbl.setToolTip(self._file_name)

        size_lbl = QLabel(f"{ext.upper()} · {self._file_size}")
        size_lbl.setStyleSheet(
            "QLabel {"
            "  color: rgba(255,255,255,0.45);"
            "  font-family: 'Poppins';"
            "  font-size: 11px;"
            "  background: transparent;"
            "  border: none;"
            "}"
        )

        info_col.addWidget(name_lbl)
        info_col.addWidget(size_lbl)
        root.addLayout(info_col, 1)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _calc_size(path):
        try:
            sz = os.path.getsize(path)
            if sz < 1024:
                return f"{sz} B"
            if sz < 1024 * 1024:
                return f"{sz / 1024:.1f} KB"
            return f"{sz / 1024 / 1024:.1f} MB"
        except Exception:
            return "—"

    # ── Actions ──────────────────────────────────────────────────────────────

    def _open_file(self):
        if os.path.exists(self._file_path):
            try:
                os.startfile(self._file_path)
            except Exception:
                import subprocess
                try:
                    subprocess.Popen(["explorer", "/select,", self._file_path])
                except Exception:
                    pass
        else:
            self._show_missing()

    def _save_as(self):
        if not os.path.exists(self._file_path):
            self._show_missing()
            return
        ext = os.path.splitext(self._file_name)[1]
        _filters = {
            ".pdf":  "PDF Files (*.pdf)",
            ".docx": "Word Documents (*.docx)",
            ".doc":  "Word Documents (*.doc)",
            ".xlsx": "Excel Workbooks (*.xlsx)",
            ".xls":  "Excel Workbooks (*.xls)",
            ".csv":  "CSV Files (*.csv)",
            ".pptx": "PowerPoint Presentations (*.pptx)",
            ".txt":  "Text Files (*.txt)",
            ".png":  "PNG Images (*.png)",
            ".jpg":  "JPEG Images (*.jpg)",
        }
        f_filter = _filters.get(ext.lower(), "All Files (*.*)")
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Save file as",
            os.path.join(os.path.expanduser("~"), "Desktop", self._file_name),
            f"{f_filter};;All Files (*.*)",
        )
        if dest:
            import shutil
            try:
                shutil.copy2(self._file_path, dest)
            except Exception as e:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Save failed", str(e))

    def _show_missing(self):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.warning(
            self,
            "File not found",
            f"The file no longer exists at:\n{self._file_path}",
        )

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setAttribute(Qt.WA_TranslucentBackground, True)
        menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        menu.setStyleSheet(
            "QMenu {"
            "  background-color: #0f1113;"
            "  color: #F2F2F2;"
            "  border: 1px solid rgba(255,255,255,0.14);"
            "  border-radius: 12px;"
            "  padding: 6px;"
            "}"
            "QMenu::item { padding: 8px 16px; margin: 2px 4px; border-radius: 8px; }"
            "QMenu::item:selected { background-color: rgba(255,255,255,0.12); }"
        )
        save_action   = menu.addAction("Save As…")
        copy_action   = menu.addAction("Copy path")
        reveal_action = menu.addAction("Show in Explorer")
        chosen = menu.exec_(self.mapToGlobal(pos))
        if chosen == save_action:
            self._save_as()
        elif chosen == copy_action:
            QApplication.clipboard().setText(self._file_path)
        elif chosen == reveal_action:
            import subprocess
            try:
                subprocess.Popen(["explorer", "/select,", self._file_path])
            except Exception:
                pass

    # ── Mouse events ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < 10:
            return
        if not os.path.exists(self._file_path):
            return
        self._dragging = True
        self.setCursor(Qt.ClosedHandCursor)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(self._file_path)])
        mime.setText(self._file_path)
        drag.setMimeData(mime)
        pix = QPixmap(self.size())
        pix.fill(Qt.transparent)
        self.render(pix)
        drag.setPixmap(pix.scaled(200, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        drag.setHotSpot(QPoint(100, 23))
        drag.exec_(Qt.CopyAction | Qt.MoveAction)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._dragging:
            self._open_file()
        self._dragging = False
        self.setCursor(Qt.PointingHandCursor)
        super().mouseReleaseEvent(event)
