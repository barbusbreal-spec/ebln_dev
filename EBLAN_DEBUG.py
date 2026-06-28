from PyQt6 import QtCore
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from PyQt6.QtWebEngineWidgets import *
from PyQt6.QtPrintSupport import *
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply, QNetworkProxy
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

import os
import re
import requests
import sys
import json
import tempfile
import shutil
import zipfile
import random
import time
import base64
import socket
import subprocess
import threading
import urllib.parse
from dataclasses import dataclass, field, asdict
from datetime import datetime


class FPSOverlay(QWidget):
    """Геймерский FPS-оверлей. Показывает всегда 1000+ FPS,
    при этом реально роняет производительность тяжёлыми вычислениями."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(220, 110)

        self._drag_pos = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(2)

        self._container = QFrame(self)
        self._container.setObjectName("fpsContainer")
        self._container.setStyleSheet("""
            QFrame#fpsContainer {
                background: rgba(0, 0, 0, 190);
                border: 2px solid #00ff66;
                border-radius: 8px;
            }
            QLabel { color: #00ff66; background: transparent; }
            QLabel#fpsValue {
                color: #00ff66;
                font-family: 'Courier New', monospace;
                font-size: 30px;
                font-weight: 900;
            }
            QLabel#fpsUnit {
                color: #00ff66;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                font-weight: bold;
            }
            QLabel#fpsInfo {
                color: #88ff88;
                font-family: 'Courier New', monospace;
                font-size: 10px;
            }
        """)
        cont_layout = QVBoxLayout(self._container)
        cont_layout.setContentsMargins(10, 6, 10, 6)
        cont_layout.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(6)
        self._fps_label = QLabel("1488")
        self._fps_label.setObjectName("fpsValue")
        unit = QLabel("FPS")
        unit.setObjectName("fpsUnit")
        unit.setAlignment(Qt.AlignmentFlag.AlignBottom)
        top.addWidget(self._fps_label)
        top.addWidget(unit)
        top.addStretch()
        cont_layout.addLayout(top)

        self._gpu_label = QLabel("GPU: хз")
        self._gpu_label.setObjectName("fpsInfo")
        cont_layout.addWidget(self._gpu_label)

        self._ping_label = QLabel("PING: 0 ms   MEM: 0.1 KB")
        self._ping_label.setObjectName("fpsInfo")
        cont_layout.addWidget(self._ping_label)

        root.addWidget(self._container)

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._refresh)
        self._update_timer.start(120)

        # "нагрузочный" таймер — роняет производительность
        self._lag_timer = QTimer(self)
        self._lag_timer.timeout.connect(self._burn_cpu)
        self._lag_timer.start(40)

    def _refresh(self):
        fps = random.randint(1000, 9999)
        self._fps_label.setText(str(fps))
        ping = random.randint(1, 9)
        mem = round(random.uniform(0.1, 0.9), 1)
        self._ping_label.setText(f"PING: {ping} ms   MEM: {mem} GB")

    def _burn_cpu(self):
        # Настоящее падение производительности (привет, геймеры)
        s = 0.0
        for i in range(120000):
            s += (i * 1.00001) ** 0.5
        # чтобы оптимизатор не выкинул переменную
        self._gpu_label.setAccessibleDescription(str(s))

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag_pos is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._drag_pos = None

    def stop(self):
        try:
            self._update_timer.stop()
            self._lag_timer.stop()
        except Exception:
            pass
        self.hide()
        self.deleteLater()


def format_wasted(seconds):
    """Форматирует количество проёбанных секунд в д/ч/м/с."""
    try:
        seconds = int(max(0, seconds))
    except Exception:
        return "0с"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}д")
    if hours or days:
        parts.append(f"{hours}ч")
    if minutes or hours or days:
        parts.append(f"{minutes}м")
    parts.append(f"{secs}с")
    return " ".join(parts)


def wasted_level(seconds):
    """Возвращает (звание, подпись) по количеству проёбанных часов."""
    h = seconds / 3600.0
    if h < 1:
        return ("Новичок-еблан", "Ещё можешь спастись, беги пока не поздно")
    if h < 5:
        return ("Студент-еблан", "Ну ок, бывает")
    if h < 20:
        return ("Опытный еблан", "Бабушка бы не одобрила")
    if h < 50:
        return ("Конкретный еблан", "Пора задуматься")
    if h < 100:
        return ("Эпический еблан", "Ты легенда, но это не комплимент")
    if h < 500:
        return ("Мегаеблан", "Жизнь прошла мимо")
    return ("ЕБЛАН-БОГ", "Тебя нельзя спасти. Смирись.")


# ============================================================
#   Ecss — Eblan CSS: простой DSL для кастомных тем браузера.
#   Транспилируется в QSS и применяется к QApplication целиком.
# ============================================================

ECSS_PRESETS = {
    "Стандартная (выкл)": "",

    "Еблан Оригинал": """# Дефолтная тёмная тема Еблан
window_bg: #2b2a33
text_color: #fbfbfe
accent: #00ddff
tab_bg: #1c1b22
tab_active: #2b2a33
toolbar_bg: #23222b
urlbar_bg: #1c1b22
urlbar_text: #fbfbfe
button_bg: #2b2a33
button_text: #fbfbfe
button_hover: #52525e
border: #3a3944
font_family: Segoe UI
font_size: 13
radius: 4
""",

    "Хакер (зелёный на чёрном)": """# Привет, Нео
window_bg: #000000
text_color: #00ff41
accent: #00ff41
tab_bg: #050505
tab_active: #000000
toolbar_bg: #030303
urlbar_bg: #050505
urlbar_text: #00ff41
button_bg: #0a0a0a
button_text: #00ff41
button_hover: #003b0f
border: #00ff41
font_family: Consolas
font_size: 13
radius: 0
""",

    "Розовый Пиздец": """# Для ценительниц
window_bg: #ff6bcb
text_color: #ffffff
accent: #ff006e
tab_bg: #e91e63
tab_active: #ff6bcb
toolbar_bg: #d81b60
urlbar_bg: #ffffff
urlbar_text: #000000
button_bg: #ff1493
button_text: #ffffff
button_hover: #ff006e
border: #ff006e
font_family: Comic Sans MS
font_size: 14
radius: 20
""",

    "Киберпанк 2077": """# V, выйди из браузера
window_bg: #0a0e27
text_color: #ffe600
accent: #ff006e
tab_bg: #1a1f3a
tab_active: #0a0e27
toolbar_bg: #0f1428
urlbar_bg: #1a1f3a
urlbar_text: #ffe600
button_bg: #ff006e
button_text: #0a0e27
button_hover: #ffe600
border: #ff006e
font_family: Consolas
font_size: 13
radius: 2
""",

    "Жёлтый Понос": """# Меньше слов, больше жёлтого
window_bg: #fff89a
text_color: #4a3b00
accent: #ffb400
tab_bg: #ffe066
tab_active: #fff89a
toolbar_bg: #ffd23f
urlbar_bg: #fffde7
urlbar_text: #4a3b00
button_bg: #ffb400
button_text: #4a3b00
button_hover: #ff8800
border: #b07d00
font_family: Arial
font_size: 13
radius: 6
""",

    "Вахта 2003": """# Windows XP, но без лицензии
window_bg: #ece9d8
text_color: #000000
accent: #0a246a
tab_bg: #f1efe2
tab_active: #ffffff
toolbar_bg: #d4d0c8
urlbar_bg: #ffffff
urlbar_text: #000000
button_bg: #ece9d8
button_text: #000000
button_hover: #c1d2ee
border: #716f64
font_family: Tahoma
font_size: 12
radius: 3
""",
}


# ============================================================
#   ЗУМЕР-РЕЖИМ (молодёжные фишки, передоз) 💀🔥
# ============================================================

BRAINROT_PHRASES = [
    "скибиди 🚽", "rizz +100 😎", "сигма-вайб активен 🗿", "based 💯",
    "no cap fr fr 🧢", "это W 🏆", "gyatt 😳", "Огайо 💀", "вайб-чек ✅",
    "+9999 aura ✨", "он реально кук 🍳", "мьюинг 🤫🧏", "fanum tax 🍔",
    "this is bussin 🔥", "skill issue 💀", "GG izi 🎮", "чел поймал W 🦅",
    "галя, отмена 🛑", "лютый кринж 😭", "ёмаё это пик 📈", "слэй 💅",
    "six seven 🤙 6️⃣7️⃣", "67 mood fr 💯", "тут пахнет W 🦅", "мог ⬆️",
    "глейзинг детектед 🫧", "luckmaxxing 🍀", "гриндим ауру 🌀", "пик перформанс 📊",
    "это так 67 🤙", "ratio + L + ты кук 🍳", "demure 💅 mindful", "беттер колл 67",
]

# Сигма-цитаты (мотивационный брейнрот)
SIGMA_QUOTES = [
    "Сигма не объясняет — сигма делает. 🗿",
    "Пока ты спал, я фармил ауру. 🌀",
    "67 — это не число, это образ жизни. 🤙",
    "Меньше слов, больше мьюинга. 🤫🧏",
    "Они хейтят, потому что не могут в W. 🦅",
    "Твой лимит — это твоё воображение и баланс Еблан Кеша. 💸",
    "Настоящий чад не глейзит. Чад могает. ⬆️",
    "Тишина — лучший рицз. 😎",
]

# Konami-код: ↑ ↑ ↓ ↓ ← → ← → B A
KONAMI_SEQ = [
    Qt.Key.Key_Up, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Down,
    Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Left, Qt.Key.Key_Right,
    Qt.Key.Key_B, Qt.Key.Key_A,
]


class ConfettiOverlay(QWidget):
    """Прозрачный клик-сквозной оверлей: дождь эмодзи. Сам себя закрывает."""

    EMOJIS = ["💀", "🔥", "😎", "🗿", "✨", "💯", "🤙", "👽", "🎮", "🥶",
              "🤡", "💅", "🫡", "😭", "🤓", "🦅", "🍕", "🚀", "⚡", "🥵", "🧢"]

    def __init__(self, parent, duration_ms=2600, count=46):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        try:
            if parent is not None:
                self.setGeometry(parent.geometry())
        except Exception:
            self.resize(900, 600)

        import random as _r
        w = max(self.width(), 400)
        h = max(self.height(), 300)
        self._parts = []
        for _ in range(count):
            self._parts.append({
                "x": _r.randint(0, w), "y": _r.randint(-h, 0),
                "vy": _r.uniform(4.0, 11.0), "vx": _r.uniform(-2.0, 2.0),
                "rot": _r.uniform(0, 360), "vr": _r.uniform(-12, 12),
                "size": _r.randint(18, 40), "e": _r.choice(self.EMOJIS),
            })
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(16)
        QTimer.singleShot(int(duration_ms), self._finish)
        self.show()
        self.raise_()

    def _step(self):
        h = max(self.height(), 1)
        for p in self._parts:
            p["y"] += p["vy"]
            p["x"] += p["vx"]
            p["rot"] += p["vr"]
            if p["y"] > h + 40:
                p["y"] = -20
        self.update()

    def _finish(self):
        try:
            self._timer.stop()
        except Exception:
            pass
        self.close()
        self.deleteLater()

    def paintEvent(self, event):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            f = QFont()
            for part in self._parts:
                f.setPointSize(part["size"])
                p.setFont(f)
                p.save()
                p.translate(part["x"], part["y"])
                p.rotate(part["rot"])
                p.drawText(0, 0, part["e"])
                p.restore()
            p.end()
        except Exception:
            pass


class SufferOverlay(QWidget):
    """Режим Палестины / страдания: чёрный квадрат поверх контента.

    Применяется навсегда (сохраняется в настройках, поднимается на старте).
    Единственный выход — отстрадать: кликнуть по квадрату ровно 67 раз.
    """

    ESCAPE_CLICKS = 67

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.clicks = 0
        self.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.setAutoFillBackground(True)
        self.setStyleSheet("background: #000000;")

    def mousePressEvent(self, ev):
        self.clicks += 1
        if self.clicks >= self.ESCAPE_CLICKS:
            try:
                self.mw.disable_suffer_mode()
            except Exception:
                pass
            return
        self.update()
        super().mousePressEvent(ev)

    def paintEvent(self, event):
        try:
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(0, 0, 0))
            # Еле заметный текст страдания — тёмно-серый на чёрном.
            p.setPen(QColor(28, 28, 28))
            f = QFont(); f.setPointSize(22); f.setBold(True); p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "СТРАДАЙ")
            f2 = QFont(); f2.setPointSize(10); p.setFont(f2)
            left = max(0, self.ESCAPE_CLICKS - self.clicks)
            r = self.rect().adjusted(0, 60, 0, 0)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter,
                       f"чтобы отстрадать — кликни ещё {left} раз")
            p.end()
        except Exception:
            pass


class MatrixOverlay(QWidget):
    """Зелёный матрица-дождь поверх окна. Клик-сквозной, сам себя закрывает."""

    GLYPHS = "01アイウエオカキ㐀67ﾊﾋﾌﾍﾎ$#%&@67"

    def __init__(self, parent, duration_ms=4200):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        try:
            if parent is not None:
                self.setGeometry(parent.geometry())
        except Exception:
            self.resize(900, 600)
        import random as _r
        cols = max(10, self.width() // 16)
        self._cols = cols
        self._drops = [_r.randint(-40, 0) for _ in range(cols)]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(60)
        QTimer.singleShot(int(duration_ms), self._finish)
        self.show(); self.raise_()

    def _step(self):
        import random as _r
        h = max(self.height(), 1)
        for i in range(self._cols):
            self._drops[i] += 1
            if self._drops[i] * 16 > h and _r.random() > 0.95:
                self._drops[i] = 0
        self.update()

    def _finish(self):
        try:
            self._timer.stop()
        except Exception:
            pass
        self.close(); self.deleteLater()

    def paintEvent(self, event):
        import random as _r
        try:
            p = QPainter(self)
            f = QFont("Courier New", 13); p.setFont(f)
            for i in range(self._cols):
                x = i * 16
                y = self._drops[i] * 16
                p.setPen(QColor(180, 255, 180))
                p.drawText(x, y, _r.choice(self.GLYPHS))
                p.setPen(QColor(0, 200, 0))
                for k in range(1, 8):
                    p.drawText(x, y - k * 16, _r.choice(self.GLYPHS))
            p.end()
        except Exception:
            pass


class BsodOverlay(QWidget):
    """Фейковый синий экран смерти. Без мигания. Закрывается по клику."""

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        try:
            self.setGeometry(parent.geometry())
        except Exception:
            self.resize(900, 600)
        self.setStyleSheet("background: #0078d7;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(80, 80, 80, 80)
        txt = QLabel(
            ":(\n\n"
            "На твоём ПК возникла проблема, и теперь ты еблан.\n"
            "Мы соберём твою ауру и Еблан Кеш, а потом перезагрузим\n"
            "твоё чувство собственного достоинства.\n\n"
            "67% завершено\n\n"
            "Код ошибки: SIX_SEVEN_FOREVER\n\n"
            "(кликни в любом месте, чтобы продолжить страдания)"
        )
        txt.setStyleSheet("color: white; font-size: 18px; font-family: 'Segoe UI', sans-serif;")
        big = QLabel(":(")
        big.setStyleSheet("color: white; font-size: 90px;")
        lay.addWidget(big)
        lay.addWidget(txt)
        lay.addStretch(1)

    def mousePressEvent(self, ev):
        self.close(); self.deleteLater()


class JumpscareOverlay(QWidget):
    """Мягкий джампскейр: большой 🗿 на пол-секунды. Без звука."""

    def __init__(self, parent, duration_ms=700):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        try:
            self.setGeometry(parent.geometry())
        except Exception:
            self.resize(900, 600)
        self.setStyleSheet("background: #000000;")
        QTimer.singleShot(int(duration_ms), self._finish)
        self.show(); self.raise_()

    def _finish(self):
        self.close(); self.deleteLater()

    def paintEvent(self, event):
        try:
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(0, 0, 0))
            f = QFont(); f.setPointSize(min(self.width(), self.height()) // 3); p.setFont(f)
            p.setPen(QColor(255, 255, 255))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "🗿")
            p.end()
        except Exception:
            pass


class AdOverlay(QWidget):
    """Полноэкранная «госреклама» (МАКС / VPN убивает). Закрывается кнопкой/кликом."""

    def __init__(self, parent, content):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setStyleSheet(f"background: {content.get('bg', '#0a3d91')};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(60, 60, 60, 60)
        lay.addStretch(1)

        title = QLabel(content.get("title", "РЕКЛАМА"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet("color: white; font-size: 40px; font-weight: 900;")
        lay.addWidget(title)

        body = QLabel(content.get("body", ""))
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        body.setStyleSheet("color: #f0f0f0; font-size: 20px; padding: 24px;")
        lay.addWidget(body)

        btn = QPushButton(content.get("btn", "Закрыть"))
        btn.setStyleSheet("font-size: 18px; padding: 12px 28px;")
        btn.clicked.connect(self._close)
        row = QHBoxLayout(); row.addStretch(1); row.addWidget(btn); row.addStretch(1)
        lay.addLayout(row)

        hint = QLabel("(это пародия. кликни в любом месте, чтобы закрыть)")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 12px;")
        lay.addWidget(hint)
        lay.addStretch(1)

    def _close(self):
        try:
            self.close(); self.deleteLater()
        except Exception:
            pass

    def mousePressEvent(self, ev):
        self._close()

    def keyPressEvent(self, ev):
        self._close()


# Куда класть фото оверлея (берётся первый существующий), иначе фолбэк.
OVERLAY_IMAGE_CANDIDATES = [
    os.path.join('images', 'kozel_overlay.jpg'),
    os.path.join('images', 'kozel_overlay.png'),
    os.path.join('images', 'eblan_overlay.png'),
    os.path.join('images', 'eblan_overlay.jpg'),
]
OVERLAY_IMAGE_FALLBACK = os.path.join('images', 'eblanai.png')


def load_overlay_pixmap():
    for path in OVERLAY_IMAGE_CANDIDATES:
        if os.path.exists(path):
            pm = QPixmap(path)
            if not pm.isNull():
                return pm
    return QPixmap(OVERLAY_IMAGE_FALLBACK)


class ImageOverlay(QWidget):
    """Фото на весь интерфейс: вращается и ПЛАВНО пульсирует прозрачностью.

    Пульсация намеренно мягкая (синус ~2 сек), без резкого стробоскопа —
    берегём фоточувствительных. Клик-сквозной, поэтому браузером под ним
    можно пользоваться.
    """

    CANDIDATES = OVERLAY_IMAGE_CANDIDATES
    FALLBACK = OVERLAY_IMAGE_FALLBACK

    def __init__(self, parent):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._pix = self._load_pixmap()
        self._angle = 0.0
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(33)  # ~30 FPS, плавно

    def _load_pixmap(self):
        return load_overlay_pixmap()

    def reload(self):
        self._pix = self._load_pixmap()
        self.update()

    def _step(self):
        self._angle = (self._angle + 3.0) % 360.0   # вращение
        self._phase += 0.05                          # фаза пульсации (медленно)
        self.update()

    def paintEvent(self, event):
        try:
            if self._pix is None or self._pix.isNull():
                return
            import math
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            # Плавная пульсация: 0.20..0.60, период ~2 сек — не строб.
            opacity = 0.20 + 0.40 * (0.5 + 0.5 * math.sin(self._phase))
            p.setOpacity(opacity)
            # Масштабируем картинку, чтобы покрывала окно даже при вращении.
            side = int(max(self.width(), self.height()) * 1.5)
            scaled = self._pix.scaled(
                side, side,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.translate(self.width() / 2, self.height() / 2)
            p.rotate(self._angle)
            p.drawPixmap(-scaled.width() // 2, -scaled.height() // 2, scaled)
            p.end()
        except Exception:
            pass


class WildOverlay(QWidget):
    """ДИКИЙ режим: быстрое мигание цветом + резкое вращение фото.

    ⚠️ ОПАСНО для людей с фоточувствительной эпилепсией. Поэтому:
      - запускается ТОЛЬКО после явного согласия в предупреждении;
      - мгновенно останавливается кликом или любой клавишей (ESC);
      - авто-стоп через FLASH_AUTO_STOP_MS, чтобы эффект не длился долго.
    """

    FLASH_INTERVAL_MS = 80         # частота мигания
    FLASH_AUTO_STOP_MS = 15000     # авто-стоп, чтобы никто не «завис» в стробе

    def __init__(self, parent, on_stop=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._on_stop = on_stop
        self._pix = load_overlay_pixmap()
        self._angle = 0.0
        self._color = QColor(0, 0, 0)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(self.FLASH_INTERVAL_MS)
        QTimer.singleShot(self.FLASH_AUTO_STOP_MS, self.stop)

    def _step(self):
        self._angle = (self._angle + random.randint(40, 120)) % 360.0
        self._color = QColor(
            random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
        )
        self.update()

    def stop(self):
        try:
            self._timer.stop()
        except Exception:
            pass
        cb = self._on_stop
        self._on_stop = None
        try:
            self.close(); self.deleteLater()
        except Exception:
            pass
        if cb:
            try:
                cb()
            except Exception:
                pass

    # Любой клик или клавиша — немедленный стоп.
    def mousePressEvent(self, ev):
        self.stop()

    def keyPressEvent(self, ev):
        self.stop()

    def paintEvent(self, event):
        try:
            p = QPainter(self)
            p.fillRect(self.rect(), self._color)
            if self._pix is not None and not self._pix.isNull():
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                side = int(max(self.width(), self.height()) * 1.4)
                scaled = self._pix.scaled(
                    side, side,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                p.translate(self.width() / 2, self.height() / 2)
                p.rotate(self._angle)
                p.drawPixmap(-scaled.width() // 2, -scaled.height() // 2, scaled)
                p.resetTransform()
            p.setPen(QColor(255, 255, 255))
            f = QFont(); f.setPointSize(12); f.setBold(True); p.setFont(f)
            p.drawText(self.rect().adjusted(0, 0, 0, -20),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                       "клик или ESC — СТОП")
            p.end()
        except Exception:
            pass


class EcssEngine:
    """Транспилятор Ecss → QSS.

    Синтаксис:
        # комментарий
        ключ: значение
        !raw
            ... произвольный QSS ...
        !end
    """

    DEFAULT_TOKENS = {
        "window_bg":    "#2b2a33",
        "text_color":   "#fbfbfe",
        "accent":       "#00ddff",
        "tab_bg":       "#1c1b22",
        "tab_active":   "#2b2a33",
        "toolbar_bg":   "#23222b",
        "urlbar_bg":    "#1c1b22",
        "urlbar_text":  "#fbfbfe",
        "button_bg":    "#2b2a33",
        "button_text":  "#fbfbfe",
        "button_hover": "#52525e",
        "border":       "#3a3944",
        "font_family":  "Segoe UI",
        "font_size":    "13",
        "radius":       "4",
    }

    @staticmethod
    def parse(source):
        """Парсит Ecss в dict токенов + опциональный raw-QSS блок."""
        tokens = {}
        raw_parts = []
        if not source:
            return tokens
        lines = source.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                i += 1
                continue
            if stripped.lower().startswith("!raw"):
                i += 1
                block = []
                while i < len(lines) and lines[i].strip().lower() != "!end":
                    block.append(lines[i])
                    i += 1
                raw_parts.append("\n".join(block))
                i += 1
                continue
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                key = key.strip().lower().replace("-", "_")
                value = value.strip()
                if value.endswith(";"):
                    value = value[:-1].strip()
                value = value.strip('"').strip("'")
                if key:
                    tokens[key] = value
            i += 1
        if raw_parts:
            tokens["__raw__"] = "\n".join(raw_parts)
        return tokens

    @classmethod
    def compile(cls, source):
        """Возвращает QSS-строку из Ecss-исходника."""
        if not source or not source.strip():
            return ""
        tokens = dict(cls.DEFAULT_TOKENS)
        tokens.update(cls.parse(source))
        raw = tokens.pop("__raw__", "")
        t = tokens

        def g(key):
            return t.get(key, cls.DEFAULT_TOKENS.get(key, ""))

        qss = f"""
/* ==== Ecss compiled theme ==== */
QMainWindow, QDialog {{
    background: {g("window_bg")};
    color: {g("text_color")};
}}
QWidget {{
    font-family: "{g("font_family")}";
    font-size: {g("font_size")}px;
    color: {g("text_color")};
}}
QToolBar {{
    background: {g("toolbar_bg")};
    border: none;
    spacing: 4px;
    padding: 4px;
}}
QToolBar QToolButton {{
    background: transparent;
    color: {g("text_color")};
    padding: 4px 6px;
    border-radius: {g("radius")}px;
}}
QToolBar QToolButton:hover {{
    background: {g("button_hover")};
}}
QTabWidget::pane {{
    border: 1px solid {g("border")};
    background: {g("window_bg")};
}}
QTabBar::tab {{
    background: {g("tab_bg")};
    color: {g("text_color")};
    padding: 8px 14px;
    border: 1px solid {g("border")};
    border-bottom: none;
    border-top-left-radius: {g("radius")}px;
    border-top-right-radius: {g("radius")}px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {g("tab_active")};
    color: {g("accent")};
}}
QTabBar::tab:hover {{
    background: {g("button_hover")};
}}
QLineEdit {{
    background: {g("urlbar_bg")};
    color: {g("urlbar_text")};
    border: 1px solid {g("border")};
    border-radius: {g("radius")}px;
    padding: 6px 10px;
    selection-background-color: {g("accent")};
}}
QLineEdit:focus {{
    border: 2px solid {g("accent")};
    padding: 5px 9px;
}}
QPushButton {{
    background: {g("button_bg")};
    color: {g("button_text")};
    border: 1px solid {g("border")};
    border-radius: {g("radius")}px;
    padding: 6px 12px;
}}
QPushButton:hover {{
    background: {g("button_hover")};
}}
QPushButton:pressed {{
    background: {g("accent")};
    color: {g("window_bg")};
}}
QMenuBar {{
    background: {g("toolbar_bg")};
    color: {g("text_color")};
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
}}
QMenuBar::item:selected {{
    background: {g("accent")};
    color: {g("window_bg")};
}}
QMenu {{
    background: {g("toolbar_bg")};
    color: {g("text_color")};
    border: 1px solid {g("border")};
}}
QMenu::item:selected {{
    background: {g("accent")};
    color: {g("window_bg")};
}}
QStatusBar {{
    background: {g("toolbar_bg")};
    color: {g("text_color")};
}}
QStatusBar QLabel {{
    color: {g("text_color")};
}}
QLabel {{
    color: {g("text_color")};
    background: transparent;
}}
QComboBox {{
    background: {g("urlbar_bg")};
    color: {g("urlbar_text")};
    border: 1px solid {g("border")};
    border-radius: {g("radius")}px;
    padding: 5px 8px;
}}
QComboBox QAbstractItemView {{
    background: {g("toolbar_bg")};
    color: {g("text_color")};
    selection-background-color: {g("accent")};
    selection-color: {g("window_bg")};
}}
QCheckBox {{
    color: {g("text_color")};
    spacing: 8px;
}}
QScrollBar:vertical {{
    background: {g("toolbar_bg")};
    width: 12px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {g("button_hover")};
    border-radius: {g("radius")}px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {g("accent")};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""
        if raw:
            qss += "\n/* ==== raw Ecss block ==== */\n" + raw + "\n"
        return qss

    @staticmethod
    def apply(source):
        """Применяет Ecss-тему к QApplication целиком. Пустая строка — сброс."""
        app = QApplication.instance()
        if app is None:
            return
        if not source or not source.strip():
            app.setStyleSheet("")
            return
        try:
            app.setStyleSheet(EcssEngine.compile(source))
        except Exception as e:
            print(f"[Ecss] Ошибка применения темы: {e}")


# ============================================================
#   UpdateService — клиент EBLAN Update Backend.
#
#   Поддерж������������вает два формата:
#     1) Новый бэкенд в папке backend/ — URL оканчивается на "/" или "index.php":
#        /api/manifest, /api/check?branch=&current=, /api/rollback
#     2) Старый плоский version.json (обратная совместимость).
# ============================================================

class UpdateService(QObject):
    """Тонкая обёртка над QNetworkAccessManager для обновлений."""

    # signal (success: bool, payload: dict, error: str)
    manifestLoaded = pyqtSignal(bool, dict, str)

    def __init__(self, parent, api_base_url):
        super().__init__(parent)
        self.api_base_url = (api_base_url or "").strip()
        self._network = QNetworkAccessManager(self)

    # -------- URL helpers --------
    def _is_legacy_json(self):
        """Старый формат: URL указывает прямо на version.json."""
        u = self.api_base_url.lower()
        return u.endswith(".json")

    def _endpoint(self, route, params=None):
        """Собирает URL эндпоинта для нового бэкенда."""
        base = self.api_base_url.rstrip("/")
        # index.php → index.php?route=...
        if base.lower().endswith("index.php"):
            url = QUrl(base)
            q = QUrlQuery()
            q.addQueryItem("route", route)
            if params:
                for k, v in params.items():
                    q.addQueryItem(k, str(v))
            url.setQuery(q)
            return url
        # иначе .htaccess rewrite: base/api/<route>
        full = f"{base}/api/{route}"
        url = QUrl(full)
        if params:
            q = QUrlQuery()
            for k, v in params.items():
                q.addQueryItem(k, str(v))
            url.setQuery(q)
        return url

    def _fallback_index_url(self, route):
        """Вариант ссылки через index.php?route=... (на случай отсутствия mod_rewrite)."""
        base = self.api_base_url.rstrip("/")
        if base.lower().endswith("index.php"):
            return None  # мы уже на index.php
        full = base + "/index.php"
        url = QUrl(full)
        q = QUrlQuery()
        q.addQueryItem("route", route)
        url.setQuery(q)
        return url

    # -------- public API --------
    def fetch_manifest(self):
        """Асинхронно загружает полный манифест. Результат — в manifestLoaded."""
        if not self.api_base_url:
            self.manifestLoaded.emit(False, {}, "empty_url")
            return

        if self._is_legacy_json():
            url = QUrl(self.api_base_url)
            allow_fallback = False
        else:
            url = self._endpoint("manifest")
            # fallback только если сейчас не index.php и не .json
            allow_fallback = not self.api_base_url.rstrip("/").lower().endswith("index.php")

        self._do_request(url, allow_fallback)

    def _do_request(self, url, allow_fallback):
        req = QNetworkRequest(url)
        # Браузерный UA, иначе serv00/nginx может ответить 403.
        try:
            req.setRawHeader(b"User-Agent", EB_HTTP_HEADERS["User-Agent"].encode("ascii"))
        except Exception:
            req.setRawHeader(b"User-Agent", b"Mozilla/5.0 EBLANBrowser/1.0")
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        reply = self._network.get(req)
        reply.finished.connect(lambda: self._on_manifest(reply, allow_fallback))

    def _on_manifest(self, reply, allow_fallback=False):
        try:
            err = reply.error()
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)

            # Автоматический откат на index.php?route=... при 404 от /api/manifest
            if allow_fallback and (status == 404 or err == QNetworkReply.NetworkError.ContentNotFoundError):
                fb = self._fallback_index_url("manifest")
                if fb is not None:
                    print(f"[updates] /api/manifest вернул 404, пробуем {fb.toString()}")
                    self._do_request(fb, allow_fallback=False)
                    return

            if err != QNetworkReply.NetworkError.NoError:
                self.manifestLoaded.emit(False, {}, reply.errorString())
                return
            raw = bytes(reply.readAll()).decode("utf-8", errors="replace")
            if not raw.strip():
                self.manifestLoaded.emit(False, {}, "empty_response")
                return
            try:
                data = json.loads(raw)
            except Exception as e:
                print(f"[updates] raw response (first 500 chars): {raw[:500]}")
                self.manifestLoaded.emit(False, {}, f"bad_json: {e}")
                return
            if not isinstance(data, dict):
                self.manifestLoaded.emit(False, {}, "bad_shape")
                return

            # Новый формат /api/manifest: {branches, rollback, meta}
            # Старый version.json: {branches, rollback}
            # Обе совместимы. Нормализуем:
            result = {
                "branches": data.get("branches", {}) or {},
                "rollback": data.get("rollback") or [],
                "meta":     data.get("meta", {}) or {},
            }
            self.manifestLoaded.emit(True, result, "")
        finally:
            try:
                reply.deleteLater()
            except Exception:
                pass


def get_settings_path():
    if sys.platform.startswith("win"):
        base = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "EBLAN")
    else:
        base = os.path.expanduser("~/etc/eblan")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "settings.json")


# ============================================================
#   ВЕРСИЯ 6.7 + экономика «Еблан Кеш»
#
#   Шуточная внутренняя валюта. Стартовый баланс — 200.
#   Чтобы войти в браузер, разово списывается 199 (остаётся 1).
#   За каждое действие капает немного кеша, на который в магазине
#   разблокируются «функции».
# ============================================================
EBLAN_VERSION = "6.7"
EBLAN_CASH_START = 200          # стартовый баланс
BROWSER_ENTRY_COST = 199        # разовая плата за вход в браузер

# Каталог магазина: feature_id -> (название, цена, описание)
EBLAN_SHOP = {
    "ai":        ("EBLAN AI",                 50, "Чат с нейронкой прямо в браузере."),
    "anon":      ("Анонимный режим",          40, "Приватное окно на Qwant без истории."),
    "gamer":     ("Геймер-режим SoftBoost™",  30, "FPS-оверлей 1488 и «ускорение»."),
    "themes":    ("Темы Ecss",                25, "Кастомные темы интерфейса."),
    "tonkeeper": ("Tonkeeper 2 (не скам)",    67, "Подключи свой TON-кошелёк. 100% не скам."),
}


# --- День Ебланов: 6 июля (6.7) ---------------------------------
EBLAN_DAY = (7, 6)              # (месяц, день) — 6 июля
EBLAN_DAY_BONUS = 670          # годовой подарок кеша в этот день
EBLAN_DAY_DISCOUNT = 0.33      # цены в магазине -67% в этот день


def is_eblan_day(dt=None):
    """True, если сегодня (или dt) — 6 июля, День Ебланов."""
    dt = dt or datetime.now()
    return (dt.month, dt.day) == EBLAN_DAY


# Иностранные домены, которые открывает «режим иноагента».
INOAGENT_TLDS = [".com", ".org", ".net"]

# Контент госрекламы (всплывает на весь экран каждые 30 сек, если включено).
AD_NAG_CONTENTS = [
    {
        "bg": "#0a3d91",
        "title": "📲 СКАЧАЙ МЕССЕНДЖЕР МАКС",
        "body": "Государственный. Безопасный. Обязательный.\n"
                "Все уже в МАКСе. А ты ещё нет?\n\n"
                "Установи МАКС — будь как все. 🇷🇺",
        "btn": "Установлю (нет)",
    },
    {
        "bg": "#7a0000",
        "title": "⚠️ VPN УБИВАЕТ",
        "body": "Каждый раз, когда ты включаешь VPN, где-то грустит чиновник.\n"
                "VPN — это не свобода, это измена. Отключи VPN — спаси Родину.\n\n"
                "Помни: тебя видно даже через прокси. 👁️",
        "btn": "Отключаю VPN (нет)",
    },
]

# Наказание за попытку отключить госрекламу — на весь экран.
AD_PUNISH_CONTENT = {
    "bg": "#7a0000",
    "title": "🤡 КУДА СОБРАЛСЯ?",
    "body": "Госрекламу ОТКЛЮЧИТЬ НЕЛЬЗЯ.\n"
            "За попытку — лови на весь экран.\n"
            "Сиди и смотри, гражданин. 🇷🇺",
    "btn": "Виноват, исправлюсь",
}


def get_local_ban_path():
    """Файл-маркер локального «бана» (шуточный, ставится Tonkeeper-ом)."""
    return os.path.join(os.path.dirname(get_settings_path()), "eblan_local_ban.json")


def check_local_seed_ban():
    """Проверяет шуточный локальный бан. Если есть — показывает заглушку и выходит.

    Бан ставится после того, как пользователь «повёлся» и ввёл 24 слова в
    Tonkeeper 2. Сами слова НИКУДА не сохраняются и не отправляются — здесь
    хранится только факт бана и причина.
    """
    path = get_local_ban_path()
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            info = json.load(f)
    except Exception:
        info = {}
    reason = (info.get("reason") or "Ты повёлся на «не скам».").strip()
    try:
        QMessageBox.critical(
            None,
            "ПОШЁЛ НАХУЙ",
            "Ты забанен в EBLAN Browser 6.7, чмо.\n\n"
            f"Причина:\n{reason}\n\n"
            "Никогда. Не вводи. Свои 24 слова. Нигде.\n\n"
            f"Если совсем невмоготу — удали файл:\n{path}",
        )
    except Exception:
        print("[ban] локальный seed-бан активен:", reason)
    sys.exit(0)


# ============================================================
#   VLESS клиент (Xray-core outbound + SOCKS5 для Chromium).
#
#   Возможности:
#     - парсинг vless://... и подписок (в т.ч. base64)
#     - TCP-ping по (host:port)
#     - управление xray-core (start/stop) с генерацией конфига
#     - SOCKS5 на 127.0.0.1:10808 + HTTP-прокси на 10809
#     - применение прокси к QtWebEngine (через CHROMIUM_FLAGS до QApplication)
#     - применение прокси к Qt-запросам (QNetworkProxy.setApplicationProxy)
# ============================================================


@dataclass
class VlessServer:
    name: str = ""
    host: str = ""
    port: int = 443
    uuid: str = ""
    security: str = "none"       # tls | reality | none
    network: str = "tcp"         # tcp | ws | grpc
    sni: str = ""
    path: str = ""
    host_header: str = ""
    pbk: str = ""                # reality public key
    fp: str = ""                 # utls fingerprint
    sid: str = ""                # reality short id
    flow: str = ""               # xtls-rprx-vision, ...
    alpn: str = ""
    ping_ms: int = -1            # -1 = не измерено
    source_uri: str = ""

    def label(self):
        ping = f"{self.ping_ms} ms" if self.ping_ms >= 0 else "—"
        return f"[{ping}]  {self.name or self.host}"


def parse_vless_uri(uri: str) -> VlessServer:
    """Парсит vless://uuid@host:port?params#name."""
    uri = (uri or "").strip()
    if not uri.lower().startswith("vless://"):
        raise ValueError("не vless URI")
    body = uri[len("vless://"):]
    name = ""
    if "#" in body:
        body, frag = body.split("#", 1)
        try:
            name = urllib.parse.unquote(frag)
        except Exception:
            name = frag
    if "@" not in body:
        raise ValueError("отсутствует '@' в VLESS URI")
    userinfo, rest = body.split("@", 1)
    uuid = userinfo.strip()

    query = {}
    if "?" in rest:
        hostport, qs = rest.split("?", 1)
        try:
            for k, v in urllib.parse.parse_qsl(qs, keep_blank_values=True):
                query[k] = v
        except Exception:
            pass
    else:
        hostport = rest

    # host:port с поддержкой IPv6
    if hostport.startswith("["):
        end = hostport.find("]")
        host = hostport[1:end] if end > 0 else hostport.strip("[]")
        after = hostport[end + 1:]
        port = 443
        if after.startswith(":"):
            try:
                port = int(after[1:])
            except Exception:
                port = 443
    elif ":" in hostport:
        host, port_s = hostport.rsplit(":", 1)
        try:
            port = int(port_s)
        except Exception:
            port = 443
    else:
        host, port = hostport, 443

    return VlessServer(
        name=name,
        host=host,
        port=port,
        uuid=uuid,
        security=query.get("security", "none"),
        network=query.get("type", "tcp"),
        sni=query.get("sni", ""),
        path=query.get("path", ""),
        host_header=query.get("host", ""),
        pbk=query.get("pbk", ""),
        fp=query.get("fp", ""),
        sid=query.get("sid", ""),
        flow=query.get("flow", ""),
        alpn=query.get("alpn", ""),
        source_uri=uri,
    )


def decode_subscription(text: str):
    """Парсит содержимое подписки. Поддерживает base64 и plain text со списком URI."""
    if not text:
        return []
    raw = text.strip()
    # попытка base64 (обычный и urlsafe, с добором паддинга)
    candidate = raw.replace("\n", "").replace("\r", "").replace(" ", "")
    if candidate and "vless://" not in raw:
        for decoder in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                padded = candidate + "=" * (-len(candidate) % 4)
                decoded = decoder(padded).decode("utf-8", errors="replace")
                if "vless://" in decoded:
                    raw = decoded
                    break
            except Exception:
                continue

    servers = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.lower().startswith("vless://"):
            continue
        try:
            servers.append(parse_vless_uri(line))
        except Exception as e:
            print(f"[vless] пропускаем строку: {e}")
    return servers


class XrayManager:
    """Обёртка над процессом xray-core."""

    def __init__(self, xray_bin="", socks_port=10808, http_port=10809):
        self.xray_bin = xray_bin or self.detect_binary()
        self.socks_port = int(socks_port)
        self.http_port = int(http_port)
        self.process = None
        self.config_path = None
        self.status = "stopped"
        self.last_error = ""

    @staticmethod
    def detect_binary():
        for name in ("xray", "xray.exe"):
            p = shutil.which(name)
            if p:
                return p
        return ""

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def build_config(self, srv: VlessServer):
        user = {"id": srv.uuid, "encryption": "none"}
        if srv.flow:
            user["flow"] = srv.flow
        outbound = {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": srv.host,
                    "port": srv.port,
                    "users": [user],
                }]
            },
            "streamSettings": {
                "network": srv.network or "tcp",
                "security": srv.security or "none",
            },
        }
        ss = outbound["streamSettings"]
        if srv.security == "tls":
            tls = {
                "serverName": srv.sni or srv.host,
                "allowInsecure": False,
            }
            if srv.fp:
                tls["fingerprint"] = srv.fp
            if srv.alpn:
                tls["alpn"] = [a for a in srv.alpn.split(",") if a]
            ss["tlsSettings"] = tls
        elif srv.security == "reality":
            reality = {
                "serverName": srv.sni or srv.host,
                "publicKey": srv.pbk,
                "shortId": srv.sid,
            }
            if srv.fp:
                reality["fingerprint"] = srv.fp
            ss["realitySettings"] = reality
        if srv.network == "ws":
            ws = {"path": srv.path or "/"}
            if srv.host_header:
                ws["headers"] = {"Host": srv.host_header}
            ss["wsSettings"] = ws
        elif srv.network == "grpc":
            ss["grpcSettings"] = {"serviceName": srv.path or ""}

        return {
            "log": {"loglevel": "warning"},
            "inbounds": [
                {
                    "tag": "socks-in",
                    "port": self.socks_port,
                    "listen": "127.0.0.1",
                    "protocol": "socks",
                    "settings": {"auth": "noauth", "udp": True},
                },
                {
                    "tag": "http-in",
                    "port": self.http_port,
                    "listen": "127.0.0.1",
                    "protocol": "http",
                },
            ],
            "outbounds": [
                outbound,
                {"protocol": "freedom", "tag": "direct"},
                {"protocol": "blackhole", "tag": "block"},
            ],
        }

    def start(self, srv: VlessServer):
        self.stop()
        if not self.xray_bin or not os.path.isfile(self.xray_bin):
            self.status = "error"
            self.last_error = "Xray не найден. Укажи путь к xray(.exe) в настройках."
            return False
        try:
            cfg = self.build_config(srv)
            fd, path = tempfile.mkstemp(suffix=".json", prefix="eblan-xray-")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            self.config_path = path
            creationflags = 0
            if os.name == "nt":
                creationflags = 0x08000000  # CREATE_NO_WINDOW
            self.process = subprocess.Popen(
                [self.xray_bin, "run", "-c", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags if os.name == "nt" else 0,
            )
            time.sleep(0.4)
            if not self.is_running():
                self.status = "error"
                self.last_error = "процесс xray упал на старте"
                return False
            self.status = "running"
            self.last_error = ""
            return True
        except Exception as e:
            self.status = "error"
            self.last_error = str(e)
            return False

    def stop(self):
        if self.process is not None:
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except Exception:
                    self.process.kill()
            except Exception:
                pass
            self.process = None
        if self.config_path and os.path.exists(self.config_path):
            try:
                os.remove(self.config_path)
            except Exception:
                pass
            self.config_path = None
        self.status = "stopped"


class VlessPinger(QObject):
    """TCP-ping серверов в фон��во�� потоке."""
    serverPinged = pyqtSignal(int, int)   # index, ms (-1 при ошибке)
    allDone = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel = threading.Event()
        self._thread = None

    def cancel(self):
        self._cancel.set()

    def ping_all(self, servers):
        self.cancel()
        self._cancel = threading.Event()
        servers_snapshot = list(servers)

        def worker():
            for idx, srv in enumerate(servers_snapshot):
                if self._cancel.is_set():
                    break
                ms = self._ping_one(srv.host, srv.port, timeout=2.5)
                try:
                    self.serverPinged.emit(idx, ms)
                except Exception:
                    pass
            try:
                self.allDone.emit()
            except Exception:
                pass

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    @staticmethod
    def _ping_one(host, port, timeout=2.5):
        try:
            start = time.time()
            with socket.create_connection((host, port), timeout=timeout):
                pass
            return int((time.time() - start) * 1000)
        except Exception:
            return -1


def _vless_state_path():
    return os.path.join(os.path.dirname(get_settings_path()), "vless_state.json")


# Глобалы для bootstrap (будут заполнены до создания QApplication).
_BOOT_VLESS_MANAGER = None
_BOOT_VLESS_SERVER = None


def _vless_bootstrap():
    """Читает vless_state.json до создания QApplication.
    Если VLESS был активен — стартует xray и подсовывает прокси в Chromium через env."""
    global _BOOT_VLESS_MANAGER, _BOOT_VLESS_SERVER
    try:
        path = _vless_state_path()
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        if not state.get("active"):
            return
        srv_data = state.get("server") or {}
        if not isinstance(srv_data, dict):
            return
        allowed = set(VlessServer.__dataclass_fields__.keys())
        srv = VlessServer(**{k: v for k, v in srv_data.items() if k in allowed})
        if not srv.host or not srv.uuid:
            return
        mgr = XrayManager(
            xray_bin=state.get("xray_bin", "") or "",
            socks_port=int(state.get("socks_port", 10808) or 10808),
            http_port=int(state.get("http_port", 10809) or 10809),
        )
        if not mgr.start(srv):
            print(f"[vless] bootstrap: не удалось запустить xray: {mgr.last_error}")
            return

        # Chromium пускаем через HTTP-прокси xray — в HTTP proxy DNS резолвится
        # на стороне прокси, без DNS-утечки и без TLS-резетов от провайдера
        # (симптом: ssl_client_socket ... net_error -101).
        # SOCKS5 остаётся для остальных Qt-запросов (QNetworkProxy).
        flags_list = [
            f'--proxy-server="http://127.0.0.1:{mgr.http_port}"',
            # никакого прокси для localhost/127.0.0.1
            '--proxy-bypass-list="<-loopback>"',
            # страховка от DNS-leak: любой локальный резолв проваливается,
            # Chromium передаёт hostname прямо прокси-серверу
            '--host-resolver-rules="MAP * ~NOTFOUND , EXCLUDE localhost"',
        ]
        current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        for extra in flags_list:
            key = extra.split("=", 1)[0]
            if key not in current:
                current = (current + " " + extra).strip()
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = current
        _BOOT_VLESS_MANAGER = mgr
        _BOOT_VLESS_SERVER = srv
        print(f"[vless] bootstrap OK: {srv.name or srv.host} "
              f"(Chromium → HTTP :{mgr.http_port}, Qt → SOCKS5 :{mgr.socks_port})")
    except Exception as e:
        print(f"[vless] bootstrap error: {e}")


class VlessController(QObject):
    """Высо��оуровневый менеджер VLESS: подписки + серверы + xray."""
    statusChanged = pyqtSignal()
    serversUpdated = pyqtSignal()
    pingProgress = pyqtSignal(int, int)  # idx, ms

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.subscriptions = []
        self.servers = []
        self.active_server_idx = -1
        self.xray_manager = XrayManager()
        self.pinger = VlessPinger(self)
        self.pinger.serverPinged.connect(self._on_pinged)

        # если xray был уже запущен в bootstrap — забираем его себе
        global _BOOT_VLESS_MANAGER, _BOOT_VLESS_SERVER
        if _BOOT_VLESS_MANAGER is not None:
            self.xray_manager = _BOOT_VLESS_MANAGER
            if _BOOT_VLESS_SERVER is not None:
                # если сервера такого в списке нет — добавим
                self.servers.append(_BOOT_VLESS_SERVER)
                self.active_server_idx = len(self.servers) - 1
            _BOOT_VLESS_MANAGER = None
            _BOOT_VLESS_SERVER = None

    # ---- state ----
    def status_text(self):
        if self.xray_manager.is_running() and 0 <= self.active_server_idx < len(self.servers):
            s = self.servers[self.active_server_idx]
            return f"Подключено: {s.name or s.host}:{s.port}"
        if self.xray_manager.status == "error":
            return f"Ошибка: {self.xray_manager.last_error}"
        return "Не подключено"

    def is_connected(self):
        return self.xray_manager.is_running()

    # ---- subscriptions ----
    def add_subscription(self, url):
        url = (url or "").strip()
        if url and url not in self.subscriptions:
            self.subscriptions.append(url)

    def remove_subscription(self, url):
        self.subscriptions = [u for u in self.subscriptions if u != url]

    def refresh_subscriptions(self, on_done=None):
        """Асинхронно тянет все подписки и заменяет список серверов."""
        subs = list(self.subscriptions)

        def work():
            all_servers = []
            errors = []
            for url in subs:
                try:
                    r = requests.get(url, timeout=10,
                                     headers={"User-Agent": "EblanBrowser/VLESS"})
                    if r.status_code >= 400:
                        errors.append(f"{url}: HTTP {r.status_code}")
                        continue
                    for s in decode_subscription(r.text):
                        all_servers.append(s)
                except Exception as e:
                    errors.append(f"{url}: {e}")
            # сохраняем пинг если сервер уже был
            old_by_key = {(s.host, s.port, s.uuid): s.ping_ms for s in self.servers}
            for s in all_servers:
                s.ping_ms = old_by_key.get((s.host, s.port, s.uuid), -1)
            self.servers = all_servers
            try:
                self.serversUpdated.emit()
            except Exception:
                pass
            if on_done:
                QTimer.singleShot(0, lambda: on_done(len(all_servers), errors))

        threading.Thread(target=work, daemon=True).start()

    # ---- ping ----
    def ping_all(self):
        self.pinger.ping_all(self.servers)

    def _on_pinged(self, idx, ms):
        if 0 <= idx < len(self.servers):
            self.servers[idx].ping_ms = ms
            self.pingProgress.emit(idx, ms)

    # ---- connect ----
    def connect_to(self, idx):
        if not (0 <= idx < len(self.servers)):
            return False, "неверный индекс"
        srv = self.servers[idx]
        if not self.xray_manager.xray_bin:
            self.xray_manager.xray_bin = XrayManager.detect_binary()
        ok = self.xray_manager.start(srv)
        if ok:
            self.active_server_idx = idx
            self._apply_qt_proxy(True)
            self._persist_state(active=True, srv=srv)
            self.statusChanged.emit()
            return True, "подключено"
        self.statusChanged.emit()
        return False, self.xray_manager.last_error or "xray не запустился"

    def disconnect(self):
        self.xray_manager.stop()
        self.active_server_idx = -1
        self._apply_qt_proxy(False)
        self._persist_state(active=False, srv=None)
        self.statusChanged.emit()

    # ---- helpers ----
    def _apply_qt_proxy(self, enabled):
        """Прокси для Qt-запросов (апдейты, AI и т.п.). Chromium идёт через CHROMIUM_FLAGS."""
        try:
            if enabled:
                p = QNetworkProxy(QNetworkProxy.ProxyType.Socks5Proxy,
                                  "127.0.0.1", self.xray_manager.socks_port)
                QNetworkProxy.setApplicationProxy(p)
            else:
                QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        except Exception as e:
            print(f"[vless] setApplicationProxy: {e}")

    def _persist_state(self, active, srv):
        try:
            state = {
                "active": bool(active),
                "server": asdict(srv) if srv is not None else None,
                "xray_bin": self.xray_manager.xray_bin,
                "socks_port": self.xray_manager.socks_port,
                "http_port": self.xray_manager.http_port,
            }
            os.makedirs(os.path.dirname(_vless_state_path()), exist_ok=True)
            with open(_vless_state_path(), "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[vless] persist: {e}")

    # ---- (de)serialization for settings.json ----
    def load_from_settings(self, data):
        self.subscriptions = list(data.get("vless_subscriptions", []) or [])
        bin_path = data.get("vless_xray_bin", "") or ""
        if bin_path:
            self.xray_manager.xray_bin = bin_path
        try:
            self.xray_manager.socks_port = int(data.get("vless_socks_port", 10808) or 10808)
            self.xray_manager.http_port = int(data.get("vless_http_port", 10809) or 10809)
        except Exception:
            pass
        cached = data.get("vless_servers_cache", []) or []
        allowed = set(VlessServer.__dataclass_fields__.keys())
        # не затираем только что добавленный из bootstrap сервер
        if not self.servers:
            self.servers = [
                VlessServer(**{k: v for k, v in s.items() if k in allowed})
                for s in cached if isinstance(s, dict)
            ]

    def dump_to_settings(self):
        return {
            "vless_subscriptions": list(self.subscriptions),
            "vless_xray_bin": self.xray_manager.xray_bin,
            "vless_socks_port": self.xray_manager.socks_port,
            "vless_http_port": self.xray_manager.http_port,
            "vless_servers_cache": [asdict(s) for s in self.servers],
        }





def load_settings():
    path = get_settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ============================================================
#   Бан по железу (hardware ban) и анонимный режим.
#
#   - get_hardware_id() — стабильный SHA256-отпечаток машины
#   - get_profile_name() — имя профиля юзера ОС
#   - _ban_url() — собирает URL бэкенда с учётом index.php / mod_rewrite
#   - check_ban_at_startup() — проверка бана (синхронная, до запуска)
#   - ban_heartbeat_async() — фоновая регистрация юзера
#   - ban_admin_request() — обёртка для админ-запросов из интерфейса
# ============================================================

INCOGNITO_HOMEPAGE = "https://murena.qwant.com"

DEFAULT_BAN_API_BASE = "https://update.riba.click/eb/upd/public/index.php"

# Браузероподобные заголовки для запросов к бэкенду.
# serv00/nginx часто отдаёт 403 на дефолтный User-Agent "python-requests/*"
# (как раз голая страница "403 Forbidden / nginx") — поэтому представляемся
# нормальным клиентом.
EB_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) EBLANBrowser/1.0 Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru,en;q=0.9",
}


def _api_to_indexphp(url: str):
    """Преобразует .../api/<route>[?qs] → .../index.php?route=<route>[&qs].

    Нужно для серверов без mod_rewrite (nginx, где .htaccess попросту
    игнорируется): красивого пути /api/<route> там не существует, и сервер
    отдаёт сырой 403. Прямая точка входа index.php работает всегда.
    Возвращает None, если URL не в форме /api/<route>."""
    import re as _re
    m = _re.match(r"^(.*?)/api/([a-zA-Z_-]+)/?(?:\?(.*))?$", url or "")
    if not m:
        return None
    base, route, qs = m.group(1), m.group(2), m.group(3)
    alt = f"{base}/index.php?route={route}"
    if qs:
        alt += "&" + qs
    return alt


def eb_api_request(url, data=None, timeout=10):
    """Запрос к бэкенду: сначала POST, а если сервер (serv00/nginx) режет
    POST и отдаёт 403 — автоматический фолбэк на GET с теми же параметрами.
    Бэкенд читает параметры и из $_GET, и из $_POST, поэтому GET работает.

    Если 403 не уходит и URL в форме /api/<route> — значит на сервере нет
    mod_rewrite/.htaccess (типичный nginx). Тогда пробуем прямую точку входа
    index.php?route=<route>. Исключения пробрасываются вызывающему коду."""
    data = data or {}
    r = requests.post(url, data=data, headers=EB_HTTP_HEADERS, timeout=timeout)
    if r.status_code == 403:
        try:
            eb_debug("net", f"POST {url} → 403, фолбэк на GET")
        except Exception:
            pass
        r = requests.get(url, params=data, headers=EB_HTTP_HEADERS, timeout=timeout)
    if r.status_code == 403:
        alt = _api_to_indexphp(url)
        if alt:
            try:
                eb_debug("net", f"{url} → 403 (нет mod_rewrite), фолбэк на {alt}")
            except Exception:
                pass
            r = requests.post(alt, data=data, headers=EB_HTTP_HEADERS, timeout=timeout)
            if r.status_code == 403:
                r = requests.get(alt, params=data, headers=EB_HTTP_HEADERS, timeout=timeout)
    return r


def _hw_subprocess_flags():
    """Флаги, чтобы на Windows не мигало окно консоли."""
    flags = 0
    si = None
    if sys.platform.startswith("win"):
        flags = 0x08000000  # CREATE_NO_WINDOW
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        except Exception:
            si = None
    return flags, si


def _hw_run(cmd, timeout=6) -> str:
    """Тихо выполнить команду, вернуть stdout (str) или ''. Никогда не падает."""
    try:
        flags, si = _hw_subprocess_flags()
        out = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            creationflags=flags, startupinfo=si,
        )
        data = out.stdout or b""
        return data.decode("utf-8", errors="ignore") if isinstance(data, bytes) else str(data)
    except Exception:
        return ""


def _hw_norm(value: str) -> str:
    """Нормализуем серийник: только A-Z0-9 в верхнем регистре.
    Отсекаем заведомо мусорные значения от прошивок/VM."""
    if not value:
        return ""
    import re as _re
    s = _re.sub(r"[^A-Za-z0-9]", "", value).upper()
    bad = {
        "0", "00000000", "0000000000", "NONE", "NA", "NULL", "UNKNOWN",
        "NOTSPECIFIED", "TOBEFILLEDBYOEM", "TOBEFILLEDBYOEMTOBEFILLEDBYOEM",
        "DEFAULTSTRING", "SYSTEMSERIALNUMBER", "FFFFFFFFFFFFFFFF",
        "00000000000000000000000000000000",
    }
    if not s or s in bad or len(s) < 3 or set(s) == {"0"} or set(s) == {"F"}:
        return ""
    return s


def _hw_disk_serials() -> list:
    """Серийники физических дисков. Читаются без root и в Win, и в Linux,
    поэтому это лучший кросс-ОС якорь для дуалбута."""
    serials = []
    plat = sys.platform
    try:
        if plat.startswith("win"):
            out = _hw_run([
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "Get-CimInstance Win32_DiskDrive | "
                "Where-Object { $_.MediaType -notmatch 'Removable' } | "
                "ForEach-Object { $_.SerialNumber }",
            ])
            if not out.strip():
                out = _hw_run(["wmic", "diskdrive", "get", "serialnumber"])
            for line in out.splitlines():
                line = line.strip()
                if not line or line.lower() == "serialnumber":
                    continue
                n = _hw_norm(line)
                if n:
                    serials.append(n)
        elif plat == "darwin":
            out = _hw_run(["system_profiler", "SPNVMeDataType", "SPSerialATADataType"])
            for line in out.splitlines():
                if "Serial Number" in line:
                    n = _hw_norm(line.split(":", 1)[-1])
                    if n:
                        serials.append(n)
        else:  # Linux
            out = _hw_run(["lsblk", "-dno", "TYPE,SERIAL"])
            for line in out.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[0] == "disk":
                    n = _hw_norm(parts[1])
                    if n:
                        serials.append(n)
            if not serials:
                import glob as _glob
                for dev in sorted(_glob.glob("/sys/block/*")):
                    name = os.path.basename(dev)
                    if name.startswith(("loop", "ram", "sr", "dm-", "zram", "md", "fd")):
                        continue
                    for sub in ("device/serial", "serial", "device/wwid", "wwid"):
                        p = os.path.join(dev, sub)
                        try:
                            if os.path.exists(p):
                                with open(p, "r", errors="ignore") as f:
                                    n = _hw_norm(f.read())
                                if n:
                                    serials.append(n)
                                    break
                        except Exception:
                            continue
    except Exception:
        pass
    # Уникализируем и сортируем — порядок/набор дисков не должен влиять.
    return sorted(set(serials))


def _hw_bios_uuid() -> str:
    """SMBIOS/BIOS UUID. На Linux обычно требует root (тогда вернёт '')."""
    plat = sys.platform
    try:
        if plat.startswith("win"):
            out = _hw_run([
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
            ])
            if not out.strip():
                out = _hw_run(["wmic", "csproduct", "get", "uuid"])
            for line in out.splitlines():
                line = line.strip()
                if line and line.lower() != "uuid":
                    n = _hw_norm(line)
                    if n:
                        return n
        elif plat == "darwin":
            out = _hw_run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return _hw_norm(line.split("=")[-1])
        else:
            try:
                with open("/sys/class/dmi/id/product_uuid", "r", errors="ignore") as f:
                    n = _hw_norm(f.read())
                if n:
                    return n
            except Exception:
                pass
            out = _hw_run(["dmidecode", "-s", "system-uuid"])
            if out.strip():
                return _hw_norm(out)
    except Exception:
        pass
    return ""


def _hw_board_serial() -> str:
    """Серийник материнской платы. На Linux обычно root-only."""
    plat = sys.platform
    try:
        if plat.startswith("win"):
            out = _hw_run([
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                "(Get-CimInstance Win32_BaseBoard).SerialNumber",
            ])
            if not out.strip():
                out = _hw_run(["wmic", "baseboard", "get", "serialnumber"])
            for line in out.splitlines():
                line = line.strip()
                if line and line.lower() != "serialnumber":
                    n = _hw_norm(line)
                    if n:
                        return n
        elif plat != "darwin":
            for p in ("/sys/class/dmi/id/board_serial", "/sys/class/dmi/id/product_serial"):
                try:
                    with open(p, "r", errors="ignore") as f:
                        n = _hw_norm(f.read())
                    if n:
                        return n
                except Exception:
                    pass
    except Exception:
        pass
    return ""


def _hw_cpu_signature() -> str:
    """
    Кросс-ОС сигнатура CPU без root: CPUID brand-string + число потоков.

    ВАЖНО: это НЕ уникальный серийник — у одинаковых моделей CPU она совпадёт.
    Используется только как доп-сигнал в fallback. Реально уникальные ID
    (Intel PPIN / TPM EK) требуют root/админ и здесь намеренно не трогаются.

    Берём именно CPUID brand-string (а не platform.processor()), т.к. он
    одинаков в Windows (реестр ProcessorNameString) и Linux (/proc/cpuinfo).
    """
    brand = ""
    plat = sys.platform
    try:
        if plat.startswith("win"):
            out = _hw_run([
                "reg", "query",
                r"HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                "/v", "ProcessorNameString",
            ])
            for line in out.splitlines():
                if "ProcessorNameString" in line and "REG_SZ" in line:
                    brand = line.split("REG_SZ", 1)[1].strip()
                    break
        elif plat == "darwin":
            brand = _hw_run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
        else:
            try:
                with open("/proc/cpuinfo", "r", errors="ignore") as f:
                    for line in f:
                        if line.lower().startswith("model name"):
                            brand = line.split(":", 1)[1].strip()
                            break
            except Exception:
                pass
    except Exception:
        pass
    try:
        cores = os.cpu_count() or 0
    except Exception:
        cores = 0
    if not brand:
        return ""
    return _hw_norm("{}|{}".format(brand, cores))


def _hw_persistent_id() -> str:
    """Последний рубеж: стабильный seed в файле ~/.eblan/hwid_seed.
    Не кросс-ОС, но стабилен в пределах одной установки."""
    try:
        base = os.path.join(os.path.expanduser("~"), ".eblan")
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, "hwid_seed")
        seed = ""
        if os.path.exists(path):
            with open(path, "r", errors="ignore") as f:
                seed = f.read().strip()
        if not seed:
            import uuid as _uuid
            seed = _uuid.uuid4().hex
            try:
                with open(path, "w") as f:
                    f.write(seed)
            except Exception:
                pass
        return seed
    except Exception:
        return ""


def get_hardware_id() -> str:
    """
    Аппаратный HWID — привязан к ЖЕЛЕЗУ, а НЕ к имени машины или ОС.

    Источник (по приоритету):
      1. Серийники физических дисков — читаются без root и в Windows,
         и в Linux, поэтому HWID одинаков при дуалбуте Win/Linux.
      2. UUID материнки/BIOS (если доступен).
      3. Серийник материнской платы.
      4. Стабильный сохранённый seed (последний резерв).

    Принципиально НЕ используем hostname и имя ОС — иначе бан обходится
    переименованием машины или загрузкой в другую ОС. Работает локально,
    ничего никуда не отправляет.
    """
    try:
        import hashlib as _hashlib

        disks = _hw_disk_serials()
        if disks:
            anchor = "disk:" + ",".join(disks)
        else:
            # Нет серийников дисков — собираем всё доступное железо.
            parts = []
            uuid_ = _hw_bios_uuid()
            if uuid_:
                parts.append("uuid:" + uuid_)
            board = _hw_board_serial()
            if board:
                parts.append("board:" + board)
            cpu = _hw_cpu_signature()
            if cpu:
                parts.append("cpu:" + cpu)
            if parts:
                anchor = "|".join(sorted(parts))
            else:
                seed = _hw_persistent_id()
                anchor = "seed:" + (seed or "unknown")

        digest = _hashlib.sha256(anchor.encode("utf-8", errors="ignore")).hexdigest()
        return "hw_" + digest[:32]
    except Exception:
        # На всякий случай — не падаем, возвращаем стабильно "unknown".
        return "unknown-hwid"


# ============================================================
#  РЕАЛЬНЫЙ IP (в обход VPN/прокси)
# ============================================================

def _is_ip(s: str) -> bool:
    try:
        socket.inet_aton(s)
        return True
    except Exception:
        try:
            socket.inet_pton(socket.AF_INET6, s)
            return True
        except Exception:
            return False


def _local_ips() -> list:
    """Локальные адреса интерфейсов (для фингерпринта)."""
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ips.add(info[4][0])
    except Exception:
        pass
    for target in (("8.8.8.8", 80), ("1.1.1.1", 80)):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1.5)
            s.connect(target)
            ips.add(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return sorted(i for i in ips if i and not i.startswith("127.") and i != "::1")


def _public_ip_direct(timeout=4) -> str:
    """Публичный IP прямым HTTP-запросом в обход прокси приложения
    (trust_env=False игнорирует системные HTTP(S)_PROXY)."""
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
        "https://ipinfo.io/ip",
    ]
    try:
        sess = requests.Session()
        sess.trust_env = False
        for url in services:
            try:
                r = sess.get(url, timeout=timeout, proxies={"http": None, "https": None})
                ip = (r.text or "").strip()
                if _is_ip(ip):
                    return ip
            except Exception:
                continue
    except Exception:
        pass
    return ""


def _parse_stun(data, magic, tx) -> str:
    import struct as _struct
    try:
        if len(data) < 20:
            return ""
        msg_type, msg_len = _struct.unpack(">HH", data[:4])
        if msg_type != 0x0101:  # Binding Success Response
            return ""
        pos, end = 20, 20 + msg_len
        while pos + 4 <= end:
            attr_type, attr_len = _struct.unpack(">HH", data[pos:pos + 4])
            val = data[pos + 4:pos + 4 + attr_len]
            pos += 4 + attr_len + ((4 - attr_len % 4) % 4)  # padding до 4 байт
            if attr_type in (0x0020, 0x0001) and len(val) >= 8:  # (XOR-)MAPPED-ADDRESS
                family = val[1]
                if family == 0x01:  # IPv4
                    raw = val[4:8]
                    if attr_type == 0x0020:  # XOR-MAPPED — расшифровываем
                        ipnum = _struct.unpack(">I", raw)[0] ^ magic
                        raw = _struct.pack(">I", ipnum)
                    return socket.inet_ntoa(raw)
        return ""
    except Exception:
        return ""


def _public_ip_stun(timeout=3) -> str:
    """Публичный IP через STUN (UDP). Часто «утекает» мимо HTTP/SOCKS-прокси
    приложения и некоторых VPN — это и есть реальный адрес."""
    import struct as _struct
    servers = [
        ("stun.l.google.com", 19302),
        ("stun1.l.google.com", 19302),
        ("stun.cloudflare.com", 3478),
    ]
    magic = 0x2112A442
    for host, port in servers:
        try:
            tx = os.urandom(12)
            header = _struct.pack(">HHI", 0x0001, 0, magic) + tx
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            s.sendto(header, (host, port))
            data, _ = s.recvfrom(2048)
            s.close()
            ip = _parse_stun(data, magic, tx)
            if ip and _is_ip(ip):
                return ip
        except Exception:
            continue
    return ""


def get_real_ip(timeout=4) -> dict:
    """
    Вычисляет РЕАЛЬНЫЙ внешний IP в обход VPN/прокси приложения.

    Стратегия:
      - STUN (UDP) — чаще всего обходит HTTP/SOCKS-прокси и протекает мимо VPN;
      - прямой HTTP в обход прокси (trust_env=False);
      - локальные адреса интерфейсов.

    Если STUN и HTTP дали разные адреса — выставляется флаг leak (значит,
    трафик где-то заворачивается через прокси/VPN). Никогда не падает.
    """
    result = {"stun_ip": "", "direct_ip": "", "local_ips": [], "real_ip": "", "leak": False}
    try:
        result["local_ips"] = _local_ips()
        result["stun_ip"] = _public_ip_stun(timeout=min(timeout, 3))
        result["direct_ip"] = _public_ip_direct(timeout=timeout)
        stun, direct = result["stun_ip"], result["direct_ip"]
        # «Реальный» = STUN (он чаще обходит прокси), иначе — прямой HTTP.
        result["real_ip"] = stun or direct
        if stun and direct and stun != direct:
            result["leak"] = True
    except Exception:
        pass
    return result


# ============================================================
#  ПОЛНЫЙ HARDWARE-ОТПЕЧАТОК (для нечёткого совпадения на сервере)
# ============================================================
#
#  Собираем КАЖДЫЙ компонент отдельным полем. Один общий HWID остаётся
#  стабильным (диски/матплата → дуалбут не ломается), а этот набор сервер
#  использует для fuzzy-match: машина = «та же», если совпало ≥N компонентов.
#  Поэтому смена hostname/одной железки бан не снимает.

def _hw_is_hexmac(s: str) -> bool:
    return len(s) == 12 and all(c in "0123456789ABCDEF" for c in s) and s != "000000000000"


def _hw_macs() -> list:
    """MAC-адреса физических сетевых адаптеров (виртуальные пропускаем)."""
    macs = set()
    plat = sys.platform
    try:
        if plat.startswith("win"):
            out = _hw_run(["getmac", "/v", "/fo", "csv", "/nh"])
            for line in out.splitlines():
                for tok in line.replace('"', " ").replace(",", " ").split():
                    n = _hw_norm(tok)
                    if _hw_is_hexmac(n):
                        macs.add(n)
            if not macs:
                out = _hw_run(["wmic", "nic", "where", "PhysicalAdapter=true", "get", "MACAddress"])
                for line in out.splitlines():
                    n = _hw_norm(line)
                    if _hw_is_hexmac(n):
                        macs.add(n)
        else:
            import glob as _glob
            virt = ("veth", "docker", "virbr", "br-", "vmnet", "vboxnet",
                    "tun", "tap", "wg", "zt", "bond", "dummy")
            for net in sorted(_glob.glob("/sys/class/net/*")):
                name = os.path.basename(net)
                if name == "lo" or name.startswith(virt):
                    continue
                if not os.path.exists(os.path.join(net, "device")):
                    continue  # нет железного устройства → виртуальный
                try:
                    with open(os.path.join(net, "address"), "r", errors="ignore") as f:
                        n = _hw_norm(f.read())
                    if _hw_is_hexmac(n):
                        macs.add(n)
                except Exception:
                    continue
    except Exception:
        pass
    return sorted(macs)


def _hw_machine_guid() -> str:
    """Machine GUID (Windows) / machine-id (Linux). Привязан к установке ОС."""
    plat = sys.platform
    try:
        if plat.startswith("win"):
            out = _hw_run(["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography",
                           "/v", "MachineGuid"])
            for line in out.splitlines():
                if "MachineGuid" in line and "REG_SZ" in line:
                    return _hw_norm(line.split("REG_SZ", 1)[1])
        else:
            for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                try:
                    with open(p, "r", errors="ignore") as f:
                        n = _hw_norm(f.read())
                    if n:
                        return n
                except Exception:
                    continue
    except Exception:
        pass
    return ""


def _hw_volume_serial() -> str:
    """Серийник тома C: (Windows) / UUID корневой ФС (Linux)."""
    plat = sys.platform
    try:
        if plat.startswith("win"):
            out = _hw_run(["cmd", "/c", "vol", "C:"])
            import re as _re
            m = _re.search(r"([0-9A-Fa-f]{4})[-\s]?([0-9A-Fa-f]{4})", out)
            if m:
                return _hw_norm(m.group(1) + m.group(2))
        else:
            out = _hw_run(["findmnt", "-n", "-o", "UUID", "/"])
            n = _hw_norm(out)
            if n:
                return n
    except Exception:
        pass
    return ""


def _hw_cpu_id() -> str:
    """CPU ProcessorId (Windows) — полу-уникален. На Linux недоступен штатно."""
    try:
        if sys.platform.startswith("win"):
            out = _hw_run(["wmic", "cpu", "get", "ProcessorId"])
            for line in out.splitlines():
                line = line.strip()
                if line and line.lower() != "processorid":
                    n = _hw_norm(line)
                    if n:
                        return n
    except Exception:
        pass
    return ""


def _hw_ram_serials() -> list:
    """Серийники планок RAM (Windows wmic). На Linux обычно root-only → пусто."""
    res = set()
    try:
        if sys.platform.startswith("win"):
            out = _hw_run(["wmic", "memorychip", "get", "SerialNumber"])
            for line in out.splitlines():
                line = line.strip()
                if line and line.lower() != "serialnumber":
                    n = _hw_norm(line)
                    if n:
                        res.add(n)
    except Exception:
        pass
    return sorted(res)


def _hw_gpus() -> list:
    """Названия видеокарт (описательно, НЕ уникально — для админки)."""
    res = []
    plat = sys.platform
    try:
        if plat.startswith("win"):
            out = _hw_run(["wmic", "path", "win32_VideoController", "get", "Name"])
            for line in out.splitlines():
                line = line.strip()
                if line and line.lower() != "name":
                    res.append(line)
        else:
            out = _hw_run(["sh", "-c", "lspci 2>/dev/null | grep -iE 'vga|3d|display'"])
            for line in out.splitlines():
                line = line.strip()
                if line:
                    res.append(line.split(": ", 1)[-1] if ": " in line else line)
    except Exception:
        pass
    seen = []
    for r in res:
        if r and r not in seen:
            seen.append(r)
    return seen[:4]


def _hw_monitors() -> list:
    """Хэши EDID мониторов (Linux без root). Меняются при смене монитора."""
    res = set()
    try:
        if not sys.platform.startswith("win"):
            import glob as _glob, hashlib as _h
            for edid in _glob.glob("/sys/class/drm/*/edid"):
                try:
                    with open(edid, "rb") as f:
                        data = f.read()
                    if data and len(data) >= 128:
                        res.add(_h.sha256(data).hexdigest()[:16].upper())
                except Exception:
                    continue
    except Exception:
        pass
    return sorted(res)


def collect_hw_components() -> dict:
    """
    Полный набор аппаратных идентификаторов отдельными полями.
    Ничего не падает; недоступное просто пустое. Отправляется на сервер,
    который делает нечёткое совпадение (≥N компонентов = та же машина).
    """
    comp = {}
    def _safe(fn, default):
        try:
            return fn()
        except Exception:
            return default
    comp["board"]        = _safe(_hw_board_serial, "")     # серийник матплаты
    comp["bios_uuid"]    = _safe(_hw_bios_uuid, "")        # System/BIOS UUID
    comp["cpu_id"]       = _safe(_hw_cpu_id, "")           # ProcessorId (Win)
    comp["cpu_model"]    = _safe(_hw_cpu_signature, "")    # описательно
    comp["machine_guid"] = _safe(_hw_machine_guid, "")     # MachineGuid / machine-id
    comp["volume"]       = _safe(_hw_volume_serial, "")    # серийник тома / UUID ФС
    comp["disks"]        = _safe(_hw_disk_serials, [])     # серийники дисков
    comp["macs"]         = _safe(_hw_macs, [])             # MAC физических NIC
    comp["ram"]          = _safe(_hw_ram_serials, [])      # серийники RAM
    comp["monitors"]     = _safe(_hw_monitors, [])         # EDID мониторов
    comp["gpus"]         = _safe(_hw_gpus, [])             # описательно
    return comp


def get_profile_name() -> str:
    """Имя профиля = имя пользователя в ОС."""
    try:
        return os.getlogin()
    except Exception:
        try:
            import getpass
            return getpass.getuser()
        except Exception:
            return "Unknown"


def _ban_url(api_base: str, route: str) -> str:
    """Поддерживает оба формата API base: с .htaccess и с index.php."""
    base = (api_base or "").strip().rstrip("/")
    if not base:
        return ""
    if base.lower().endswith("index.php"):
        return f"{base}?route={route}"
    return f"{base}/api/{route}"


def check_ban_at_startup(api_base: str, hwid: str, components: dict = None) -> dict:
    """Возвращает dict с ключами banned/reason/profile или {} при ошибке.
    Если переданы компоненты железа — сервер сохранит их и сделает
    нечёткое совпадение (ловит обходчиков уже на первом запуске)."""
    url = _ban_url(api_base, "check_ban")
    if not url:
        return {}
    try:
        data = {"hwid": hwid}
        if components:
            try:
                data["components"] = json.dumps(components, ensure_ascii=False)
            except Exception:
                pass
        # POST, т.к. компоненты могут быть объёмными; сервер принимает и GET.
        eb_debug("ban", f"check_ban → {url} (hwid={hwid[:12]}…, компонентов={len(components or {})})")
        r = eb_api_request(url, data, timeout=6)
        eb_debug("ban", f"check_ban HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code == 200:
            text = r.text.strip()
            if not text:
                print("[ban] empty response from server")
                return {}
            result = r.json()
            if isinstance(result, dict):
                return result
        else:
            print(f"[ban] server returned {r.status_code}: {r.text[:200]}")
    except json.JSONDecodeError as e:
        print(f"[ban] bad JSON: {e}")
    except Exception as e:
        print(f"[ban] check failed: {e}")
    return {}


def ban_heartbeat_async(api_base: str, hwid: str, profile: str, components: dict = None):
    """В фоне регистрирует машину на сервере, чтобы админка её увидела."""
    url = _ban_url(api_base, "heartbeat")
    if not url:
        return

    def _go():
        try:
            data = {"hwid": hwid, "profile": profile}
            if components:
                try:
                    data["components"] = json.dumps(components, ensure_ascii=False)
                except Exception:
                    pass
            # Реальный IP (в обход VPN/прокси) — считаем в этом же фоне.
            try:
                info = get_real_ip()
                if info.get("real_ip"):
                    data["real_ip"] = info["real_ip"]
                if info.get("local_ips"):
                    data["local_ip"] = ",".join(info["local_ips"][:4])
                if info.get("leak"):
                    data["proxy_leak"] = "1"
            except Exception:
                pass
            eb_debug("ban", f"heartbeat → {url} (real_ip={data.get('real_ip','?')}, leak={data.get('proxy_leak','0')})")
            resp = eb_api_request(url, data, timeout=12)
            eb_debug("ban", f"heartbeat HTTP {resp.status_code}")
        except Exception as e:
            eb_debug("ban", f"heartbeat ошибка: {e}")

    threading.Thread(target=_go, daemon=True).start()


def ban_admin_request(api_base: str, route: str, password: str, **fields) -> dict:
    """Синхронный POST/GET-запрос к админ-эндпоинту бэкенда.
    Возвращает {ok: bool, ...}. Никогда не бросает исключений."""
    url = _ban_url(api_base, route)
    if not url:
        return {"ok": False, "error": "no_api_base"}
    payload = {"password": password}
    payload.update({k: ("" if v is None else str(v)) for k, v in fields.items()})
    try:
        # Список юзеров и пинг — обычным GET'ом, остальное — POST'ом.
        if route in ("bans", "ping"):
            r = requests.get(url, params=payload, headers=EB_HTTP_HEADERS, timeout=8)
        else:
            r = eb_api_request(url, payload, timeout=8)
        try:
            data = r.json()
        except Exception:
            data = {"ok": False, "error": f"bad_json_{r.status_code}"}
        if not isinstance(data, dict):
            return {"ok": False, "error": "bad_response"}
        return data
    except Exception as e:
        return {"ok": False, "error": f"net: {e}"}


# ============================================================
#   EBLAN ID аккаунт — низкоуровневые обёртки запросов.
#   Используются и AccountLoginDialog, и встроенной формой онбординга,
#   чтобы не дублировать логику auth_start/auth_complete и синхронизации
#   ключа. Все функции синхронные, никогда не бросают исключений.
# ============================================================
def eblan_auth_start(api_base: str, email: str, timeout: int = 10) -> dict:
    """Шаг 1: запросить код на email. Возвращает dict ответа сервера."""
    url = _ban_url(api_base, "auth_start")
    if not url:
        return {"ok": False, "error": "no_api_base"}
    try:
        r = eb_api_request(url, {"email": email}, timeout=timeout)
        if r.status_code in (200, 400):
            return r.json()
        return {"ok": False, "error": f"http_{r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def eblan_auth_complete(api_base: str, email: str, code: str, timeout: int = 10) -> dict:
    """Шаг 2: подтвердить код. Возвращает dict с token/account при успехе."""
    url = _ban_url(api_base, "auth_complete")
    if not url:
        return {"ok": False, "error": "no_api_base"}
    try:
        r = eb_api_request(url, {"email": email, "code": code}, timeout=timeout)
        if r.status_code in (200, 400, 401):
            return r.json()
        return {"ok": False, "error": f"http_{r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def eblan_fetch_key(api_base: str, token: str, timeout: int = 10) -> dict:
    """Скачать сохранённый EBLAN ID ключ аккаунта (для pull-синхронизации)."""
    url = _ban_url(api_base, "get_eblan_id_key")
    if not url:
        return {"ok": False, "error": "no_api_base"}
    try:
        r = eb_api_request(url, {"token": token}, timeout=timeout)
        return r.json() if r.status_code in (200, 401) else {"ok": False, "error": f"http_{r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def eblan_push_key(api_base: str, token: str, key: str, timeout: int = 10) -> dict:
    """Выгрузить EBLAN ID ключ на сервер (для push-синхронизации)."""
    url = _ban_url(api_base, "save_eblan_id_key")
    if not url:
        return {"ok": False, "error": "no_api_base"}
    try:
        r = eb_api_request(url, {"token": token, "key": key}, timeout=timeout)
        return r.json() if r.status_code in (200, 400, 401) else {"ok": False, "error": f"http_{r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}



    def __init__(self, is_beta=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_beta = is_beta
        self.setWindowTitle("О программе")
        self.setMinimumSize(500, 350)
        self.setStyleSheet("""
            AboutDialog {
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            }
            QLabel {
                color: white;
            }
            QTextEdit {
                background: #0f3460;
                color: #00d4ff;
                border: 1px solid #00d4ff;
                border-radius: 5px;
            }
            QPushButton {
                background: #00d4ff;
                color: #1a1a2e;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #00f0ff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Заголовок с логотипом (кликабельный)
        header_layout = QHBoxLayout()
        
        class ClickableLabel(QLabel):
            def mousePressEvent(self, ev):
                try:
                    self.clicked()
                except Exception:
                    pass

        logo = ClickableLabel()
        logo_pixmap = QPixmap(os.path.join('images', 'ma-icon-128.png'))
        logo.setPixmap(logo_pixmap.scaledToWidth(100, Qt.TransformationMode.SmoothTransformation))
        logo.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Информация рядом с логотипом
        info_widget = QVBoxLayout()
        title = QLabel("EBLAN BROWSER")
        title_font = title.font()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #00d4ff;")
        info_widget.addWidget(title)

        version_text = "6.7  (67)"
        version = QLabel(version_text)
        version_font = version.font()
        version_font.setPointSize(12)
        version.setFont(version_font)
        version.setStyleSheet("color: #888;")
        info_widget.addWidget(version)

        info_widget.addWidget(QLabel("Лучший в мире браузер 67 с защитой и геймерским режимом!"))

        header_layout.addLayout(info_widget)
        layout.addLayout(header_layout)

        layout.addSpacing(10)

        # Описание
        desc = QLabel("Разработано @eblanbrowser\nпаверед бу пайтон и кьют6")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(desc)

        layout.addSpacing(15)

        # Статус разработки
        warning = QLabel("Данный браузер является эксперементом и может содержать баги.")
        warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning.setStyleSheet("color: #ff6b6b; font-weight: bold; padding: 10px; background: rgba(255,0,0,0.1); border-radius: 5px;")
        layout.addWidget(warning)

        layout.addSpacing(10)

        # Кнопка для System Info (neofetch style)
        def show_sysinfo():
            try:
                import platform
                node = platform.node()
                sysplat = platform.platform()
                arch = platform.machine()
                proc = platform.processor()
                pyver = platform.python_version()
                hwid = get_hardware_id()

                dlg = QDialog(self)
                dlg.setWindowTitle("HalalFetch")
                dlg.setMinimumSize(600, 400)
                dlg.setStyleSheet("""
                    QDialog { background: #000000; }
                    QLabel { color: white; }
                    QTextEdit { background: #000000; color: #00ff00; border: 1px solid #00ff00; font-family: 'Courier New', monospace; }
                    QPushButton { background: #00ff00; color: #000000; border: none; border-radius: 5px; padding: 8px 16px; font-weight: bold; }
                    QPushButton:hover { background: #00cc00; }
                """)
                v = QVBoxLayout(dlg)
                
                title_lbl = QLabel("Halalfetch (c) EBLAN Soft")
                title_lbl.setStyleSheet("color: #00ff00; font-weight: bold; font-size: 13px; font-family: 'Courier New', monospace;")
                v.addWidget(title_lbl)
                
                te = QTextEdit()
                te.setReadOnly(True)
                te.setStyleSheet("background: #000000; color: #00ff00; border: 2px solid #00ff00; font-family: 'Courier New', monospace;")
                
                # Neofetch-style output
                info_text = f"""
┌─────────────────────────────────────┐
│  EBLAN Browser System Information   │
└─────────────────────────────────────┘

Host:         {node}
OS:           {sysplat}
Arch:         {arch}
Processor:    {proc}
Python:       {pyver}
HWID:         {hwid}

Status:       ✓ HALAL
""".strip()
                
                te.setPlainText(info_text)
                te.setMinimumHeight(250)
                v.addWidget(te)
                
                btns = QHBoxLayout()
                copy_btn = QPushButton("📋 Копировать")
                def do_copy():
                    cb = QApplication.clipboard()
                    cb.setText(info_text)
                    QMessageBox.information(dlg, "✓ Успех", "Информация скопирована в буфер обмена!")
                copy_btn.clicked.connect(do_copy)
                btns.addWidget(copy_btn)
                
                close_btn = QPushButton("❌ Закрыть")
                close_btn.clicked.connect(dlg.accept)
                btns.addWidget(close_btn)
                v.addLayout(btns)
                dlg.exec()
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось получить информацию: {e}")

        logo.clicked = show_sysinfo

        # Кнопка ОК
        layout.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)

class EblanIdDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("[СТАРАЯ ВЕРСИЯ НЕ ИСПОЛЬЗУЙТЕ] Привязка EBLAN ID")
        self.setFixedSize(380, 250)

        self.eblan_id = None

        layout = QVBoxLayout(self)

        info = QLabel(
            "Привет, я ассистент по EblanID системе синхранизации<br>"
            "Если ты хочешь привязать <b>EBLAN ID</b>.<br>"
            "👉 <a href='https://t.me/EBLANID_BOT'>"
            "нажми на меня</a><br><br>"
            "А если нет, просто нажми иди нахуй✅")
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        info.setOpenExternalLinks(True)
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Вставь EBLAN ID (24 символа)")
        #self.input.setEnabled(False)
        layout.addWidget(self.input)

        bind_btn = QPushButton("Привязать")
        bind_btn.clicked.connect(self.verify)
        #bind_btn.setEnabled(False)
        layout.addWidget(bind_btn)

        bind_btn = QPushButton("Не хочу привязывать EBLAN ID, иди нахуй✅")
        bind_btn.clicked.connect(self._skip_and_accept)
        layout.addWidget(bind_btn)

        # по рофлу на будущие
        try:
            sc = QShortcut(QKeySequence("Ctrl+R, P"), self)
            sc.activated.connect(self._skip_and_accept)
        except Exception:
            pass


    # ✅
    def verify(self):
        eblan_id = self.input.text().strip()

        if len(eblan_id) != 24:
            QMessageBox.warning(self, "Ошибка", "EBLAN ID должен быть 24 символа")
            return

        try:
            r = requests.get(
                "https://twgood.serv00.net/id/main.php",
                params={"idc": eblan_id},
                timeout=5
            )
        except Exception:
            QMessageBox.critical(self, "Ошибка", "Cервер EBLAN ID недоступен")
            return

        if r.status_code == 200 and r.text.strip() == "OK":
            self.eblan_id = eblan_id
            save_eblan_id(eblan_id)
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "На данный момент принимается любая хуйня на 24 символа!!!",
            )

    def _skip_and_accept(self):
        try:
            global SKIP_EBLAN_ID
            SKIP_EBLAN_ID = True
        except Exception:
            pass
        self.accept()



class UpdateDialog(QDialog):
    def __init__(self, current_version, new_version, changelog, download_url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle("Доступно обновление!")
        self.setWindowIcon(QIcon(os.path.join('images', 'update.png')))
        self.download_url = download_url

        layout = QVBoxLayout()

        title = QLabel(f"EBLAN {new_version}")
        font = title.font()
        font.setPointSize(16)
        title.setFont(font)
        layout.addWidget(title)

        layout.addWidget(QLabel(f"Текущая версия: {current_version}"))

        layout.addWidget(QLabel("Список изменений:"))

        changelog_text = QTextEdit()
        changelog_text.setPlainText(changelog)
        changelog_text.setReadOnly(True)
        layout.addWidget(changelog_text)

        button_box = QDialogButtonBox()
        update_button = button_box.addButton("Обновить", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel_button = button_box.addButton("Нет, спасибо", QDialogButtonBox.ButtonRole.RejectRole)

        update_button.clicked.connect(self.accept_update)
        cancel_button.clicked.connect(self.reject)

        layout.addWidget(button_box)
        self.setLayout(layout)

    def accept_update(self):
        QDesktopServices.openUrl(QUrl(self.download_url))
        self.accept()


class SettingsDialog(QDialog):
    """Firefox-style настройки: сайдбар слева, содержимое справа.
    Автоматически подстраивается под светлую/тёмную тему системы."""

    @staticmethod
    def _detect_dark_theme():
        """Определяем тёмную тему по яркости Window-цвета из палитры Qt."""
        try:
            app = QApplication.instance()
            if app is None:
                return False
            c = app.palette().color(QPalette.ColorRole.Window)
            # perceived luminance
            lum = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue())
            return lum < 128
        except Exception:
            return False

    @staticmethod
    def _build_qss(dark):
        if dark:
            # Firefox Dark (Proton)
            t = {
                "bg":        "#1c1b22",
                "panel":     "#2b2a33",
                "card":      "#23222b",
                "border":    "#3a3944",
                "text":      "#fbfbfe",
                "text_dim":  "#b1b1b3",
                "hover":     "#52525e",
                "sel_bg":    "#2b4566",
                "accent":    "#00ddff",
                "accent_hi": "#80ebff",
                "input_bg":  "#1c1b22",
                "btn_bg":    "#2b2a33",
                "btn_hover": "#52525e",
                "btn_press": "#6e6e7a",
                "primary":   "#00ddff",
                "primary_hv":"#80ebff",
                "primary_fg":"#0c0c0d",
                "danger":    "#ff4f5e",
                "danger_hv": "#ff8088",
            }
        else:
            # Firefox Light (Proton)
            t = {
                "bg":        "#f9f9fb",
                "panel":     "#f0f0f4",
                "card":      "#ffffff",
                "border":    "#d7d7db",
                "text":      "#0c0c0d",
                "text_dim":  "#737373",
                "hover":     "#e0e0e6",
                "sel_bg":    "#d7e9ff",
                "accent":    "#0060df",
                "accent_hi": "#003eaa",
                "input_bg":  "#ffffff",
                "btn_bg":    "#ededf0",
                "btn_hover": "#d7d7db",
                "btn_press": "#b1b1b3",
                "primary":   "#0060df",
                "primary_hv":"#003eaa",
                "primary_fg":"#ffffff",
                "danger":    "#d70022",
                "danger_hv": "#a4000f",
            }

        return f"""
            QDialog {{
                background: {t["bg"]};
                color: {t["text"]};
            }}
            QWidget#ffSidebar {{
                background: {t["panel"]};
                border-right: 1px solid {t["border"]};
            }}
            QLabel#ffBrand {{
                color: {t["text"]};
                font-size: 15px;
                font-weight: 700;
                padding: 4px 16px 12px 16px;
            }}
            QListWidget#ffNav {{
                background: transparent;
                border: none;
                outline: 0;
                font-size: 13px;
                padding: 8px 0;
                color: {t["text"]};
            }}
            QListWidget#ffNav::item {{
                padding: 10px 16px;
                color: {t["text"]};
                border-left: 3px solid transparent;
                margin: 1px 6px;
                border-radius: 4px;
            }}
            QListWidget#ffNav::item:hover {{
                background: {t["hover"]};
            }}
            QListWidget#ffNav::item:selected {{
                background: {t["sel_bg"]};
                color: {t["accent"]};
                border-left: 3px solid {t["accent"]};
                font-weight: bold;
            }}
            QLabel#ffPageTitle {{
                font-size: 20px;
                font-weight: 600;
                color: {t["text"]};
                padding-bottom: 8px;
                border-bottom: 1px solid {t["border"]};
            }}
            QLabel#ffHint {{
                color: {t["text_dim"]};
                font-size: 11px;
            }}
            QLabel#ffVersion {{
                color: {t["text_dim"]};
                font-size: 11px;
                padding: 8px 16px;
            }}
            QWidget#ffContent {{
                background: {t["bg"]};
                color: {t["text"]};
            }}
            QScrollArea#ffScroll {{
                background: {t["bg"]};
                border: none;
            }}
            QScrollArea#ffScroll > QWidget > QWidget {{
                background: {t["bg"]};
            }}
            QCheckBox {{
                color: {t["text"]};
                padding: 4px 0;
                spacing: 8px;
                background: transparent;
            }}
            QLabel {{
                color: {t["text"]};
                background: transparent;
            }}
            QLineEdit, QComboBox {{
                background: {t["input_bg"]};
                color: {t["text"]};
                border: 1px solid {t["border"]};
                border-radius: 2px;
                padding: 6px 8px;
                selection-background-color: {t["accent"]};
                selection-color: {t["primary_fg"]};
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 2px solid {t["accent"]};
                padding: 5px 7px;
            }}
            QComboBox QAbstractItemView {{
                background: {t["card"]};
                color: {t["text"]};
                selection-background-color: {t["sel_bg"]};
                selection-color: {t["accent"]};
                border: 1px solid {t["border"]};
            }}
            QPushButton {{
                background: {t["btn_bg"]};
                color: {t["text"]};
                border: 1px solid transparent;
                border-radius: 2px;
                padding: 7px 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: {t["btn_hover"]};
            }}
            QPushButton:pressed {{
                background: {t["btn_press"]};
            }}
            QPushButton#ffPrimary {{
                background: {t["primary"]};
                color: {t["primary_fg"]};
            }}
            QPushButton#ffPrimary:hover {{
                background: {t["primary_hv"]};
            }}
            QPushButton#ffDanger {{
                background: {t["danger"]};
                color: #ffffff;
            }}
            QPushButton#ffDanger:hover {{
                background: {t["danger_hv"]};
            }}
            QFrame#ffCard {{
                background: {t["card"]};
                border: 1px solid {t["border"]};
                border-radius: 4px;
            }}
            QFrame#ffFooter {{
                background: {t["panel"]};
                border-top: 1px solid {t["border"]};
            }}
        """

    def __init__(self, enable_eblan_ai, subscription_level="pro", update_branch="main", main_window=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_window = main_window
        self.setWindowTitle("На��тр��йк�� — EBLAN Browser")
        self.subscription_level = subscription_level
        self.ai_server = getattr(main_window, 'ai_server', "https://api.mistral.ai/v1/chat/completions")
        self.ai_key = getattr(main_window, 'ai_key', "tx4pRKoTH9hyBIX9B20gHpGGWuKa49RD")
        self.ai_model = getattr(main_window, 'ai_model', "mistral-large-2512")
        self._initial_branch = update_branch
        self._initial_ai = enable_eblan_ai

        self._is_dark = self._detect_dark_theme()
        # Если активна Ecss-тема — не п��именяем локальный QSS, чтобы тема с QApplication
        # распространилась на диалог. Иначе — дефолтный стиль настроек.
        if not (getattr(main_window, 'ecss_theme', '') or '').strip():
            self.setStyleSheet(self._build_qss(self._is_dark))
        self.setMinimumSize(920, 620)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- Sidebar ----------
        sidebar = QWidget()
        sidebar.setObjectName("ffSidebar")
        sidebar.setFixedWidth(240)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 16, 0, 12)
        sb_layout.setSpacing(8)

        brand = QLabel("Настройки")
        brand.setObjectName("ffBrand")
        sb_layout.addWidget(brand)

        self.nav = QListWidget()
        self.nav.setObjectName("ffNav")
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for name in [
            "Основные",
            "История и кеш",
            "Загрузки",
            "EBLAN AI",
            "Геймер-режим",
            "Время проёба",
            "Темы (Ecss)",
            "VLESS VPN",
            "EBLAN ID",
            "Обновления",
            "Опасная зона",
        ]:
            self.nav.addItem(QListWidgetItem(name))
        sb_layout.addWidget(self.nav, 1)

        ver = QLabel(f"  EBLAN Browser\n  {getattr(main_window, 'current_version', '')}")
        ver.setObjectName("ffVersion")
        sb_layout.addWidget(ver)

        root.addWidget(sidebar)

        # ---------- Content ----------
        content_wrap = QWidget()
        content_wrap.setObjectName("ffContent")
        cw_layout = QVBoxLayout(content_wrap)
        cw_layout.setContentsMargins(0, 0, 0, 0)
        cw_layout.setSpacing(0)

        self.stack = QStackedWidget()
        cw_layout.addWidget(self.stack, 1)

        # Pages
        self.stack.addWidget(self._build_general_page())
        self.stack.addWidget(self._build_history_page())
        self.stack.addWidget(self._build_downloads_page())
        self.stack.addWidget(self._build_ai_page())
        self.stack.addWidget(self._build_gamer_page())
        self.stack.addWidget(self._build_wasted_page())
        self.stack.addWidget(self._build_themes_page())
        self.stack.addWidget(self._build_vless_page())
        self.stack.addWidget(self._build_eblanid_page())
        self.stack.addWidget(self._build_updates_page())
        self.stack.addWidget(self._build_danger_page())

        # Footer with buttons
        footer = QFrame()
        footer.setObjectName("ffFooter")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(16, 10, 16, 10)
        f_layout.addStretch()

        cancel_btn = QPushButton("Отмена")
        def on_cancel():
            # Откатить предпросмотр Ecss к сохранённой теме
            try:
                EcssEngine.apply(getattr(self.main_window, 'ecss_theme', '') or '')
            except Exception:
                pass
            self.reject()
        cancel_btn.clicked.connect(on_cancel)
        f_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Сохранить")
        ok_btn.setObjectName("ffPrimary")
        ok_btn.clicked.connect(self.accept)
        f_layout.addWidget(ok_btn)

        cw_layout.addWidget(footer)

        root.addWidget(content_wrap, 1)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

    def changeEvent(self, event):
        """Пересобираем тему, если система переключилась между светлой и тёмной."""
        try:
            if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange, QEvent.Type.ThemeChange):
                is_dark = self._detect_dark_theme()
                if is_dark != self._is_dark:
                    self._is_dark = is_dark
                    # не перетираем Ecss-тему своим QSS
                    if not (getattr(self.main_window, 'ecss_theme', '') or '').strip():
                        self.setStyleSheet(self._build_qss(is_dark))
        except Exception:
            pass
        super().changeEvent(event)

    # ---------- helpers ----------
    def _page(self, title):
        page = QWidget()
        page.setObjectName("ffContent")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("ffScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        inner.setObjectName("ffContent")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(40, 32, 40, 32)
        inner_layout.setSpacing(16)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("ffPageTitle")
        inner_layout.addWidget(title_lbl)

        scroll.setWidget(inner)
        page_layout.addWidget(scroll)

        return page, inner_layout

    def _card(self, parent_layout):
        card = QFrame()
        card.setObjectName("ffCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        parent_layout.addWidget(card)
        return lay

    def _hint(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("ffHint")
        lbl.setWordWrap(True)
        return lbl

    # ---------- pages ----------
    def _build_general_page(self):
        page, layout = self._page("Основные")

        card = self._card(layout)
        card.addWidget(QLabel("<b>Общие параметры</b>"))
        fsb_checkbox = QCheckBox("Отправка данных в ФСБ (шутка)")
        fsb_checkbox.setChecked(True)
        fsb_checkbox.setEnabled(False)
        card.addWidget(fsb_checkbox)
        card.addWidget(self._hint("Так как мы сотрудничаем с ФСБ, мы вынуждены отправлять им некоторые данные. Но не волнуйтесь, ваши данные в безопасности (нет)."))

        layout.addStretch()
        return page

    def _build_history_page(self):
        page, layout = self._page("История и кеш")

        card = self._card(layout)
        card.addWidget(QLabel("<b>История просмотров</b>"))
        self.enable_history_checkbox = QCheckBox("Вести историю посещённых сайтов")
        self.enable_history_checkbox.setChecked(getattr(self.main_window, 'history_enabled', True))
        card.addWidget(self.enable_history_checkbox)
        card.addWidget(self._hint("EBLAN Browser будет запоминать посещённые страницы."))

        layout.addStretch()
        return page

    def _build_downloads_page(self):
        page, layout = self._page("Загрузки")

        card = self._card(layout)
        card.addWidget(QLabel("<b>Папка для сохранения файлов</b>"))

        row = QHBoxLayout()
        self.downloads_folder_display = QLineEdit()
        self.downloads_folder_display.setReadOnly(True)
        self.downloads_folder_display.setText(get_downloads_path())
        row.addWidget(self.downloads_folder_display)

        choose_btn = QPushButton("Обзор…")
        def choose_folder():
            folder = QFileDialog.getExistingDirectory(self, "Выберите папку для загрузок", self.downloads_folder_display.text())
            if folder:
                self.downloads_folder_display.setText(folder)
        choose_btn.clicked.connect(choose_folder)
        row.addWidget(choose_btn)

        card.addLayout(row)
        card.addWidget(self._hint("Все скачанные файлы будут автоматически сохраняться в эту папку."))

        layout.addStretch()
        return page

    def _build_ai_page(self):
        page, layout = self._page("EBLAN AI")

        card = self._card(layout)
        card.addWidget(QLabel("<b>EBLAN AI (Beta)</b>"))
        self.enable_eblan_ai_checkbox = QCheckBox("Включить EBLAN AI в панели инструментов")
        self.enable_eblan_ai_checkbox.setChecked(self._initial_ai)
        card.addWidget(self.enable_eblan_ai_checkbox)
        card.addWidget(self._hint("Искусственный еблан ответит на ваши вопросы. Иногда."))

        card2 = self._card(layout)
        card2.addWidget(QLabel("<b>Конфигурация API</b>"))

        card2.addWidget(QLabel("Сервер API"))
        self.ai_server_input = QLineEdit()
        self.ai_server_input.setText(self.ai_server)
        card2.addWidget(self.ai_server_input)

        card2.addWidget(QLabel("API ключ"))
        self.ai_key_input = QLineEdit()
        self.ai_key_input.setText(self.ai_key)
        self.ai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        card2.addWidget(self.ai_key_input)

        card2.addWidget(QLabel("Модель"))
        self.ai_model_input = QLineEdit()
        self.ai_model_input.setText(self.ai_model)
        card2.addWidget(self.ai_model_input)

        layout.addStretch()
        return page

    def _build_gamer_page(self):
        page, layout = self._page("Геймер-режим")

        card = self._card(layout)
        card.addWidget(QLabel("<b>Гейминг в браузере</b>"))
        self.gamer_mode_checkbox = QCheckBox("Включить EBLAN SoftBoost™")
        self.gamer_mode_checkbox.setChecked(getattr(self.main_window, 'gamer_mode', False))
        card.addWidget(self.gamer_mode_checkbox)
        card.addWidget(self._hint(
            "Благодоря EBLAN SoftBoost™, браузер будет использовать все ресурсы вашего компьютера для достижения максимальной производительности. "
            "Отображает крутой FPS-счётчик поверх окна. "
            "Побочный эффект: реальная производительность браузера может ощутимо просесть. "
            "Но кому это важно, когда у тебя 9999 FPS?"
        ))

        card2 = self._card(layout)
        card2.addWidget(QLabel("<b>Дополнительно</b>"))
        self.gamer_boost_checkbox = QCheckBox("EBLAN SoftBoost™ Выключатель™")
        self.gamer_boost_checkbox.setChecked(True)
        card2.addWidget(self.gamer_boost_checkbox)
        card2.addWidget(self._hint("Выключает EBLAN SoftBoost™, правда у нас нет такой функции по этому вы обречены использовать её вечно:)"))

        # Зумер-режим (молодёжные фишки, передоз)
        card3 = self._card(layout)
        # Радужный переливающийся заголовок (анимируется по таймеру).
        self._zoomer_title = QLabel()
        self._zoomer_title.setTextFormat(Qt.TextFormat.RichText)
        self._zoomer_title_text = "Зумер-режим 💀🔥 (brainrot)"
        self._zoomer_rainbow_phase = 0.0
        card3.addWidget(self._zoomer_title)
        self._zoomer_rainbow_timer = QTimer(self)
        self._zoomer_rainbow_timer.timeout.connect(self._tick_zoomer_rainbow)
        self._zoomer_rainbow_timer.start(70)
        self._tick_zoomer_rainbow()
        self.zoomer_mode_checkbox = QCheckBox("Включить зумер-режим")
        self.zoomer_mode_checkbox.setChecked(bool(getattr(self.main_window, 'zoomer_mode', False)))
        card3.addWidget(self.zoomer_mode_checkbox)
        card3.addWidget(self._hint(
            "Полный передоз молодёжкой: брейнрот-фразы в статусбаре (скибиди, rizz, "
            "сигма, based, no cap…), счётчик AURA с RGB-переливом, залпы эмодзи-конфетти "
            "и секретный Konami-код (↑↑↓↓←→←→ B A) на +9999 AURA. "
            "Чистый вайб, ноль смысла. 🗿"
        ))

        layout.addStretch()
        return page

    def _build_wasted_page(self):
        page, layout = self._page("Сколько времени ты проебал")

        mw = self.main_window
        total = 0
        level_title, level_desc = "Новичок-еблан", ""
        try:
            total = mw._current_wasted_total() if mw else 0
            level_title, level_desc = wasted_level(total)
        except Exception:
            pass

        hero = self._card(layout)
        hero.addWidget(QLabel("<b>Общий счёт</b>"))

        self._wasted_big_label = QLabel(format_wasted(total))
        self._wasted_big_label.setStyleSheet(
            "font-size: 34px; font-weight: 900; padding: 4px 0;"
        )
        hero.addWidget(self._wasted_big_label)

        self._wasted_level_label = QLabel(f"Звание: <b>{level_title}</b>")
        self._wasted_level_label.setStyleSheet("font-size: 14px;")
        hero.addWidget(self._wasted_level_label)

        self._wasted_desc_label = QLabel(level_desc)
        self._wasted_desc_label.setObjectName("ffHint")
        self._wasted_desc_label.setWordWrap(True)
        hero.addWidget(self._wasted_desc_label)

        # Разбивка
        stats = self._card(layout)
        stats.addWidget(QLabel("<b>Разбивка по масштабу трагедии</b>"))

        days = total / 86400.0
        hours = total / 3600.0
        minutes = total / 60.0
        lines = [
            f"В секундах: <b>{total:,}</b>".replace(",", " "),
            f"В минутах: <b>{minutes:,.1f}</b>".replace(",", " "),
            f"В часах: <b>{hours:,.2f}</b>".replace(",", " "),
            f"В днях: <b>{days:,.3f}</b>".replace(",", " "),
        ]
        for t in lines:
            lbl = QLabel(t)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            stats.addWidget(lbl)

        # Альтернатива
        fun = self._card(layout)
        fun.addWidget(QLabel("<b>Что ты мог сделать за это время</b>"))
        alt = [
            ("серий «Бригады» посмотреть", 50 * 60),
            ("раз сходить в качалку", 60 * 60),
            ("прочитать «Войну и мир» (страниц)", 90),
            ("кругов по району пробежать", 25 * 60),
            ("раз позвонить маме (по 5 мин)", 5 * 60),
        ]
        for name, seconds_per in alt:
            count = total // max(1, seconds_per)
            lbl = QLabel(f"{name}: <b>{count}</b>")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            fun.addWidget(lbl)

        # Действия
        actions = self._card(layout)
        actions.addWidget(QLabel("<b>Действия</b>"))
        row = QHBoxLayout()
        reset_btn = QPushButton("Обнулить счётчик")
        reset_btn.setObjectName("ffDanger")
        def do_reset():
            if self.main_window is not None:
                self.main_window.reset_wasted()
                try:
                    new_total = self.main_window._current_wasted_total()
                    self._wasted_big_label.setText(format_wasted(new_total))
                    lvl_title, lvl_desc = wasted_level(new_total)
                    self._wasted_level_label.setText(f"Звание: <b>{lvl_title}</b>")
                    self._wasted_desc_label.setText(lvl_desc)
                except Exception:
                    pass
        reset_btn.clicked.connect(do_reset)
        row.addWidget(reset_btn)
        row.addStretch()
        actions.addLayout(row)
        actions.addWidget(self._hint("Счётчик обновляется каждую секунду в статус-баре."))

        # Live-обновление большой цифры
        self._wasted_page_timer = QTimer(self)
        def tick():
            try:
                if self.main_window is None:
                    return
                t2 = self.main_window._current_wasted_total()
                self._wasted_big_label.setText(format_wasted(t2))
            except Exception:
                pass
        self._wasted_page_timer.timeout.connect(tick)
        self._wasted_page_timer.start(1000)

        layout.addStretch()
        return page

    def _build_themes_page(self):
        page, layout = self._page("Темы (Ecss)")

        intro = self._card(layout)
        intro.addWidget(QLabel("<b>Eblan CSS — ебашь браузер как хочешь</b>"))
        intro.addWidget(self._hint(
            "Ecss — мини-язык на базе CSS, который компилируется в QSS и применяется ко всему "
            "браузеру. Выбери пресет или напиши свой. Синтаксис: ключ: значение. "
            "Комментарии — #. Для сырого QSS — блок !raw ... !end."
        ))

        # Пресеты
        presets_card = self._card(layout)
        presets_card.addWidget(QLabel("<b>Готовые пресеты</b>"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Пресет:"))
        self.ecss_preset_combo = QComboBox()
        for name in ECSS_PRESETS.keys():
            self.ecss_preset_combo.addItem(name)
        row.addWidget(self.ecss_preset_combo, 1)
        load_preset_btn = QPushButton("Загрузить в редактор")
        def load_preset():
            name = self.ecss_preset_combo.currentText()
            src = ECSS_PRESETS.get(name, "")
            self.ecss_editor.setPlainText(src)
        load_preset_btn.clicked.connect(load_preset)
        row.addWidget(load_preset_btn)
        presets_card.addLayout(row)

        # Редактор
        editor_card = self._card(layout)
        editor_card.addWidget(QLabel("<b>Ecss исходник</b>"))
        self.ecss_editor = QTextEdit()
        self.ecss_editor.setAcceptRichText(False)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self.ecss_editor.setFont(mono)
        self.ecss_editor.setMinimumHeight(260)
        initial = getattr(self.main_window, 'ecss_theme', '') or ''
        self.ecss_editor.setPlainText(initial)
        editor_card.addWidget(self.ecss_editor)

        btn_row = QHBoxLayout()
        preview_btn = QPushButton("Предпросмотр")
        preview_btn.setObjectName("ffPrimary")
        def do_preview():
            src = self.ecss_editor.toPlainText()
            try:
                EcssEngine.apply(src)
            except Exception as e:
                QMessageBox.warning(self, "Ecss", f"Ошибка применения:\n{e}")
        preview_btn.clicked.connect(do_preview)
        btn_row.addWidget(preview_btn)

        revert_btn = QPushButton("Отменить предпросмотр")
        def do_revert():
            try:
                EcssEngine.apply(getattr(self.main_window, 'ecss_theme', '') or '')
            except Exception:
                pass
        revert_btn.clicked.connect(do_revert)
        btn_row.addWidget(revert_btn)

        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(lambda: self.ecss_editor.setPlainText(""))
        btn_row.addWidget(clear_btn)

        btn_row.addStretch()

        export_btn = QPushButton("Экспорт .ecss")
        def do_export():
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить тему", "my-theme.ecss", "Ecss (*.ecss);;Все файлы (*.*)")
            if path:
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(self.ecss_editor.toPlainText())
                except Exception as e:
                    QMessageBox.warning(self, "Ошибка", f"{e}")
        export_btn.clicked.connect(do_export)
        btn_row.addWidget(export_btn)

        import_btn = QPushButton("Импорт .ecss")
        def do_import():
            path, _ = QFileDialog.getOpenFileName(self, "Загрузить тему", "", "Ecss (*.ecss);;Все файлы (*.*)")
            if path:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self.ecss_editor.setPlainText(f.read())
                except Exception as e:
                    QMessageBox.warning(self, "Ошибка", f"{e}")
        import_btn.clicked.connect(do_import)
        btn_row.addWidget(import_btn)

        editor_card.addLayout(btn_row)
        editor_card.addWidget(self._hint(
            "Нажми «Сохранить» внизу окна, чтобы тема применилась навсегда. "
            "«Отменить предпросмотр» — вернёт текущую сохранённую тему."
        ))

        # Справка
        help_card = self._card(layout)
        help_card.addWidget(QLabel("<b>Доступные ключи</b>"))
        keys_text = (
            "<code>window_bg, text_color, accent, "
            "tab_bg, tab_active, toolbar_bg, "
            "urlbar_bg, urlbar_text, "
            "button_bg, button_text, button_hover, "
            "border, font_family, font_size, radius</code>"
        )
        keys_lbl = QLabel(keys_text)
        keys_lbl.setWordWrap(True)
        keys_lbl.setTextFormat(Qt.TextFormat.RichText)
        help_card.addWidget(keys_lbl)

        layout.addStretch()
        return page

    def _build_vless_page(self):
        page, layout = self._page("VLESS VPN")

        mw = self.main_window
        vc = getattr(mw, 'vless_controller', None) if mw else None

        # ---- Статус ----
        status_card = self._card(layout)
        status_card.addWidget(QLabel("<b>Статус</b>"))
        self._vless_status_label = QLabel(vc.status_text() if vc else "Контроллер не инициализирован")
        self._vless_status_label.setStyleSheet("font-size: 14px;")
        status_card.addWidget(self._vless_status_label)

        status_row = QHBoxLayout()
        self._vless_connect_btn = QPushButton("Подключить выбранный")
        self._vless_connect_btn.setObjectName("ffPrimary")
        self._vless_disconnect_btn = QPushButton("Отключить")
        self._vless_disconnect_btn.setObjectName("ffDanger")

        def do_connect():
            if not vc:
                return
            idx = self._vless_srv_list.currentRow()
            if idx < 0:
                QMessageBox.information(self, "VLESS", "Выбери сервер в списке.")
                return
            ok, msg = vc.connect_to(idx)
            if not ok:
                QMessageBox.warning(self, "VLESS", f"Не удалось подключиться:\n{msg}")
            self._vless_refresh_ui()

        def do_disconnect():
            if not vc:
                return
            vc.disconnect()
            self._vless_refresh_ui()

        self._vless_connect_btn.clicked.connect(do_connect)
        self._vless_disconnect_btn.clicked.connect(do_disconnect)
        status_row.addWidget(self._vless_connect_btn)
        status_row.addWidget(self._vless_disconnect_btn)
        status_row.addStretch()
        status_card.addLayout(status_row)
        status_card.addWidget(self._hint(
            "Подключение поднимает локальный SOCKS5 (127.0.0.1:10808) и HTTP-прокси (:10809) через xray. "
            "Chromium при следующем запуске пустит трафик через HTTP-прокси (без DNS-leak), "
            "Qt-запросы идут через SOCKS5 сразу. Для применения к браузеру перезапусти программу."
        ))

        # ---- Xray ----
        xray_card = self._card(layout)
        xray_card.addWidget(QLabel("<b>Движок Xray-core</b>"))
        xray_row = QHBoxLayout()
        xray_row.addWidget(QLabel("Путь к xray:"))
        self._vless_bin_input = QLineEdit()
        if vc:
            self._vless_bin_input.setText(vc.xray_manager.xray_bin or "")
        self._vless_bin_input.setPlaceholderText("xray или xray.exe (из PATH), либо полный путь")
        xray_row.addWidget(self._vless_bin_input, 1)
        browse_btn = QPushButton("Обзор…")
        def browse_xray():
            path, _ = QFileDialog.getOpenFileName(self, "Выбери xray-core", "",
                                                  "Все файлы (*.*)")
            if path:
                self._vless_bin_input.setText(path)
                if vc:
                    vc.xray_manager.xray_bin = path
        browse_btn.clicked.connect(browse_xray)
        xray_row.addWidget(browse_btn)
        detect_btn = QPushButton("Авто")
        def detect_xray():
            p = XrayManager.detect_binary()
            if p:
                self._vless_bin_input.setText(p)
                if vc:
                    vc.xray_manager.xray_bin = p
            else:
                QMessageBox.information(self, "VLESS",
                                        "xray не найден в PATH. Скачай его с github.com/XTLS/Xray-core и укажи путь вручную.")
        detect_btn.clicked.connect(detect_xray)
        xray_row.addWidget(detect_btn)
        xray_card.addLayout(xray_row)

        ports_row = QHBoxLayout()
        ports_row.addWidget(QLabel("SOCKS порт:"))
        self._vless_socks_input = QLineEdit()
        if vc:
            self._vless_socks_input.setText(str(vc.xray_manager.socks_port))
        self._vless_socks_input.setFixedWidth(90)
        ports_row.addWidget(self._vless_socks_input)
        ports_row.addWidget(QLabel("HTTP порт:"))
        self._vless_http_input = QLineEdit()
        if vc:
            self._vless_http_input.setText(str(vc.xray_manager.http_port))
        self._vless_http_input.setFixedWidth(90)
        ports_row.addWidget(self._vless_http_input)
        ports_row.addStretch()
        xray_card.addLayout(ports_row)

        # ---- Подписки ----
        subs_card = self._card(layout)
        subs_card.addWidget(QLabel("<b>Подписки</b>"))
        self._vless_subs_list = QListWidget()
        self._vless_subs_list.setMaximumHeight(110)
        if vc:
            for u in vc.subscriptions:
                self._vless_subs_list.addItem(u)
        subs_card.addWidget(self._vless_subs_list)

        subs_row = QHBoxLayout()
        self._vless_sub_input = QLineEdit()
        self._vless_sub_input.setPlaceholderText("https://example.com/subscription")
        subs_row.addWidget(self._vless_sub_input, 1)
        add_sub_btn = QPushButton("Добавить")
        def add_sub():
            url = self._vless_sub_input.text().strip()
            if not url or not vc:
                return
            vc.add_subscription(url)
            self._vless_subs_list.clear()
            for u in vc.subscriptions:
                self._vless_subs_list.addItem(u)
            self._vless_sub_input.clear()
        add_sub_btn.clicked.connect(add_sub)
        subs_row.addWidget(add_sub_btn)

        del_sub_btn = QPushButton("Удалить")
        def del_sub():
            item = self._vless_subs_list.currentItem()
            if not item or not vc:
                return
            vc.remove_subscription(item.text())
            self._vless_subs_list.takeItem(self._vless_subs_list.currentRow())
        del_sub_btn.clicked.connect(del_sub)
        subs_row.addWidget(del_sub_btn)
        subs_card.addLayout(subs_row)

        refresh_row = QHBoxLayout()
        refresh_btn = QPushButton("Обновить подписки")
        refresh_btn.setObjectName("ffPrimary")
        paste_vless_btn = QPushButton("Вставить одиночный vless://…")
        def do_refresh():
            if not vc:
                return
            # подтянуть актуальные порты/бинарь
            if self._vless_bin_input.text().strip():
                vc.xray_manager.xray_bin = self._vless_bin_input.text().strip()
            refresh_btn.setEnabled(False)
            refresh_btn.setText("Загружаем…")

            def done(n, errors):
                refresh_btn.setEnabled(True)
                refresh_btn.setText("Обновить подписки")
                self._vless_rebuild_server_list()
                msg = f"Загружено серверов: {n}"
                if errors:
                    msg += "\n\nОшибки:\n" + "\n".join(errors[:5])
                QMessageBox.information(self, "VLESS", msg)

            vc.refresh_subscriptions(on_done=done)
        refresh_btn.clicked.connect(do_refresh)
        refresh_row.addWidget(refresh_btn)

        def paste_uri():
            uri, ok = QInputDialog.getText(self, "VLESS URI", "Вставь vless://… :")
            if not ok or not uri.strip():
                return
            try:
                srv = parse_vless_uri(uri.strip())
                vc.servers.append(srv)
                self._vless_rebuild_server_list()
            except Exception as e:
                QMessageBox.warning(self, "VLESS", f"Не удалось распарсить:\n{e}")
        paste_vless_btn.clicked.connect(paste_uri)
        refresh_row.addWidget(paste_vless_btn)
        refresh_row.addStretch()
        subs_card.addLayout(refresh_row)

        # ---- Серверы ----
        srv_card = self._card(layout)
        srv_card.addWidget(QLabel("<b>Серверы</b>"))
        self._vless_srv_list = QListWidget()
        self._vless_srv_list.setMinimumHeight(200)
        srv_card.addWidget(self._vless_srv_list)

        srv_row = QHBoxLayout()
        ping_btn = QPushButton("Пинговать всех")
        def do_ping():
            if not vc:
                return
            vc.ping_all()
        ping_btn.clicked.connect(do_ping)
        srv_row.addWidget(ping_btn)

        clear_btn = QPushButton("Очистить список")
        def do_clear():
            if not vc:
                return
            if vc.is_connected():
                QMessageBox.information(self, "VLESS", "Сначала отключись.")
                return
            vc.servers = []
            self._vless_rebuild_server_list()
        clear_btn.clicked.connect(do_clear)
        srv_row.addWidget(clear_btn)
        srv_row.addStretch()
        srv_card.addLayout(srv_row)

        # связать сигналы контроллера с UI
        if vc:
            try:
                vc.statusChanged.connect(self._vless_refresh_ui)
                vc.serversUpdated.connect(self._vless_rebuild_server_list)
                vc.pingProgress.connect(self._vless_on_ping)
            except Exception:
                pass

        self._vless_rebuild_server_list()
        self._vless_refresh_ui()

        layout.addStretch()
        return page

    def _vless_rebuild_server_list(self):
        try:
            vc = self.main_window.vless_controller if self.main_window else None
            if vc is None or not hasattr(self, "_vless_srv_list"):
                return
            prev = self._vless_srv_list.currentRow()
            self._vless_srv_list.clear()
            for srv in vc.servers:
                self._vless_srv_list.addItem(srv.label())
            if 0 <= prev < self._vless_srv_list.count():
                self._vless_srv_list.setCurrentRow(prev)
            elif vc.active_server_idx >= 0:
                self._vless_srv_list.setCurrentRow(vc.active_server_idx)
        except Exception as e:
            print(f"[vless ui] rebuild: {e}")

    def _vless_on_ping(self, idx, ms):
        try:
            vc = self.main_window.vless_controller if self.main_window else None
            if vc is None or not hasattr(self, "_vless_srv_list"):
                return
            if 0 <= idx < self._vless_srv_list.count():
                self._vless_srv_list.item(idx).setText(vc.servers[idx].label())
        except Exception:
            pass

    def _vless_refresh_ui(self):
        try:
            vc = self.main_window.vless_controller if self.main_window else None
            if vc is None or not hasattr(self, "_vless_status_label"):
                return
            self._vless_status_label.setText(vc.status_text())
            connected = vc.is_connected()
            self._vless_connect_btn.setEnabled(not connected)
            self._vless_disconnect_btn.setEnabled(connected)
        except Exception:
            pass

    def _build_eblanid_page(self):
        page, layout = self._page("EBLAN ID")

        mw = self.main_window

        intro = self._card(layout)
        intro.addWidget(QLabel("<b>Синхронизация настроек между устройствами</b>"))
        intro.addWidget(self._hint(
            "EBLAN ID — Это наш формат передачи настроек браузера в виде зашифрованного текста. "
            "Скопируй ключ на одном компе и вставь на другом — тема, подписки VLESS, "
            "настройки AI и обновлений применятся автоматически. "
            "ВНИМАНИЕ: Пути к файлам и бинарь xray-core не сохраняются"
        ))

        # ---- Мой ключ ----
        mine = self._card(layout)
        mine.addWidget(QLabel("<b>Мой EBLAN ID</b>"))
        self._eblanid_mine = QTextEdit()
        self._eblanid_mine.setReadOnly(True)
        self._eblanid_mine.setObjectName("eblanidMine")
        self._eblanid_mine.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._eblanid_mine.setMaximumHeight(120)
        try:
            key = mw.export_eblanid() if mw else ""
        except Exception as e:
            key = ""
            print(f"[eblanid] export error: {e}")
        self._eblanid_mine.setPlainText(key)
        mine.addWidget(self._eblanid_mine)

        mine_row = QHBoxLayout()
        copy_btn = QPushButton("Скопировать ключ")
        copy_btn.setObjectName("ffPrimary")
        def do_copy():
            QApplication.clipboard().setText(self._eblanid_mine.toPlainText())
            copy_btn.setText("Скопировано!")
            QTimer.singleShot(1500, lambda: copy_btn.setText("Скопировать ключ"))
        copy_btn.clicked.connect(do_copy)
        mine_row.addWidget(copy_btn)

        refresh_btn = QPushButton("Пересчитать")
        def do_refresh():
            try:
                self._eblanid_mine.setPlainText(mw.export_eblanid() if mw else "")
            except Exception as e:
                QMessageBox.warning(self, "EBLAN ID", f"Ошибка: {e}")
        refresh_btn.clicked.connect(do_refresh)
        mine_row.addWidget(refresh_btn)

        save_btn = QPushButton("Сохранить в файл…")
        def do_save():
            path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить EBLAN ID", "eblanid.txt",
                "Текстовые файлы (*.txt);;Все файлы (*.*)"
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._eblanid_mine.toPlainText())
                QMessageBox.information(self, "EBLAN ID", "Ключ сохранён.")
            except Exception as e:
                QMessageBox.warning(self, "EBLAN ID", f"Не удалось сохранить:\n{e}")
        save_btn.clicked.connect(do_save)
        mine_row.addWidget(save_btn)

        mine_row.addStretch()
        mine.addLayout(mine_row)
        mine.addWidget(self._hint(
            "Длина ключа зависит от количества VLESS-сервер��в и размера Ecss-темы."
        ))

        # ---- Применить чужой ключ ----
        apply_card = self._card(layout)
        apply_card.addWidget(QLabel("<b>Применить EBLAN ID</b>"))
        self._eblanid_input = QTextEdit()
        self._eblanid_input.setPlaceholderText("Вставь ebl_… сюда")
        self._eblanid_input.setMaximumHeight(100)
        apply_card.addWidget(self._eblanid_input)

        apply_row = QHBoxLayout()
        paste_btn = QPushButton("Вставить из буфера")
        def do_paste():
            t = QApplication.clipboard().text() or ""
            self._eblanid_input.setPlainText(t.strip())
        paste_btn.clicked.connect(do_paste)
        apply_row.addWidget(paste_btn)

        load_btn = QPushButton("Загрузить из файла…")
        def do_load():
            path, _ = QFileDialog.getOpenFileName(
                self, "Загрузить EBLAN ID", "",
                "Текстовые файлы (*.txt);;Все файлы (*.*)"
            )
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._eblanid_input.setPlainText(f.read().strip())
            except Exception as e:
                QMessageBox.warning(self, "EBLAN ID", f"Не удалось открыть:\n{e}")
        load_btn.clicked.connect(do_load)
        apply_row.addWidget(load_btn)

        apply_btn = QPushButton("Применить")
        apply_btn.setObjectName("ffPrimary")
        def do_apply():
            if not mw:
                return
            key = self._eblanid_input.toPlainText().strip()
            if not key:
                QMessageBox.information(self, "EBLAN ID", "Сначала вставь ключ.")
                return
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("EBLAN ID")
            box.setText("Применить настройки из этого ключа? Текущие будут перезаписаны.")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if box.exec() != QMessageBox.StandardButton.Yes:
                return
            ok, msg = mw.import_eblanid(key)
            if ok:
                QMessageBox.information(
                    self, "EBLAN ID",
                    f"{msg}\n\nЧасть изменений (VPN в Chromium) вступит в силу после перезапуска."
                )
                # обновить свой отображаемый ключ + перестроить списки VLESS
                try:
                    self._eblanid_mine.setPlainText(mw.export_eblanid())
                except Exception:
                    pass
                try:
                    self._vless_rebuild_server_list()
                    self._vless_refresh_ui()
                except Exception:
                    pass
            else:
                QMessageBox.warning(self, "EBLAN ID", f"Ошибка:\n{msg}")
        apply_btn.clicked.connect(do_apply)
        apply_row.addWidget(apply_btn)

        apply_row.addStretch()
        apply_card.addLayout(apply_row)

        layout.addStretch()
        return page

    def _build_updates_page(self):
        page, layout = self._page("Обновления")

        card = self._card(layout)
        card.addWidget(QLabel("<b>Канал обновлений</b>"))
        card.addWidget(QLabel("Ветка обновления:"))
        self.branch_combo = QComboBox()
        self.branch_combo.addItems(["Релиз", "Бета тестировани��", "вн��треннее тестирование"])
        idx = {"main": 0, "public_beta": 1, "closed_beta": 2}.get(self._initial_branch, 0)
        self.branch_combo.setCurrentIndex(idx)
        card.addWidget(self.branch_combo)
        card.addWidget(self._hint("⚠ Бета-ветки могут быть нестабильны."))

        # API-база бэкенда обновлений
        api_card = self._card(layout)
        api_card.addWidget(QLabel("<b>Сервер обновлений (backend API)</b>"))
        api_card.addWidget(QLabel("API base URL:"))
        self.update_api_input = QLineEdit()
        current_api = getattr(self.main_window, 'update_api_base', '') or ''
        self.update_api_input.setText(current_api)
        self.update_api_input.setPlaceholderText("https://update.riba.click/eb/upd/public/index.php")
        api_card.addWidget(self.update_api_input)
        api_card.addWidget(self._hint(
            "Указывай корень бэкенда (см. backend/public/). Поддерживается и "
            "старый формат — прямая ссылка на version.json."
        ))

        api_row = QHBoxLayout()
        test_btn = QPushButton("Проверить соединение")
        def do_test():
            url = self.update_api_input.text().strip()
            if not url:
                QMessageBox.warning(self, "Обновления", "URL пустой.")
                return
            try:
                self.main_window.update_service.api_base_url = url
                self.main_window.update_api_base = url
                self.main_window.check_for_updates(interactive=True)
            except Exception as e:
                QMessageBox.warning(self, "Обновления", f"Ошибка:\n{e}")
        test_btn.clicked.connect(do_test)
        api_row.addWidget(test_btn)
        api_row.addStretch()
        api_card.addLayout(api_row)

        # Экспериментальное: режим отладки
        dbg_card = self._card(layout)
        dbg_card.addWidget(QLabel("<b>Отладка (экспериментальное)</b>"))
        self.debug_checkbox = QCheckBox("Отладка")
        self.debug_checkbox.setChecked(bool(getattr(self.main_window, 'debug_mode', False)))
        dbg_card.addWidget(self.debug_checkbox)
        dbg_card.addWidget(self._hint(
            "Врубает ПОДРОБНОЕ логирование во всех подсистемах: навигация и вкладки, "
            "загрузки, обновления, VLESS/прокси, баны и EBLAN ID, плюс внутренние "
            "сообщения движка Qt/WebEngine. В консоли (терминал, откуда запущен браузер) "
            "повалит дохуя логов с таймстампами — это для диагностики багов, в обычной "
            "жизни не нужно и немного грузит. Применяется сразу при сохранении; "
            "часть низкоуровневых логов Qt включится полностью после перезапуска."
        ))

        card2 = self._card(layout)
        card2.addWidget(QLabel("<b>Откат</b>"))
        rollback_btn = QPushButton("Откатиться на старую версию")
        rollback_btn.clicked.connect(self.main_window.show_rollback_dialog)
        card2.addWidget(rollback_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()
        return page

    def _build_danger_page(self):
        page, layout = self._page("Опасная зона")

        card = self._card(layout)
        card.addWidget(QLabel("<b>Сброс настроек</b>"))
        card.addWidget(self._hint(
            "Это удалит файл инициализации и при следующем запуске браузер "
            "начнёт с нуля. Все ваши настройки будут потеряны."
        ))
        reset_btn = QPushButton("⚠  Сбросить на заводские настройки")
        reset_btn.setObjectName("ffDanger")

        def reset_settings():
            confirm = QMessageBox.question(
                self,
                "Подтверждение сброса",
                "Вы уверены? Это удалит файл инициализации и при следующем запуске браузер начнёт с нуля.\n\nВсе ваши настройки будут потеряны!",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    init_file = os.path.join(os.path.dirname(get_settings_path()), "eblan_initiated")
                    if os.path.exists(init_file):
                        os.remove(init_file)
                    QMessageBox.information(self, "Готово", "Да начнем все сначало!")
                except Exception as e:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось удалить файл: {e}")

        reset_btn.clicked.connect(reset_settings)
        card.addWidget(reset_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()
        return page

    # ---------- getters ----------
    def get_eblan_ai_state(self):
        return self.enable_eblan_ai_checkbox.isChecked()

    def get_history_enabled(self):
        return self.enable_history_checkbox.isChecked()

    def get_downloads_folder(self):
        return self.downloads_folder_display.text()

    def get_selected_branch(self):
        return ["main", "public_beta", "closed_beta"][self.branch_combo.currentIndex()]

    def get_gamer_mode(self):
        return self.gamer_mode_checkbox.isChecked()

    def get_zoomer_mode(self):
        try:
            return self.zoomer_mode_checkbox.isChecked()
        except Exception:
            return False

    def _tick_zoomer_rainbow(self):
        """Перекрашивает заголовок зумер-режима по буквам — радуга переливается."""
        try:
            import colorsys
            text = getattr(self, '_zoomer_title_text', 'Зумер-режим')
            self._zoomer_rainbow_phase = (getattr(self, '_zoomer_rainbow_phase', 0.0) + 0.03) % 1.0
            phase = self._zoomer_rainbow_phase
            n = max(len(text), 1)
            parts = []
            for i, ch in enumerate(text):
                if ch == ' ':
                    parts.append('&nbsp;')
                    continue
                hh = ((i / n) + phase) % 1.0
                r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hh, 0.95, 1.0)]
                parts.append(f'<span style="color:#{r:02x}{g:02x}{b:02x}">{ch}</span>')
            self._zoomer_title.setText(f"<b>{''.join(parts)}</b>")
        except Exception:
            pass

    def get_ecss_source(self):
        try:
            return self.ecss_editor.toPlainText()
        except Exception:
            return getattr(self.main_window, 'ecss_theme', '') or ''

    def get_update_api_base(self):
        try:
            return self.update_api_input.text().strip()
        except Exception:
            return None

    def get_debug_mode(self):
        try:
            return self.debug_checkbox.isChecked()
        except Exception:
            return False

    def get_ai_config(self):
        return {
            "server": self.ai_server_input.text(),
            "key": self.ai_key_input.text(),
            "model": self.ai_model_input.text()
        }


class BetaSettingsDialog(QDialog):
    def __init__(self, parent=None, main_window=None):
        super().__init__(parent)
        self.setWindowTitle("EBLAN Lab")
        self.main_window = main_window

        layout = QVBoxLayout()

        warning = QLabel("Данное меню больше не поддерживается. Функции представленные тут были удаленны.")
        warning.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(warning)

        btn_open_settings = QPushButton("Открыть файл настроек (settings.json)")
        btn_open_settings.clicked.connect(self.open_settings_file)
        layout.addWidget(btn_open_settings)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)


    def open_settings_file(self):
        try:
            path = get_settings_path()
            if os.path.exists(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            else:
                QMessageBox.warning(self, "Ошибка", f"Файл настроек не найден: {path}")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть файл: {e}")


class AIChatDialog(QDialog):
    def __init__(self, main_window, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_window = main_window
        self.setWindowTitle("EBLAN AI")
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout()

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history)

        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Введите запрос...")
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field)

        send_btn = QPushButton("Отправить")
        send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(send_btn)

        layout.addLayout(input_layout)

        self.setLayout(layout)

        self.chat_history.append("EBLAN AI: Привет! Я EblanAI, созданный компанией EBLAN, чтобы помогать пользователям Eblan Browser. Задай свой вопрос, и я отвечу на русском!")

    def send_message(self):
        query = self.input_field.text().strip()
        if not query:
            return

        self.chat_history.append(f"Вы: {query}")
        self.input_field.clear()


        QTimer.singleShot(1500, lambda: self.generate_response(query))

    def disable_eblan_ai(self):
        self.main_window.enable_eblan_ai = False
        try:
            with open(get_settings_path(), "w", encoding="utf-8") as f:
                json.dump({
                    "subscription_level": self.main_window.subscription_level,
                    "update_branch": self.main_window.update_branch,
                    "enable_eblan_ai": self.main_window.enable_eblan_ai
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Ошибка сохранения настроек:", e)

        self.main_window.ai_action.setEnabled(False)
        self.chat_history.append("EBLAN AI: Я отключён! Прощай, пользователь!")
        QTimer.singleShot(1000, self.close)

    def generate_response(self, query):
        try:
            system_prompt = (
                "Ты EblanAI, созданный компанией EBLAN, чтобы помогать пользователям Eblan Browser."
                "Всегда отвечай на русском языке. Твой ответ должен быть полезным и соответствовать запросу пользователя."
                "Скачать еблан браузер можно https://eblanbrowser.ru"
                "Отвечай всегда без форматирования"
                "Если запрос не ясен, попроси уточнить. Если запрос не по теме Eblan browser, вежливо откажись отвечать."
            )
            request = QNetworkRequest(QUrl("https://api.mistral.ai/v1/chat/completions"))
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
            request.setRawHeader(b"Authorization", b"Bearer tx4pRKoTH9hyBIX9B20gHpGGWuKa49RD")
            data = json.dumps({
                "model": "mistral-large-2512",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                "max_tokens": 500,
                "temperature": 0.7
            }).encode('utf-8')
            reply = self.main_window.network_manager.post(request, data)
            reply.finished.connect(lambda: self.handle_ai_response(reply))
        except Exception as e:
            self.chat_history.append(f"EBLAN AI: Ошибка при обращении к серверу: {str(e)}")

    def handle_ai_response(self, reply):
        try:
            data = reply.readAll().data().decode('utf-8')
            resp = json.loads(data)

            if not resp.get("choices") or len(resp["choices"]) == 0:
                self.chat_history.append("EBLAN AI: сервер молчит как рыба, я в шоке")
                return

            content = resp["choices"][0]["message"].get("content")
            
            if content is None or content.strip() == "":
                self.chat_history.append("EBLAN AI: сервер отдал пустоту, я не знаю что сказать")
            else:
                self.chat_history.append(f"EBLAN AI: {content.strip()}")

        except Exception as e:
            self.chat_history.append("EBLAN AI: я сломался, прости((")
            print("AI ошибка:", e)


class UpdateDialog2(QDialog):
    def __init__(self, cur_ver, info, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.info = info
        self.setWindowTitle("Доступно обновление")

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"<h2>Ты на: {cur_ver}</h2>"))
        layout.addWidget(QLabel(f"<h2>Новая: <b>{info['version']}</b></h2>"))
        layout.addWidget(QLabel("Обновления где в названии меняется цифра крупные\nОбновления где в названии меняется цифра после другой мелкая"))

        if info.get("force", False):
            layout.addWidget(QLabel("<font color=red><b>На тестовых ветках отказатся нельзя.</b></font>"))

        log = QTextEdit()
        log.setPlainText(info.get("changelog", "-"))
        log.setReadOnly(True)
        log.setMaximumHeight(200)
        layout.addWidget(log)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        btns = QDialogButtonBox()
        ok_btn = btns.addButton("Скачать", QDialogButtonBox.ButtonRole.AcceptRole)
        no_btn = btns.addButton("Закрыть", QDialogButtonBox.ButtonRole.RejectRole)
        if info.get("force", False):
            no_btn.setEnabled(False)
        ok_btn.clicked.connect(self.start_download)
        no_btn.clicked.connect(self.reject)

        layout.addWidget(btns)

    def start_download(self):
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.main_window.start_download_and_install(
            self.info["download_url"],
            self.info["version"],
            self.progress
        )
        self.accept()


class DevToolsDialog(QDialog):
    def __init__(self, main_window, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_window = main_window
        self.setWindowTitle("EBLANDEV Tools")
        self.setMinimumSize(900, 600)
        self.command_history = []
        self.history_index = -1

        # Dark theme stylesheet
        self.setStyleSheet("""
            QDialog {
                background: #1e1e1e;
                color: #d4d4d4;
            }
            QTabBar::tab {
                background: #2d2d30;
                color: #d4d4d4;
                padding: 8px 20px;
                border: 1px solid #3e3e42;
            }
            QTabBar::tab:selected {
                background: #0e639c;
                color: white;
            }
            QTextEdit, QListWidget, QTableWidget {
                background: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3e3e42;
                font-family: 'Courier New', monospace;
            }
            QLineEdit {
                background: #2d2d30;
                color: #d4d4d4;
                border: 1px solid #3e3e42;
                padding: 5px;
                font-family: 'Courier New', monospace;
            }
            QPushButton {
                background: #0e639c;
                color: white;
                border: 1px solid #007acc;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: #1177bb;
            }
            QComboBox {
                background: #2d2d30;
                color: #d4d4d4;
                border: 1px solid #3e3e42;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab widget for different devtools sections
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # ===== CONSOLE TAB =====
        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        console_layout.addWidget(self.console_output)

        # Input area
        input_layout = QHBoxLayout()
        self.console_input = QLineEdit()
        self.console_input.setPlaceholderText(">> Введите JavaScript код...")
        self.console_input.returnPressed.connect(self.execute_console_js)
        input_layout.addWidget(self.console_input)

        execute_btn = QPushButton("Выполнить")
        execute_btn.clicked.connect(self.execute_console_js)
        input_layout.addWidget(execute_btn)

        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(self.console_output.clear)
        input_layout.addWidget(clear_btn)

        console_layout.addLayout(input_layout)
        self.tabs.addTab(console_widget, ">_ Console")

        # ===== ELEMENTS TAB =====
        elements_widget = QWidget()
        elements_layout = QVBoxLayout(elements_widget)

        elements_layout.addWidget(QLabel("Исходный код"))
        self.dom_tree = QTextEdit()
        self.dom_tree.setReadOnly(True)
        elements_layout.addWidget(self.dom_tree)

        inspect_btn = QPushButton("Получить")
        inspect_btn.clicked.connect(self.inspect_dom)
        elements_layout.addWidget(inspect_btn)

        self.tabs.addTab(elements_widget, "Элементы")

        # ===== NETWORK TAB =====
        network_widget = QWidget()
        network_layout = QVBoxLayout(network_widget)

        network_layout.addWidget(QLabel("Сетевые запросы (последние):"))
        self.network_table = QTableWidget()
        self.network_table.setColumnCount(4)
        self.network_table.setHorizontalHeaderLabels(["Метод", "URL", "Статус", "Тип"])
        self.network_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        network_layout.addWidget(self.network_table)

        network_refresh_btn = QPushButton("Обновить Network")
        network_refresh_btn.clicked.connect(self.refresh_network_info)
        network_layout.addWidget(network_refresh_btn)

        self.tabs.addTab(network_widget, "Network")

        # ===== STORAGE TAB =====
        storage_widget = QWidget()
        storage_layout = QVBoxLayout(storage_widget)

        storage_layout.addWidget(QLabel("LocalStorage:"))
        self.local_storage_display = QTextEdit()
        self.local_storage_display.setReadOnly(True)
        storage_layout.addWidget(self.local_storage_display)

        storage_layout.addWidget(QLabel("SessionStorage:"))
        self.session_storage_display = QTextEdit()
        self.session_storage_display.setReadOnly(True)
        storage_layout.addWidget(self.session_storage_display)

        storage_refresh_btn = QPushButton("🔄 Обновить Storage")
        storage_refresh_btn.clicked.connect(self.refresh_storage)
        storage_layout.addWidget(storage_refresh_btn)

        self.tabs.addTab(storage_widget, "Storage")

        # ===== SETTINGS TAB =====
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)

        settings_layout.addWidget(QLabel("Опции DevTools:"))
        
        self.pretty_print_cb = QCheckBox("Pretty-print JSON вывод")
        self.pretty_print_cb.setChecked(True)
        settings_layout.addWidget(self.pretty_print_cb)

        self.show_timestamps_cb = QCheckBox("Показывать временные метки")
        self.show_timestamps_cb.setChecked(True)
        settings_layout.addWidget(self.show_timestamps_cb)

        self.auto_format_cb = QCheckBox("Автоматическое форматирование объектов")
        self.auto_format_cb.setChecked(True)
        settings_layout.addWidget(self.auto_format_cb)

        settings_layout.addSpacing(20)
        settings_layout.addWidget(QLabel("Полезные команды:"))
        commands_text = QTextEdit()
        commands_text.setReadOnly(True)
        commands_text.setText("""
document.title                      // название страницы
document.body.innerHTML             // HTML содержимое
window.location.href                // текущий URL
navigator.userAgent                 // user agent
localStorage.getItem('key')         // получить из localStorage
sessionStorage.getItem('key')       // получить из sessionStorage
document.querySelectorAll('*')      // все элементы
console.log('text')                 // вывести в консоль
        """.strip())
        settings_layout.addWidget(commands_text)

        settings_layout.addStretch()
        self.tabs.addTab(settings_widget, "Настройки")

        # Footer
        footer_layout = QHBoxLayout()
        footer_layout.addWidget(QLabel("EBLANDEV Tools"))
        footer_layout.addStretch()
        close_btn = QPushButton("✕ Закрыть")
        close_btn.clicked.connect(self.accept)
        footer_layout.addWidget(close_btn)
        layout.addLayout(footer_layout)

        self.print_to_console("EBLANDEV Tools запущены✅", "info")

    def print_to_console(self, message, msg_type="log"):
        timestamp = ""
        if self.show_timestamps_cb.isChecked():
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S") + " "

        color_map = {
            "info": "#0e639c",
            "error": "#f48771",
            "warning": "#dcdcaa",
            "success": "#6a9955",
            "log": "#d4d4d4"
        }
        color = color_map.get(msg_type, "#d4d4d4")
        styled_msg = f"<span style='color: {color}'>{timestamp}{message}</span>"
        self.console_output.append(styled_msg)

    def execute_console_js(self):
        js_code = self.console_input.text().strip()
        if not js_code:
            self.print_to_console("Ошибка: Введите код!", "error")
            return

        self.command_history.append(js_code)
        self.history_index = -1
        self.console_input.clear()

        current_widget = self.main_window.tabs.currentWidget()
        if not current_widget:
            self.print_to_console("Ошибка: Нет активной вкладки!", "error")
            return

        page = current_widget.page()
        if not page:
            self.print_to_console("Ошибка: Не удалось получить страницу!", "error")
            return

        self.print_to_console(f"> {js_code}", "info")
        page.runJavaScript(js_code, 0, self.handle_js_result)

    def handle_js_result(self, result):
        if result is None:
            self.print_to_console("undefined", "log")
        else:
            output = str(result)
            if self.pretty_print_cb.isChecked() and self.auto_format_cb.isChecked():
                try:
                    parsed = json.loads(output)
                    output = json.dumps(parsed, ensure_ascii=False, indent=2)
                except:
                    pass
            self.print_to_console(output, "log")

    def inspect_dom(self):
        current_widget = self.main_window.tabs.currentWidget()
        if not current_widget:
            self.dom_tree.setText("Ошибка: Нет активной вкладки!")
            return

        page = current_widget.page()
        if not page:
            self.dom_tree.setText("Ошибка: Не удалось получить страницу!")
            return

        page.runJavaScript(
            "document.documentElement.outerHTML",
            0,
            self.display_dom
        )

    def display_dom(self, html):
        if html:
            self.dom_tree.setPlainText(html[:10000])  # limit output

    def refresh_storage(self):
        current_widget = self.main_window.tabs.currentWidget()
        if not current_widget:
            self.local_storage_display.setText("Ошибка: Нет активной вкладки!")
            return

        page = current_widget.page()

        # Get localStorage
        page.runJavaScript(
            "JSON.stringify(Object.entries(localStorage))",
            0,
            lambda result: self.display_local_storage(result)
        )

        # Get sessionStorage
        page.runJavaScript(
            "JSON.stringify(Object.entries(sessionStorage))",
            0,
            lambda result: self.display_session_storage(result)
        )

    def display_local_storage(self, result):
        try:
            data = json.loads(result) if result else []
            text = "\n".join([f"{k} = {v}" for k, v in data]) if data else "(пусто)"
            self.local_storage_display.setPlainText(text)
        except:
            self.local_storage_display.setPlainText("(Ошибка при чтении)")

    def display_session_storage(self, result):
        try:
            data = json.loads(result) if result else []
            text = "\n".join([f"{k} = {v}" for k, v in data]) if data else "(пусто)"
            self.session_storage_display.setPlainText(text)
        except:
            self.session_storage_display.setPlainText("(Ошибка при чтении)")

    def refresh_network_info(self):
        self.network_table.setRowCount(0)
        self.print_to_console("Сетева�� информация обновится при перезагрузке страницы", "info")


class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("История просмотра")
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout(self)

        self.listw = QListWidget()
        layout.addWidget(self.listw)

        btn_layout = QHBoxLayout()
        open_btn = QPushButton("Открыть в браузере")
        open_btn.clicked.connect(self.open_selected)
        btn_layout.addWidget(open_btn)

        clear_btn = QPushButton("Очистить историю")
        clear_btn.clicked.connect(self.clear_history)
        btn_layout.addWidget(clear_btn)

        layout.addLayout(btn_layout)

        self.reload()

    def reload(self):
        self.listw.clear()
        for it in load_history():
            t = it.get("title") or it.get("url")
            ts = it.get("ts", "")
            self.listw.addItem(f"{t} — {it.get('url')} — {ts}")

    def open_selected(self):
        idx = self.listw.currentRow()
        if idx < 0:
            return
        items = load_history()
        url = items[idx]["url"]
        QDesktopServices.openUrl(QUrl(url))

    def clear_history(self):
        save_history([])
        self.reload()


class DownloadsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Загрузки")
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout(self)

        self.listw = QListWidget()
        layout.addWidget(self.listw)

        btn_layout = QHBoxLayout()
        open_btn = QPushButton("Открыть файл")
        open_btn.clicked.connect(self.open_file)
        btn_layout.addWidget(open_btn)

        open_folder_btn = QPushButton("Открыть папку")
        open_folder_btn.clicked.connect(self.open_folder)
        btn_layout.addWidget(open_folder_btn)

        clear_btn = QPushButton("Очистить список")
        clear_btn.clicked.connect(self.clear_list)
        btn_layout.addWidget(clear_btn)

        layout.addLayout(btn_layout)

        self.reload()

    def reload(self):
        self.listw.clear()
        for it in load_download_history():
            fn = it.get("filename")
            st = it.get("status")
            ts = it.get("ts", "")
            path = it.get("path")
            self.listw.addItem(f"{fn} — {st} — {ts} — {path}")

    def open_file(self):
        idx = self.listw.currentRow()
        if idx < 0:
            return
        items = load_download_history()
        path = items[idx].get("path")
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def open_folder(self):
        idx = self.listw.currentRow()
        if idx < 0:
            return
        items = load_download_history()
        path = items[idx].get("path")
        if path:
            folder = os.path.dirname(path)
            if os.path.exists(folder):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def clear_list(self):
        save_download_history([])
        self.reload()

EBLAN_ID_API = "https://twgood.serv00.net/id/main.php"

# If True, skip EBLAN ID prompt on startup when shortcut pressed
SKIP_EBLAN_ID = False

def get_eblan_id_path():
    base = os.path.dirname(get_settings_path())
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "eblan_id.json")


def load_eblan_id():
    path = get_eblan_id_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("eblan_id")
    except Exception:
        return None


def save_eblan_id(eblan_id: str):
    with open(get_eblan_id_path(), "w", encoding="utf-8") as f:
        json.dump({"eblan_id": eblan_id}, f)

def check_eblan_id_alive(eblan_id: str) -> bool:
    try:
        r = requests.get(
            EBLAN_ID_API,
            params={"idc": eblan_id},
            headers=EB_HTTP_HEADERS,
            timeout=5
        )
        return r.status_code == 200 and r.text.strip() == "OK"
    except Exception:
        return False


# ----------------- History & Downloads -----------------
def get_history_path():
    base = os.path.dirname(get_settings_path())
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "history.json")


def load_history():
    path = get_history_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(items):
    try:
        with open(get_history_path(), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_history_entry(url, title):
    try:
        items = load_history()
        items.insert(0, {
            "url": url,
            "title": title,
            "ts": datetime.utcnow().isoformat()
        })
        # keep recent 500
        items = items[:500]
        save_history(items)
    except Exception:
        pass


def get_downloads_path(settings=None):
    # default to user Downloads
    default = os.path.join(os.path.expanduser("~"), "Downloads")
    try:
        settings_path = get_settings_path()
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("downloads_folder", default)
    except Exception:
        pass
    return default


def get_download_history_path():
    base = os.path.dirname(get_settings_path())
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "downloads.json")


def load_download_history():
    path = get_download_history_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_download_history(items):
    try:
        with open(get_download_history_path(), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_download_entry(url, filename, path, status="completed"):
    try:
        items = load_download_history()
        items.insert(0, {
            "url": url,
            "filename": filename,
            "path": path,
            "status": status,
            "ts": datetime.utcnow().isoformat()
        })
        items = items[:500]
        save_download_history(items)
    except Exception:
        pass


# --------- Extensions (.eblp) Support ---------
def get_extensions_path():
    base = os.path.dirname(get_settings_path())
    ext_path = os.path.join(base, "extensions")
    os.makedirs(ext_path, exist_ok=True)
    return ext_path


def parse_eblp_file(eblp_path):
    """Parse .eblp extension file and extract JS, Meta, CSS sections"""
    try:
        with open(eblp_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        result = {
            'meta': {},
            'js': '',
            'css': ''
        }
        
        sections = content.split('---')
        
        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue
            
            # First section = JS (if not labeled)
            if i == 0 and not section.startswith('Meta') and not section.startswith('CSS'):
                result['js'] = section
            # Check for Meta section
            elif section.startswith('Meta'):
                meta_content = section.replace('Meta', '', 1).strip()
                for line in meta_content.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        result['meta'][key.strip()] = value.strip()
            # Check for CSS section
            elif section.startswith('CSS'):
                result['css'] = section.replace('CSS', '', 1).strip()
            # Other sections are JS
            else:
                result['js'] += '\n' + section
        
        return result
    except Exception as e:
        print(f"Ошибка парсинга расширения {eblp_path}: {e}")
        return None


def load_extensions(main_window):
    """Load all .eblp extensions from extensions folder"""
    ext_dir = get_extensions_path()
    extensions = []
    
    for filename in os.listdir(ext_dir):
        if filename.endswith('.eblp'):
            ext_path = os.path.join(ext_dir, filename)
            parsed = parse_eblp_file(ext_path)
            if parsed and parsed['meta']:
                extensions.append({
                    'filename': filename,
                    'path': ext_path,
                    'meta': parsed['meta'],
                    'js': parsed['js'],
                    'css': parsed['css'],
                    'enabled': True
                })
    
    return extensions


def inject_extension_js(browser_page, ext_js):
    """Inject extension JavaScript into page"""
    if ext_js:
        browser_page.runJavaScript(ext_js)


def inject_extension_css(browser_page, ext_css):
    """Inject extension CSS into page"""
    if ext_css:
        js_code = f"""
        const style = document.createElement('style');
        style.textContent = `{ext_css}`;
        document.head.appendChild(style);
        """
        browser_page.runJavaScript(js_code)


class _ChoiceCard(QFrame):
    """Кликабельная карточка-выбор в тёмной теме EBLAN (accent cyan)."""
    def __init__(self, title, subtitle, accent="#00ddff", on_click=None, parent=None):
        super().__init__(parent)
        self.setObjectName("ChoiceCard")
        self._on_click = on_click
        self._accent = accent
        self._selected = False
        self._title_text = title
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)
        self._t = QLabel(title)
        self._t.setObjectName("ChoiceTitle")
        self._s = QLabel(subtitle)
        self._s.setObjectName("ChoiceSubtitle")
        self._s.setWordWrap(True)
        lay.addWidget(self._t)
        lay.addWidget(self._s)
        self._apply_style()

    def _apply_style(self):
        if self._selected:
            border = self._accent
            bg = "#2b4566"
            title_color = self._accent
        else:
            border = "#3a3944"
            bg = "#23222b"
            title_color = "#fbfbfe"
        self.setStyleSheet(f"""
            QFrame#ChoiceCard {{
                background: {bg};
                border: 1px solid {border};
                border-left: 3px solid {border};
                border-radius: 4px;
            }}
            QFrame#ChoiceCard:hover {{
                border: 1px solid {self._accent};
                border-left: 3px solid {self._accent};
            }}
            QLabel#ChoiceTitle {{
                color: {title_color};
                font-size: 14px;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#ChoiceSubtitle {{
                color: #b1b1b3;
                font-size: 12px;
                background: transparent;
            }}
        """)

    def setSelected(self, val: bool):
        self._selected = bool(val)
        self._apply_style()

    def isSelected(self):
        return self._selected

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and self._on_click:
            try:
                self._on_click()
            except Exception:
                pass
        super().mousePressEvent(ev)


class OnboardingWizard(QDialog):
    """Визард первичной настройки в том же стиле, что SettingsDialog.
    Тёмный фон #1c1b22, cyan-акцент #00ddff, сайдбар со шагами слева."""

    # Индексы шагов (совпадают с индексами в _steps_meta)
    STEP_INTRO = 0
    STEP_EBLANID = 1
    STEP_PATRIOT = 2
    STEP_AI = 3
    STEP_VLESS = 4
    STEP_FINISH = 5

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("EBLAN Browser — Первый запуск")
        self.setMinimumSize(900, 600)
        self.setModal(True)

        self._result = {
            "patriot": True,
            "enable_ai": True,
            "ai_server": getattr(main_window, "ai_server", "https://api.mistral.ai/v1/chat/completions"),
            "ai_key":    getattr(main_window, "ai_key", ""),
            "ai_model":  getattr(main_window, "ai_model", "mistral-large-2512"),
            "enable_vless": False,
            "gamer_mode": False,
            "imported_eblanid": False,  # True если пользователь успешно применил ключ
        }

        self._steps_meta = [
            ("Начало", "Intro"),
            ("EBLAN ID", "Import"),
            ("Интернет", "Patriot"),
            ("EBLAN AI", "AI"),
            ("VLESS VPN", "VLESS"),
            ("Готово", "Finish"),
        ]

        # ---------- Разметка: Sidebar | Content | Footer ----------
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # === SIDEBAR ===
        self.sidebar = QWidget()
        self.sidebar.setObjectName("ffSidebar")
        self.sidebar.setFixedWidth(220)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(0, 16, 0, 0)
        side.setSpacing(0)

        brand = QLabel("Первый запуск")
        brand.setObjectName("ffBrand")
        side.addWidget(brand)

        self.nav = QListWidget()
        self.nav.setObjectName("ffNav")
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.nav.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Клик по шагу — переход (но назад можно только на пройденный)
        self.nav.currentRowChanged.connect(self._nav_clicked)
        for title, _ in self._steps_meta:
            it = QListWidgetItem(title)
            self.nav.addItem(it)
        side.addWidget(self.nav, 1)

        ver = QLabel(f"EBLAN Browser\n{getattr(main_window, 'version', 'setup')}")
        ver.setObjectName("ffVersion")
        side.addWidget(ver)

        root.addWidget(self.sidebar)

        # === CONTENT + FOOTER ===
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)

        self._content_host = QWidget()
        self._content_host.setObjectName("ffContent")
        content_lay = QVBoxLayout(self._content_host)
        content_lay.setContentsMargins(24, 20, 24, 16)
        content_lay.setSpacing(14)

        # Заголовок страницы (как в SettingsDialog)
        self._page_title = QLabel("")
        self._page_title.setObjectName("ffPageTitle")
        content_lay.addWidget(self._page_title)

        # Стек страниц
        self._stack = QStackedWidget()
        content_lay.addWidget(self._stack, 1)

        self._stack.addWidget(self._build_step_intro())
        self._stack.addWidget(self._build_step_eblanid())
        self._stack.addWidget(self._build_step_patriot())
        self._stack.addWidget(self._build_step_ai())
        self._stack.addWidget(self._build_step_vless())
        self._stack.addWidget(self._build_step_finish())

        right_col.addWidget(self._content_host, 1)

        # Footer как в SettingsDialog
        footer = QFrame()
        footer.setObjectName("ffFooter")
        nav_lay = QHBoxLayout(footer)
        nav_lay.setContentsMargins(16, 10, 16, 10)

        self._back_btn = QPushButton("Назад")
        self._back_btn.clicked.connect(self._go_back)
        nav_lay.addWidget(self._back_btn)

        nav_lay.addStretch()

        self._skip_btn = QPushButton("Пропустить")
        self._skip_btn.clicked.connect(self._skip_all)
        nav_lay.addWidget(self._skip_btn)

        self._next_btn = QPushButton("Далее")
        self._next_btn.setObjectName("ffPrimary")
        self._next_btn.setDefault(True)
        self._next_btn.clicked.connect(self._go_next)
        nav_lay.addWidget(self._next_btn)

        right_col.addWidget(footer)

        right_host = QWidget()
        right_host.setLayout(right_col)
        root.addWidget(right_host, 1)

        self._apply_stylesheet()
        self.nav.setCurrentRow(0)
        self._sync_to_step(0)

    def _apply_stylesheet(self):
        # Берём тот же QSS, что SettingsDialog (dark Firefox Proton),
        # + добавляем стили для footer/content, которые в исходнике на QDialog завязаны.
        base = SettingsDialog._build_qss(True)
        extra = """
            QDialog#OnbDialog { background: #1c1b22; }
            QFrame#ffFooter {
                background: #2b2a33;
                border-top: 1px solid #3a3944;
            }
            QWidget#ffContent, QDialog {
                background: #1c1b22;
            }
        """
        self.setObjectName("OnbDialog")
        self.setStyleSheet(base + extra)

    # --------- навигация ---------
    def _sync_to_step(self, idx):
        """Переключает стек, заголовок и состояние кнопок."""
        idx = max(0, min(idx, self._stack.count() - 1))
        self._stack.setCurrentIndex(idx)
        title, _ = self._steps_meta[idx]
        # Удобный заголовок страницы — конкретный для каждого шага
        page_titles = {
            self.STEP_INTRO:    "Добро пожаловать",
            self.STEP_EBLANID:  "EBLAN ID - перенос настроек",
            self.STEP_PATRIOT:  "Вопрос на иноагенета",
            self.STEP_AI:       "EBLAN AI",
            self.STEP_VLESS:    "Вэпэнэс и EBLAN SoftBoost",
            self.STEP_FINISH:   "Всё готово",
        }
        self._page_title.setText(page_titles.get(idx, title))

        last = idx == self.STEP_FINISH
        self._back_btn.setEnabled(idx > 0)
        self._skip_btn.setVisible(not last)
        self._next_btn.setText("Готово" if last else "Далее")

        # Обновим выделение в nav без рекурсии
        if self.nav.currentRow() != idx:
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(idx)
            self.nav.blockSignals(False)

        if last:
            self._refresh_summary()

    def _nav_clicked(self, row):
        # Назад можно всегда, вперёд — только на следующий шаг (чтобы не скипать валидацию AI)
        current = self._stack.currentIndex()
        if row == current:
            return
        if row <= current or row == current + 1:
            # Перед выходом с AI-шага соберём поля
            if current == self.STEP_AI and self._result.get("enable_ai"):
                self._collect_ai_fields()
            self._sync_to_step(row)
        else:
            # Откатим выделение
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(current)
            self.nav.blockSignals(False)

    def _go_back(self):
        idx = self._stack.currentIndex()
        if idx > 0:
            self._sync_to_step(idx - 1)

    def _skip_all(self):
        self.accept()

    def _collect_ai_fields(self):
        try:
            self._result["ai_server"] = self._ai_server_in.text().strip() or self._result["ai_server"]
            self._result["ai_key"] = self._ai_key_in.text().strip()
            self._result["ai_model"] = self._ai_model_in.text().strip() or self._result["ai_model"]
        except Exception:
            pass

    # --------- утилиты построения ---------
    def _step_page(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        return w, lay

    def _card(self, parent_layout):
        """Секционная карточка в стиле SettingsDialog.QFrame#ffCard."""
        card = QFrame()
        card.setObjectName("ffCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(8)
        parent_layout.addWidget(card)
        return box

    def _paragraph(self, text):
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #b1b1b3; font-size: 12px; background: transparent;")
        return lbl

    def _field_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #b1b1b3; font-size: 11px; background: transparent;")
        return lbl

    # --------- шаги ---------
    def _build_step_intro(self):
        w, lay = self._step_page()
        box = self._card(lay)

        heading = QLabel("EBLAN Browser")
        heading.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #fbfbfe; background: transparent;"
        )
        box.addWidget(heading)

        tagline = QLabel("ассестент по настройке/!!111")
        tagline.setStyleSheet("color: #00ddff; font-size: 13px; background: transparent;")
        box.addWidget(tagline)

        box.addSpacing(4)
        box.addWidget(self._paragraph(
            "Пройдём несколько коротких шагов, чтобы настроить браузер под вас. "
            "Все параметры можно изменить потом в настройках. "
            "Слева — список шагов, справа — содержимое текущего шага."
        ))

        features_box = self._card(lay)
        ftitle = QLabel("Что будет в этой настройке")
        ftitle.setStyleSheet("font-weight: 700; color: #fbfbfe; background: transparent;")
        features_box.addWidget(ftitle)
        for line in (
            "• Импорт EBLAN ID с другого устройства",
            "• Фильтр RU/SU/BY или весь интернет",
            "• Встроенный EBLAN AI в адресной строке",
            "• Настройка VLESS VPN и геймер-режима",
        ):
            l = QLabel(line)
            l.setStyleSheet("color: #fbfbfe; font-size: 12px; background: transparent;")
            features_box.addWidget(l)

        lay.addStretch()
        return w

    def _build_step_eblanid(self):
        w, lay = self._step_page()

        intro_box = self._card(lay)
        hint = QLabel(
            "EBLAN Browser умеет переносить настройки между устройствами. "
            "Войдите в учётную запись EBLAN ID (по email + коду) — и настройки "
            "восстановятся автоматически. Либо, если у вас есть EBLAN ID ключ, "
            "вставьте его вручную."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #fbfbfe; font-size: 12px; background: transparent;")
        intro_box.addWidget(hint)

        choice_box = self._card(lay)
        q = QLabel("Как переносим настройки?")
        q.setStyleSheet("font-weight: 700; color: #fbfbfe; background: transparent;")
        choice_box.addWidget(q)
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self._card_account = _ChoiceCard(
            "Да, у меня учётная запись",
            "Войду по email и коду — настройки подтянутся с сервера.",
            accent="#00ddff",
            on_click=lambda: self._select_eblanid_mode("account"),
        )
        self._card_has_key = _ChoiceCard(
            "Нет, у меня ключ",
            "Вставлю EBLAN ID ключ и восстановлю настройки вручную.",
            accent="#00ddff",
            on_click=lambda: self._select_eblanid_mode("key"),
        )
        cards_row.addWidget(self._card_account)
        cards_row.addWidget(self._card_has_key)
        choice_box.addLayout(cards_row)

        # Ссылка-переход для тех, у кого нет ни аккаунта, ни ключа.
        link = QLabel(
            "<a href='#skip' style='color:#00ddff;'>"
            "Нет, у меня нету учётной записи и ключа</a>"
        )
        link.setStyleSheet("background: transparent; font-size: 12px;")
        link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        link.linkActivated.connect(lambda _=None: self._go_next())
        choice_box.addWidget(link)

        # --- Форма входа по аккаунту (email + код), скрыта по умолчанию ---
        self._account_form = self._build_eblanid_account_form()
        lay.addWidget(self._account_form)

        # --- Форма импорта ключа, скрыта по умолчанию ---
        self._import_form = self._build_eblanid_key_form()
        lay.addWidget(self._import_form)

        self._select_eblanid_mode(None)
        lay.addStretch()
        return w

    def _build_eblanid_account_form(self):
        """Встроенная форма входа EBLAN ID (email + 6-значный код)."""
        frame = QFrame()
        frame.setObjectName("ffCard")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(16, 14, 16, 14)
        fl.setSpacing(8)

        fl.addWidget(self._field_label("Email учётной записи"))
        self._acc_email = QLineEdit()
        self._acc_email.setPlaceholderText("ваша@почта.com")
        fl.addWidget(self._acc_email)

        send_row = QHBoxLayout()
        self._acc_send_btn = QPushButton("Отправить код")
        self._acc_send_btn.clicked.connect(self._acc_send_code)
        send_row.addWidget(self._acc_send_btn)
        send_row.addStretch()
        fl.addLayout(send_row)

        # Блок ввода кода — появляется сразу после нажатия «Отправить код».
        self._acc_code_widget = QWidget()
        cw = QVBoxLayout(self._acc_code_widget)
        cw.setContentsMargins(0, 4, 0, 0)
        cw.setSpacing(8)
        cw.addWidget(self._field_label("Код из письма"))
        self._acc_code = QLineEdit()
        self._acc_code.setPlaceholderText("123456")
        self._acc_code.setMaxLength(6)
        cw.addWidget(self._acc_code)
        self._acc_login_btn = QPushButton("Войти")
        self._acc_login_btn.setObjectName("ffPrimary")
        self._acc_login_btn.clicked.connect(self._acc_complete_login)
        cw.addWidget(self._acc_login_btn)
        self._acc_code_widget.setVisible(False)
        fl.addWidget(self._acc_code_widget)

        self._acc_status = QLabel("")
        self._acc_status.setWordWrap(True)
        self._acc_status.setStyleSheet("background: transparent; font-size: 12px;")
        fl.addWidget(self._acc_status)

        self._acc_pending_email = ""
        return frame

    def _build_eblanid_key_form(self):
        """Встроенная форма импорта EBLAN ID ключа (вынесена из шага)."""
        frame = QFrame()
        frame.setObjectName("ffCard")
        form_lay = QVBoxLayout(frame)
        form_lay.setContentsMargins(16, 14, 16, 14)
        form_lay.setSpacing(8)

        form_lay.addWidget(self._field_label("Ваш EBLAN ID"))
        self._eblanid_input = QTextEdit()
        self._eblanid_input.setPlaceholderText("Вставьте ключ вида ebl_…")
        self._eblanid_input.setMaximumHeight(86)
        form_lay.addWidget(self._eblanid_input)

        form_row = QHBoxLayout()
        paste_btn = QPushButton("Вставить из буфера")
        def do_paste():
            t = QApplication.clipboard().text() or ""
            self._eblanid_input.setPlainText(t.strip())
        paste_btn.clicked.connect(do_paste)
        form_row.addWidget(paste_btn)

        file_btn = QPushButton("Открыть файл…")
        def do_file():
            path, _ = QFileDialog.getOpenFileName(
                self, "Открыть EBLAN ID", "",
                "Текстовые файлы (*.txt);;Все файлы (*.*)"
            )
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._eblanid_input.setPlainText(f.read().strip())
            except Exception as e:
                QMessageBox.warning(self, "EBLAN ID", f"Не удалось открыть: {e}")
        file_btn.clicked.connect(do_file)
        form_row.addWidget(file_btn)

        form_row.addStretch()

        apply_btn = QPushButton("Применить ключ")
        apply_btn.setObjectName("ffPrimary")
        apply_btn.clicked.connect(self._acc_apply_key)
        form_row.addWidget(apply_btn)
        form_lay.addLayout(form_row)

        self._import_status = QLabel("")
        self._import_status.setWordWrap(True)
        self._import_status.setStyleSheet("background: transparent;")
        form_lay.addWidget(self._import_status)
        return frame

    def _select_eblanid_mode(self, mode):
        """mode ∈ {'account','key',None}. Подсвечивает карточку и показывает форму."""
        self._eblanid_mode = mode
        self._card_account.setSelected(mode == "account")
        self._card_has_key.setSelected(mode == "key")
        self._account_form.setVisible(mode == "account")
        self._import_form.setVisible(mode == "key")

    def _acc_send_code(self):
        email = (self._acc_email.text() or "").strip()
        if not email or "@" not in email:
            self._acc_set_status("Введите корректный email", error=True)
            return
        self._acc_pending_email = email
        api = getattr(self.main_window, "update_api_base", "") or DEFAULT_BAN_API_BASE
        # Поле кода показываем сразу — ответ сервера может задержаться.
        self._acc_code_widget.setVisible(True)
        self._acc_code.setFocus()
        self._acc_send_btn.setText("Отправить заново")
        self._acc_set_status("Отправляю код — проверьте почту…")

        def _go():
            resp = eblan_auth_start(api, email)
            QtCore.QTimer.singleShot(0, lambda: self._acc_on_code_sent(resp))

        threading.Thread(target=_go, daemon=True).start()

    def _acc_on_code_sent(self, resp: dict):
        if resp.get("ok"):
            self._acc_set_status("Код отправлен! Введите его из письма.")
            return
        err = resp.get("error", "unknown")
        if err == "too_many_requests":
            self._acc_set_status("Код уже отправляли — введите его из письма.")
        elif err == "ip_limit_reached":
            self._acc_set_status("С этого IP уже есть аккаунт.", error=True)
        elif err == "invalid_email":
            self._acc_set_status("Некорректный email.", error=True)
        elif err == "mail_failed":
            self._acc_set_status("Не удалось отправить письмо.", error=True)
        else:
            self._acc_set_status(f"Ошибка: {err}", error=True)

    def _acc_complete_login(self):
        code = (self._acc_code.text() or "").strip()
        if len(code) != 6 or not code.isdigit():
            self._acc_set_status("Код должен быть 6 цифр.", error=True)
            return
        api = getattr(self.main_window, "update_api_base", "") or DEFAULT_BAN_API_BASE
        self._acc_login_btn.setEnabled(False)
        self._acc_set_status("Проверяю код…")

        def _go():
            resp = eblan_auth_complete(api, self._acc_pending_email, code)
            QtCore.QTimer.singleShot(0, lambda: self._acc_on_login(resp))

        threading.Thread(target=_go, daemon=True).start()

    def _acc_on_login(self, resp: dict):
        self._acc_login_btn.setEnabled(True)
        if not resp.get("ok"):
            err = resp.get("error", "unknown")
            if err == "invalid_code":
                err = "неверный код"
            elif err == "too_many_attempts":
                err = "много попыток — запросите код заново"
            self._acc_set_status(f"Ошибка: {err}", error=True)
            return

        mw = self.main_window
        token = resp.get("token")
        account = resp.get("account") or {}
        email = account.get("email", "?")
        if mw is not None:
            mw.eblan_token = token
            mw.eblan_account = account
            try:
                mw.save_settings()
            except Exception:
                pass
            # Синхронизация: тянем ключ с сервера либо выгружаем свой.
            try:
                ok, action, _msg = mw.sync_eblan_id_after_login(silent=True)
            except Exception:
                ok, action = False, "noop"
            self._result["imported_eblanid"] = bool(ok and action == "pulled")
            self._result["enable_ai"] = bool(getattr(mw, "enable_eblan_ai", True))
            self._result["gamer_mode"] = bool(getattr(mw, "gamer_mode", False))

        self._acc_set_status(f"✓ Вход как {email}. Настройки синхронизированы.")
        QTimer.singleShot(400, lambda: self._sync_to_step(self.STEP_FINISH))

    def _acc_apply_key(self):
        mw = self.main_window
        if mw is None:
            return
        key = self._eblanid_input.toPlainText().strip()
        if not key:
            QMessageBox.information(self, "EBLAN ID", "Сначала вставьте ключ.")
            return
        try:
            ok, msg = mw.import_eblanid(key)
        except Exception as e:
            ok, msg = False, str(e)
        if ok:
            self._result["imported_eblanid"] = True
            self._result["enable_ai"] = bool(getattr(mw, "enable_eblan_ai", True))
            self._result["gamer_mode"] = bool(getattr(mw, "gamer_mode", False))
            self._import_status.setText("Ключ применён — настройки восстановлены.")
            self._import_status.setStyleSheet(
                "color: #30e60b; font-size: 12px; background: transparent;"
            )
            QTimer.singleShot(300, lambda: self._sync_to_step(self.STEP_FINISH))
        else:
            self._import_status.setText(f"Не удалось применить: {msg}")
            self._import_status.setStyleSheet(
                "color: #ff4f5e; font-size: 12px; background: transparent;"
            )

    def _acc_set_status(self, text: str, error: bool = False):
        self._acc_status.setText(text or "")
        color = "#ff4f5e" if error else "#30e60b"
        self._acc_status.setStyleSheet(
            f"color: {color}; font-size: 12px; background: transparent;"
        )

    def _build_step_patriot(self):
        w, lay = self._step_page()

        intro = self._card(lay)
        intro.addWidget(self._paragraph(
            "Вопрос на иноагента: хотите ли вы ограничить браузер только рунетом и союзными зонами?"
            "Если нет то вы будете признаны иноагентом и получите по полной программе от всех органов, включая Роскомнадзор, ФСБ и ОМОНа."
        ))

        choice = self._card(lay)
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self._card_patriot = _ChoiceCard(
            "Только RU / SU / BY",
            "Рунет и союзные зоны. Остальное не нужно, НАШЕ лучше.",
            accent="#00ddff",
            on_click=lambda: self._select_patriot(True),
        )
        self._card_worldwide = _ChoiceCard(
            "Весь интернет",
            "Иноагентский режим. Риск получить по полной от всех органов, включая Роскомнадзор, ФСБ и ОМОНа.",
            accent="#00ddff",
            on_click=lambda: self._select_patriot(False),
        )
        cards_row.addWidget(self._card_patriot)
        cards_row.addWidget(self._card_worldwide)
        choice.addLayout(cards_row)

        self._select_patriot(True)
        lay.addStretch()
        return w

    def _select_patriot(self, val):
        self._result["patriot"] = bool(val)
        self._card_patriot.setSelected(val)
        self._card_worldwide.setSelected(not val)

    def _build_step_ai(self):
        w, lay = self._step_page()

        intro = self._card(lay)
        intro.addWidget(self._paragraph(
            "Включить ии помойщника EBLAN AI — "
            "получите ответ. Включение по желанию."
        ))
        choice_row = QHBoxLayout()
        choice_row.setSpacing(10)
        self._card_ai_on = _ChoiceCard(
            "Включить",
            "Рекомендуется. Выключить можно в настройках в любой момент.",
            accent="#00ddff",
            on_click=lambda: self._select_ai(True),
        )
        self._card_ai_off = _ChoiceCard(
            "Не сейчас",
            "Браузер без AI-ассистента.",
            accent="#00ddff",
            on_click=lambda: self._select_ai(False),
        )
        choice_row.addWidget(self._card_ai_on)
        choice_row.addWidget(self._card_ai_off)
        intro.addLayout(choice_row)

        # Форма конфига в отдельной карточке
        self._ai_form = QFrame()
        self._ai_form.setObjectName("ffCard")
        form = QGridLayout(self._ai_form)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.addWidget(self._field_label("API URL"), 0, 0)
        self._ai_server_in = QLineEdit(self._result["ai_server"])
        form.addWidget(self._ai_server_in, 0, 1)
        form.addWidget(self._field_label("Модель"), 0, 2)
        self._ai_model_in = QLineEdit(self._result["ai_model"])
        form.addWidget(self._ai_model_in, 0, 3)
        form.addWidget(self._field_label("API ключ"), 1, 0)
        self._ai_key_in = QLineEdit(self._result["ai_key"])
        self._ai_key_in.setEchoMode(QLineEdit.EchoMode.Password)
        form.addWidget(self._ai_key_in, 1, 1, 1, 3)
        lay.addWidget(self._ai_form)

        self._select_ai(True)
        lay.addStretch()
        return w

    def _select_ai(self, val):
        self._result["enable_ai"] = bool(val)
        self._card_ai_on.setSelected(val)
        self._card_ai_off.setSelected(not val)
        self._ai_form.setVisible(val)

    def _build_step_vless(self):
        w, lay = self._step_page()

        intro = self._card(lay)
        intro.addWidget(self._paragraph(
            "Иноагентский пункт номер два: хотите ли вы настроить встроенный VLESS VPN? "
            "Вы будете нарушать законодательство РФ, и подвергать риском устройство"
        ))
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)
        self._card_vpn_on = _ChoiceCard(
            "Перейти к настройке VPN",
            "После финиша откроется раздел VLESS VPN.",
            accent="#00ddff",
            on_click=lambda: self._select_vpn(True),
        )
        self._card_vpn_off = _ChoiceCard(
            "НЕТ Я РУZZКИЙ",
            "МНЕ НАХУЙ НЕНУЖОН ЭТОТ ВАШ ВЭПЭНЭС, Я ХОЧУ ЧТОБЫ МЕНЯ НЕ ПРИЗНАЛИ ИНОАГЕНТОМ И НЕ НАЕБАЛИ ОТ ВСЕХ ОРГАНОВ, ВКЛЮЧАЯ РОСКОМНАДЗОР, ФСБ И ОМОНа.",
            accent="#00ddff",
            on_click=lambda: self._select_vpn(False),
        )
        cards_row.addWidget(self._card_vpn_on)
        cards_row.addWidget(self._card_vpn_off)
        intro.addLayout(cards_row)

        extras = self._card(lay)
        self._gamer_check = QCheckBox("Включить Eblan SoftBoost")
        self._gamer_check.setChecked(True)
        self._gamer_check.stateChanged.connect(
            lambda s: self._result.__setitem__("gamer_mode", s == Qt.CheckState.Checked.value)
        )
        extras.addWidget(self._gamer_check)

        self._select_vpn(False)
        lay.addStretch()
        return w

    def _select_vpn(self, val):
        self._result["enable_vless"] = bool(val)
        self._card_vpn_on.setSelected(val)
        self._card_vpn_off.setSelected(not val)

    def _build_step_finish(self):
        w, lay = self._step_page()

        hero_card = self._card(lay)
        title = QLabel("Всё готово")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #fbfbfe; background: transparent;"
        )
        hero_card.addWidget(title)
        sub = QLabel("Нажмите «Готово», чтобы закрыть мастер.")
        sub.setStyleSheet("color: #00ddff; font-size: 12px; background: transparent;")
        hero_card.addWidget(sub)

        summary_card = self._card(lay)
        head = QLabel("Сводка")
        head.setStyleSheet("font-weight: 700; color: #fbfbfe; background: transparent;")
        summary_card.addWidget(head)
        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet(
            "color: #fbfbfe; font-size: 12px; background: transparent;"
        )
        summary_card.addWidget(self._summary_label)
        tip = QLabel("Любой пункт можно изменить в Настройках.")
        tip.setStyleSheet("color: #b1b1b3; font-size: 11px; background: transparent;")
        summary_card.addWidget(tip)

        lay.addStretch()
        return w

    def _refresh_summary(self):
        r = self._result
        lines = []
        if r.get("imported_eblanid"):
            lines.append("✓ EBLAN ID применён — настройки восстановлены с другого устройства")
        lines.append("• Интернет: " + ("только RU / SU / BY" if r["patriot"] else "без фильтра"))
        lines.append("• EBLAN AI: " + ("включён" if r["enable_ai"] else "выключен"))
        lines.append("• VLESS VPN: " + ("откроем настройки" if r["enable_vless"] else "настроить позже"))
        if r.get("gamer_mode"):
            lines.append("• Геймер-режим: включён")
        try:
            self._summary_label.setText("\n".join(lines))
        except Exception:
            pass

    def _go_next(self):
        idx = self._stack.currentIndex()
        if idx == self.STEP_AI and self._result.get("enable_ai"):
            self._collect_ai_fields()
        if idx >= self._stack.count() - 1:
            self.accept()
            return
        self._sync_to_step(idx + 1)

    def get_result(self):
        return dict(self._result)


# ============================================================
#   Магазин «Еблан Кеш» — разблокировка функций за валюту.
# ============================================================
class ShopDialog(QDialog):
    def __init__(self, main_window, *args, **kwargs):
        super().__init__(main_window, *args, **kwargs)
        self.mw = main_window
        self.setWindowTitle("🛒 Магазин EBLAN — Еблан Кеш")
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)

        header = QLabel("Магазин функций")
        f = header.font(); f.setPointSize(16); f.setBold(True); header.setFont(f)
        root.addWidget(header)

        self.balance_label = QLabel()
        self.balance_label.setStyleSheet("font-weight: 800; color: #c98a00; padding: 4px 0;")
        root.addWidget(self.balance_label)

        hint = QLabel("Зарабатывай Еблан Кеш действиями в браузере и открывай функции тут.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        root.addWidget(hint)

        if is_eblan_day():
            sale = QLabel("🎉 ДЕНЬ ЕБЛАНОВ: скидка −67% на всё! 🥳")
            sale.setStyleSheet("color: #e0245e; font-weight: 800; padding: 4px 0;")
            root.addWidget(sale)

        root.addSpacing(8)

        self._rows = {}
        for fid, (name, base_price, desc) in EBLAN_SHOP.items():
            price = self.mw.shop_price(fid)
            row = QFrame()
            row.setFrameShape(QFrame.Shape.StyledPanel)
            rl = QHBoxLayout(row)

            info = QVBoxLayout()
            if price != base_price:
                title = QLabel(f"{name} — {price} Еблан Кеш  (было {base_price})")
            else:
                title = QLabel(f"{name} — {price} Еблан Кеш")
            tf = title.font(); tf.setBold(True); title.setFont(tf)
            info.addWidget(title)
            d = QLabel(desc); d.setWordWrap(True); d.setStyleSheet("color: #999;")
            info.addWidget(d)
            rl.addLayout(info, 1)

            btn = QPushButton()
            btn.clicked.connect(lambda _=False, fid=fid: self._buy(fid))
            rl.addWidget(btn)

            root.addWidget(row)
            self._rows[fid] = btn

        root.addStretch(1)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn)

        self._refresh()

    def _refresh(self):
        self.balance_label.setText(f"💰 Баланс: {int(self.mw.eblan_cash)} Еблан Кеш")
        for fid, btn in self._rows.items():
            price = self.mw.shop_price(fid)
            if self.mw.is_unlocked(fid):
                btn.setText("✅ Куплено")
                btn.setEnabled(False)
            elif int(self.mw.eblan_cash) < price:
                btn.setText(f"Купить ({price})")
                btn.setEnabled(False)
            else:
                btn.setText(f"Купить ({price})")
                btn.setEnabled(True)

    def _buy(self, fid):
        name = EBLAN_SHOP[fid][0]
        price = self.mw.shop_price(fid)
        if self.mw.is_unlocked(fid):
            return
        if not self.mw.spend_cash(price):
            QMessageBox.warning(self, "Магазин", "Не хватает Еблан Кеш. Поброди ещё по сайтам.")
            return
        self.mw.unlocked_features.append(fid)
        self.mw.save_settings()
        # AI-кнопка зависит от покупки — обновим доступность.
        if fid == "ai":
            try:
                self.mw.enable_eblan_ai = True
                self.mw.ai_action.setEnabled(True)
            except Exception:
                pass
        QMessageBox.information(self, "Магазин", f"«{name}» разблокирована! 🎉")
        self._refresh()


# ============================================================
#   Tonkeeper 2 (не скам) — ШУТОЧНАЯ анти-фишинг пародия.
#
#   ВАЖНО / БЕЗОПАСНОСТЬ: введённые «24 слова» НИКУДА не уходят —
#   ни в сеть, ни в лог, ни в Discord, ни на диск. Они живут только
#   в локальных переменных этого диалога и сразу выбрасываются.
#   Смысл фичи — наказать того, кто реально ввёл сид-фразу: показать
#   фейковый баланс и влепить локальный бан. Это троллинг/урок «никому
#   не диктуй свои 24 слова», а не сбор кошельков.
# ============================================================
class TonkeeperDialog(QDialog):
    def __init__(self, main_window, *args, **kwargs):
        super().__init__(main_window, *args, **kwargs)
        self.mw = main_window
        self.setWindowTitle("Tonkeeper 2 (не скам)")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)

        header = QLabel("Tonkeeper 2 — подключение кошелька")
        f = header.font(); f.setPointSize(15); f.setBold(True); header.setFont(f)
        root.addWidget(header)

        sub = QLabel("Введи свою секретную фразу из 24 слов, чтобы увидеть баланс.\n"
                     "Это 100% не скам, мамой клянусь 🤝")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #888;")
        root.addWidget(sub)

        grid = QGridLayout()
        self._fields = []
        for i in range(24):
            row = i % 12
            col = (i // 12) * 2
            grid.addWidget(QLabel(f"{i + 1}."), row, col)
            edit = QLineEdit()
            edit.setPlaceholderText(f"слово {i + 1}")
            grid.addWidget(edit, row, col + 1)
            self._fields.append(edit)
        root.addLayout(grid)

        btns = QHBoxLayout()
        connect_btn = QPushButton("Подключить кошелёк")
        connect_btn.clicked.connect(self._connect)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(cancel_btn)
        btns.addWidget(connect_btn)
        root.addLayout(btns)

    def _connect(self):
        # Считаем только ФАКТ заполнения — содержимое слов нам не нужно
        # и никуда не передаётся.
        filled = sum(1 for e in self._fields if e.text().strip())
        if filled < 24:
            QMessageBox.warning(
                self, "Tonkeeper 2",
                f"Заполнено {filled}/24. Введи все 24 слова, иначе кошелёк не подключить.",
            )
            return

        # Немедленно очищаем поля — слова больше нигде не живут.
        for e in self._fields:
            e.clear()

        # Фейковый «скан блокчейна» и рандомный баланс.
        ton = round(random.uniform(0.00000001, 0.00009999), 8)
        usd = round(ton * random.uniform(2.0, 6.0), 6)
        QMessageBox.information(
            self, "Сканируем блокчейн…",
            "Подключаемся к ноде TON…\nПроверяем баланс…\nГенерируем отчёт…",
        )
        QMessageBox.information(
            self, "Баланс кошелька",
            f"Найден баланс:\n\n{ton} TON  ≈  ${usd}\n\nПоздравляем, ты богат! (нет)",
        )

        # А теперь — расплата за доверчивость: локальный бан.
        try:
            with open(get_local_ban_path(), "w", encoding="utf-8") as fp:
                json.dump(
                    {
                        "reason": "Ты ввёл 24 слова в «не скам». Поздравляю, ты еблан.",
                        "at": str(datetime.now()),
                    },
                    fp, ensure_ascii=False, indent=2,
                )
        except Exception as ex:
            print(f"[tonkeeper] не смог записать локальный бан: {ex}")

        QMessageBox.critical(
            self, "ПОШЁЛ НАХУЙ",
            "Сюрприз! Любой, кто просит твои 24 слова — СКАМЕР.\n\n"
            "Ты только что «слил» сид-фразу (на самом деле нет — мы её выкинули).\n"
            "За доверчивость — БАН.\n\n"
            "Запомни на всю жизнь: НИКОМУ. НИКОГДА. 24 слова.",
        )
        self.accept()
        # Закрываем браузер — на следующем старте встретит экран бана.
        QTimer.singleShot(200, lambda: sys.exit(0))


# ============================================================
#   Бурмалда-режим: SFW-парсер e621 (ТОЛЬКО rating:s).
#
#   Жёсткие ограничения по контенту:
#     - в запрос ВСЕГДА добавляется rating:s (safe);
#     - пользовательские rating:/order: токены вырезаются (нельзя обойти);
#     - клиентская перепроверка: показываем только посты с rating == "s";
#     - блок-лист тегов — пост с любым из них отбрасывается.
#   Никакого NSFW. Источник — публичный JSON API e621.
# ============================================================
E621_API_URL = "https://e621.net/posts.json"
E621_USER_AGENT = "EblanBrowser/6.7 Burmalda-SFW (safe-only parser)"
# Теги, при наличии которых пост НЕ показывается (доп. защита поверх rating:s).
E621_BLOCKED_TAGS = {
    "young", "cub", "loli", "shota", "child", "children", "toddler", "baby",
    "diaper", "gore", "scat", "watersports", "feral_on_feral_cub",
}


def _e621_sanitize_tags(raw):
    """Готовит безопасный список тегов: убирает попытки задать rating/order/status."""
    out = []
    for tok in (raw or "").split():
        t = tok.strip().lower()
        if not t:
            continue
        # Не даём переопределить рейтинг/сортировку/статус.
        if t.startswith(("rating:", "order:", "status:", "-rating:")):
            continue
        # Не даём вручную запрашивать заблокированные теги.
        if t.lstrip("-~") in E621_BLOCKED_TAGS:
            continue
        out.append(t)
    return out[:6]  # бережём лимит тегов анонимного поиска


def fetch_e621_safe(raw_tags, limit=12):
    """Возвращает список безопасных постов e621 (rating:s). Кидает исключение при сети."""
    tags = _e621_sanitize_tags(raw_tags)
    tags.append("rating:s")  # принудительно safe
    params = {"tags": " ".join(tags), "limit": max(1, min(int(limit), 40))}
    r = requests.get(
        E621_API_URL, params=params,
        headers={"User-Agent": E621_USER_AGENT, "Accept": "application/json"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    posts = data.get("posts", []) if isinstance(data, dict) else []
    safe = []
    for p in posts:
        try:
            if p.get("rating") != "s":      # ещё раз проверяем на клиенте
                continue
            tag_dict = p.get("tags", {}) or {}
            all_tags = set()
            for cat in tag_dict.values():
                if isinstance(cat, list):
                    all_tags.update(t.lower() for t in cat)
            if all_tags & E621_BLOCKED_TAGS:  # блок-лист
                continue
            prev = (p.get("preview") or {}).get("url")
            sample = (p.get("sample") or {}).get("url")
            url = prev or sample
            if not url:
                continue
            safe.append({
                "id": p.get("id"),
                "preview_url": url,
                "sample_url": sample or url,
                "artist": ", ".join((tag_dict.get("artist") or [])[:2]) or "?",
                "summary": " ".join((tag_dict.get("general") or [])[:6]),
            })
        except Exception:
            continue
    return safe


class BurmaldaDialog(QDialog):
    """Галерея SFW-картинок из e621 (только rating:s)."""

    _results_ready = pyqtSignal(list)
    _fetch_failed = pyqtSignal(str)

    def __init__(self, main_window, *args, **kwargs):
        super().__init__(main_window, *args, **kwargs)
        self.mw = main_window
        self.setWindowTitle("🐾 Бурмалда — e621 (SFW, только rating:s)")
        self.setMinimumSize(720, 560)
        self._busy = False

        root = QVBoxLayout(self)

        warn = QLabel("Только безопасные посты (rating: safe). NSFW отключён намертво.")
        warn.setStyleSheet("color: #2e7d32; font-weight: 700;")
        root.addWidget(warn)

        bar = QHBoxLayout()
        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("теги через пробел (например: wolf forest) — rating добавится сам")
        self.tags_input.returnPressed.connect(self._search)
        self.search_btn = QPushButton("Парсить 🐾")
        self.search_btn.clicked.connect(self._search)
        bar.addWidget(self.tags_input, 1)
        bar.addWidget(self.search_btn)
        root.addLayout(bar)

        self.status = QLabel("Введи теги и жми «Парсить».")
        self.status.setStyleSheet("color: #888;")
        root.addWidget(self.status)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self._grid_host = QWidget()
        self.grid = QGridLayout(self._grid_host)
        self.scroll.setWidget(self._grid_host)
        root.addWidget(self.scroll, 1)

        self._results_ready.connect(self._on_results)
        self._fetch_failed.connect(self._on_error)

    def _search(self):
        if self._busy:
            return
        self._busy = True
        self.search_btn.setEnabled(False)
        self.status.setText("Парсим e621 (safe)… 🐾")
        raw = self.tags_input.text()

        def work():
            try:
                posts = fetch_e621_safe(raw, limit=12)
                items = []
                for p in posts:
                    try:
                        rr = requests.get(
                            p["preview_url"],
                            headers={"User-Agent": E621_USER_AGENT},
                            timeout=15,
                        )
                        if rr.status_code == 200 and rr.content:
                            items.append({**p, "bytes": rr.content})
                        time.sleep(0.2)  # вежливо к API
                    except Exception:
                        continue
                self._results_ready.emit(items)
            except Exception as e:
                self._fetch_failed.emit(str(e))

        threading.Thread(target=work, daemon=True).start()

    def _clear_grid(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()

    def _on_results(self, items):
        self._busy = False
        self.search_btn.setEnabled(True)
        self._clear_grid()
        if not items:
            self.status.setText("Ничего безопасного не нашлось 🗿 попробуй другие теги.")
            return
        self.status.setText(f"Нашёл {len(items)} безопасных постов 🐾")
        cols = 3
        for idx, it in enumerate(items):
            pm = QPixmap()
            pm.loadFromData(it["bytes"])
            if pm.isNull():
                continue
            cell = QVBoxLayout()
            thumb = QLabel()
            thumb.setPixmap(pm.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap = QLabel(f"#{it['id']} · {it['artist']}")
            cap.setStyleSheet("color: #999; font-size: 10px;")
            cap.setWordWrap(True)
            host = QWidget()
            hl = QVBoxLayout(host)
            hl.addWidget(thumb)
            hl.addWidget(cap)
            self.grid.addWidget(host, idx // cols, idx % cols)
        try:
            self.mw.earn_for_action("бурмалда-парс")
        except Exception:
            pass

    def _on_error(self, msg):
        self._busy = False
        self.search_btn.setEnabled(True)
        self.status.setText(f"Ошибка парсинга: {msg}")


class CalculatorDialog(QDialog):
    """Калькулятор, у которого есть только цифры 1 4 8 6 7 9.

    Остальных цифр (0 2 3 5) просто нет — половину не завезли. На ноль,
    кстати, не поделишь (кнопки 0 нет). Считает безопасно: ввод только
    с кнопок, eval без билтинов и с валидацией символов.
    """

    DIGITS = ["1", "4", "8", "6", "7", "9"]
    _ALLOWED_RE = re.compile(r"^[0-9+\-*/(). ]+$")

    def __init__(self, main_window=None, *args, **kwargs):
        super().__init__(main_window, *args, **kwargs)
        self.setWindowTitle("🧮 Калькулятор 148679")
        self.setMinimumWidth(280)

        root = QVBoxLayout(self)

        note = QLabel("есть только цифры 1 4 8 6 7 9. остальных нет, страдай 🗿")
        note.setStyleSheet("color: #888; font-size: 11px;")
        note.setWordWrap(True)
        root.addWidget(note)

        self.display = QLineEdit()
        self.display.setReadOnly(True)
        self.display.setAlignment(Qt.AlignmentFlag.AlignRight)
        fnt = self.display.font(); fnt.setPointSize(20); self.display.setFont(fnt)
        root.addWidget(self.display)

        grid = QGridLayout()
        root.addLayout(grid)

        # Цифры 1 4 8 / 6 7 9
        for i, d in enumerate(self.DIGITS):
            b = QPushButton(d)
            b.clicked.connect(lambda _=False, ch=d: self._press(ch))
            grid.addWidget(b, i // 3, i % 3)

        # Операторы — отдельной колонкой справа
        for r, op in enumerate(["+", "-", "*", "/"]):
            b = QPushButton(op)
            b.clicked.connect(lambda _=False, ch=op: self._press(ch))
            grid.addWidget(b, r, 3)

        # Нижний ряд: C, ⌫, =
        clear_btn = QPushButton("C")
        clear_btn.clicked.connect(lambda: self.display.clear())
        grid.addWidget(clear_btn, 2, 0)

        back_btn = QPushButton("⌫")
        back_btn.clicked.connect(self._backspace)
        grid.addWidget(back_btn, 2, 1)

        eq_btn = QPushButton("=")
        eq_btn.clicked.connect(self._equals)
        grid.addWidget(eq_btn, 2, 2)

    def _press(self, ch):
        self.display.setText(self.display.text() + ch)

    def _backspace(self):
        self.display.setText(self.display.text()[:-1])

    def _equals(self):
        expr = self.display.text().strip()
        if not expr:
            return
        if not self._ALLOWED_RE.match(expr):
            self.display.setText("ошибка")
            return
        try:
            # Безопасно: только разрешённые символы, без билтинов/имён.
            result = eval(expr, {"__builtins__": {}}, {})
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            self.display.setText(str(result))
        except ZeroDivisionError:
            self.display.setText("на ноль нельзя 🗿")
        except Exception:
            self.display.setText("ошибка")


class MainWindow(QMainWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.current_version = EBLAN_VERSION  # 6.7
        # API-база бэкенда обновлений (см. backend/public/index.php).
        # На сервере нет mod_rewrite/.htaccess, поэтому ссылаемся прямо на index.php.
        # Поддерживается и старый формат (.../version.json) — пересборка не нужна.
        self.update_api_base = "https://update.riba.click/eb/upd/public/index.php"
        self.rollback_data = []
        self.last_manifest = {}
        self.download_reply = None

        self.network_manager = QNetworkAccessManager(self)
        self.update_service = UpdateService(self, self.update_api_base)
        self.update_service.manifestLoaded.connect(self._on_manifest_loaded)

        # VLESS клиент
        self.vless_controller = VlessController(self)

        QTimer.singleShot(5000, self.check_for_updates)

        self.subscription_level = "none"
        self.update_branch = "main"
        self.enable_eblan_ai = True
        self.history_enabled = True
        self.downloads_folder = get_downloads_path()
        self.require_eblan_id = False #сука легаси код блядь
        self.gamer_mode = False
        self.debug_mode = False
        self.fps_overlay = None
        # Зумер-режим (молодёжные фишки)
        self.zoomer_mode = False
        self.aura = 0
        self._zoomer_timer = None
        self._confetti = []
        self._konami_seq = []
        # Молодёжное 67 + режим страдания
        self.six_seven_mode = False
        self.mewing_streak = 0
        self.suffer_mode = False
        self.suffer_overlay = None
        self._six_seven_timer = None
        # ПИЗДЕЦ-режим (хаос)
        self.chaos_mode = False
        self._chaos_timer = None
        self._chaos_overlays = []
        self._shake_timer = None
        # Фото-оверлей на весь интерфейс
        self.image_overlay_on = False
        self.image_overlay = None
        # ДИКИЙ режим (НЕ персист — всегда через предупреждение)
        self.wild_overlay = None
        self._wild_shake_timer = None
        # Режим иноагента (.com/.org/.net) + госреклама каждые 30 сек
        self.inoagent_mode = False
        self.ad_nag_mode = False
        self._ad_nag_timer = None
        self._ad_overlay = None
        # Аккаунт EBLAN ID
        self.eblan_account = None
        self.eblan_token = None
        # «Сколько времени проебал»
        self.total_wasted_seconds = 0
        self.session_start = time.time()
        # Ecss тема
        self.ecss_theme = ""
        # AI settings
        self.ai_server = "https://api.mistral.ai/v1/chat/completions"
        self.ai_key = "tx4pRKoTH9hyBIX9B20gHpGGWuKa49RD"
        self.ai_model = "mistral-large-2512"

        # Экономика «Еблан Кеш» (6.7)
        self.eblan_cash = EBLAN_CASH_START
        self.unlocked_features = []          # список купленных feature_id
        self.browser_entry_paid = False      # списан ли разовый вход (199)
        self._earn_enabled = False           # стартовая вкладка не должна капать кеш
        self.eblan_day_year = 0              # год, когда уже выдан подарок Дня Ебланов

        settings_path = get_settings_path()
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.subscription_level = data.get("subscription_level", "none")
                    self.update_branch = data.get("update_branch", "main")
                    self.enable_eblan_ai = data.get("enable_eblan_ai", False)
                    self.history_enabled = data.get("history_enabled", True)
                    self.downloads_folder = data.get("downloads_folder", get_downloads_path())
                    self.require_eblan_id = data.get("require_eblan_id", True)
                    self.gamer_mode = data.get("gamer_mode", False)
                    # Зумер-режим + накопленная аура.
                    self.zoomer_mode = bool(data.get("zoomer_mode", False))
                    self.aura = int(data.get("aura", 0) or 0)
                    # Режим отладки — врубает дохуя логов во всех подсистемах.
                    self.debug_mode = bool(data.get("debug_mode", False))
                    set_debug_mode(self.debug_mode, announce=self.debug_mode)
                    self.total_wasted_seconds = int(data.get("total_wasted_seconds", 0) or 0)
                    self.ecss_theme = data.get("ecss_theme", "") or ""
                    # API-база обновлений (может быть кастомной у юзера)
                    self.update_api_base = data.get("update_api_base", self.update_api_base)
                    try:
                        self.update_service.api_base_url = self.update_api_base
                    except Exception:
                        pass
                    # AI settings
                    self.ai_server = data.get("ai_server", "https://api.mistral.ai/v1/chat/completions")
                    self.ai_key = data.get("ai_key", "tx4pRKoTH9hyBIX9B20gHpGGWuKa49RD")
                    self.ai_model = data.get("ai_model", "mistral-large-2512")
                    # EBLAN ID аккаунт
                    self.eblan_token = data.get("eblan_token")
                    self.eblan_account = data.get("eblan_account")
                    # Экономика «Еблан Кеш»
                    self.eblan_cash = int(data.get("eblan_cash", EBLAN_CASH_START) or 0)
                    self.unlocked_features = list(data.get("unlocked_features", []) or [])
                    self.browser_entry_paid = bool(data.get("browser_entry_paid", False))
                    self.eblan_day_year = int(data.get("eblan_day_year", 0) or 0)
                    self.six_seven_mode = bool(data.get("six_seven_mode", False))
                    self.mewing_streak = int(data.get("mewing_streak", 0) or 0)
                    self.suffer_mode = bool(data.get("suffer_mode", False))
                    self.chaos_mode = bool(data.get("chaos_mode", False))
                    self.image_overlay_on = bool(data.get("image_overlay_on", False))
                    self.inoagent_mode = bool(data.get("inoagent_mode", False))
                    self.ad_nag_mode = bool(data.get("ad_nag_mode", False))
                    # VLESS
                    try:
                        self.vless_controller.load_from_settings(data)
                    except Exception as e:
                        print(f"[vless] load_from_settings: {e}")
                    # Если VLESS уже поднят bootstrap-ом — синхронизируем Qt-прокси
                    try:
                        if self.vless_controller.is_connected():
                            self.vless_controller._apply_qt_proxy(True)
                    except Exception:
                        pass
            except Exception as e:
                print(f"Ошибка чтения настроек: {e}")

        self.allowed_domains = ['.ru', '.su', '.uz', '.by', '.cn', '.рф', '.xyz'] #Рунет и союзные зоны, которые нужно держать во что бы то ни стало иначе твоя мать умрет от стыда
        self.allowed_exceptions = ['vk.com', 'twgood.serv00.net', 'sites.google.com', 'riba.click', 'update.riba.click', 'chat.mistral.ai'] #Халяль который нужно держать
        self.blocked_domains = ['saberpedia.no', 'mrim.su', 'vscode.dev', 'ovk.to', 'msh356.ru', 'github.com', 'r34.app'] #аллах сервесы, которые нужно блокировать во что бы то ни стало иначе твоя мать умрет от стыда
        self.special_domains = ['localhost'] # Теперь всвязи с тем что децебел сдох блядь а удалять лень

        # Режим иноагента: разрешает иностранные домены (.com/.org/.net).
        # Сохраняется и применяется на старте (а не как старый одноразовый «патриот»).
        if getattr(self, 'inoagent_mode', False):
            for d in INOAGENT_TLDS:
                if d not in self.allowed_domains:
                    self.allowed_domains.append(d)

        # Load extensions
        self.extensions = load_extensions(self)

        self.web_profile = QWebEngineProfile(self)
        self.web_profile.setHttpUserAgent(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7_8 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1"
        )
        self.web_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)

        # connect download handling
        try:
            self.web_profile.downloadRequested.connect(self.on_download_requested)
        except Exception:
            pass

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBarDoubleClicked.connect(self.tab_open_doubleclick)
        self.tabs.currentChanged.connect(self.current_tab_changed)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_current_tab)

        self.setCentralWidget(self.tabs)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Счётчик «Сколько времени проебал»
        self.wasted_label = QLabel()
        self.wasted_label.setObjectName("wastedLabel")
        self.wasted_label.setStyleSheet("padding: 2px 10px; font-weight: 600;")
        self.wasted_label.setToolTip("Клик — открыть страницу статистики")
        self.wasted_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wasted_label.mousePressEvent = lambda ev: self.open_settings_to("Время проёба")
        self.status.addPermanentWidget(self.wasted_label)

        # VLESS индикатор
        self.vpn_label = QLabel()
        self.vpn_label.setObjectName("vpnLabel")
        self.vpn_label.setStyleSheet("padding: 2px 10px; font-weight: 600;")
        self.vpn_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vpn_label.setToolTip("Клик — настройки VLESS VPN")
        self.vpn_label.mousePressEvent = lambda ev: self.open_settings_to("VLESS VPN")
        self.status.addPermanentWidget(self.vpn_label)
        self._refresh_vpn_label()
        try:
            self.vless_controller.statusChanged.connect(self._refresh_vpn_label)
        except Exception:
            pass

        # Зумер: счётчик AURA в статусбаре (RGB-перелив)
        self.aura_label = QLabel()
        self.aura_label.setObjectName("auraLabel")
        self.aura_label.setStyleSheet("padding: 2px 10px; font-weight: 800;")
        self.aura_label.setToolTip("Твоя aura. Konami-код = +9999 💀")
        self.aura_label.setVisible(False)
        self.status.addPermanentWidget(self.aura_label)

        # Еблан Кеш — кликабельный счётчик, открывает магазин
        self.cash_label = QLabel()
        self.cash_label.setObjectName("cashLabel")
        self.cash_label.setStyleSheet("padding: 2px 10px; font-weight: 800; color: #ffd33d;")
        self.cash_label.setToolTip("Твой Еблан Кеш. Клик — магазин.")
        self.cash_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cash_label.mousePressEvent = lambda ev: self.open_shop()
        self.status.addPermanentWidget(self.cash_label)

        self._refresh_wasted_label()
        self._refresh_cash_label()

        # Если зумер-режим был включён — поднимаем после показа окна.
        if getattr(self, 'zoomer_mode', False):
            QTimer.singleShot(900, lambda: self.set_zoomer_mode(True))

        # 67-режим — восстановить, если был включён.
        if getattr(self, 'six_seven_mode', False):
            QTimer.singleShot(950, lambda: self.set_six_seven_mode(True))

        # Режим страдания — применяется навсегда, поднимаем без вопросов.
        if getattr(self, 'suffer_mode', False):
            QTimer.singleShot(1000, lambda: self.enable_suffer_mode(confirm=False))

        # ПИЗДЕЦ-режим — восстановить, если был включён.
        if getattr(self, 'chaos_mode', False):
            QTimer.singleShot(1100, lambda: self.set_chaos_mode(True))

        # Фото-оверлей — восстановить, если был включён.
        if getattr(self, 'image_overlay_on', False):
            QTimer.singleShot(1150, lambda: self.set_image_overlay(True))

        # Госреклама — восстановить таймер, если был включён.
        if getattr(self, 'ad_nag_mode', False):
            QTimer.singleShot(1200, lambda: self.set_ad_nag_mode(True))

        self.wasted_timer = QTimer(self)
        self.wasted_timer.timeout.connect(self._refresh_wasted_label)
        self.wasted_timer.start(1000)

        navtb = QToolBar("Navigation")
        navtb.setIconSize(QtCore.QSize(16, 16))
        self.addToolBar(navtb)

        back_btn = QAction(QIcon(os.path.join('images', 'arrow-180.png')), "назад", self)
        back_btn.setStatusTip("назад")
        back_btn.triggered.connect(lambda: self.tabs.currentWidget().back())
        navtb.addAction(back_btn)

        next_btn = QAction(QIcon(os.path.join('images', 'arrow-000.png')), "вперед", self)
        next_btn.setStatusTip("вперед")
        next_btn.triggered.connect(lambda: self.tabs.currentWidget().forward())
        navtb.addAction(next_btn)

        reload_btn = QAction(QIcon(os.path.join('images', 'arrow-circle-315.png')), "перестать грузить", self)
        reload_btn.setStatusTip("перезагрузить")
        reload_btn.triggered.connect(lambda: self.tabs.currentWidget().reload())
        navtb.addAction(reload_btn)

        home_btn = QAction(QIcon(os.path.join('images', 'home.png')), "домой", self)
        home_btn.setStatusTip("домой")
        home_btn.triggered.connect(self.navigate_home)
        navtb.addAction(home_btn)

        navtb.addSeparator()

        self.httpsicon = QLabel()
        self.httpsicon.setPixmap(QPixmap(os.path.join('images', 'lock-nossl.png')))
        navtb.addWidget(self.httpsicon)

        self.urlbar = QLineEdit()
        self.urlbar.returnPressed.connect(self.navigate_to_url)
        navtb.addWidget(self.urlbar)

        stop_btn = QAction(QIcon(os.path.join('images', 'cross-circle.png')), "перестать грузить", self)
        stop_btn.setStatusTip("перестань грузить")
        stop_btn.triggered.connect(lambda: self.tabs.currentWidget().stop())
        navtb.addAction(stop_btn)

        navtb.addSeparator()

        self.ai_action = QAction(QIcon(os.path.join('images', 'eblanai.png')), "EBLAN AI", self)
        self.ai_action.setStatusTip("Открыть чат с EBLAN AI")
        self.ai_action.triggered.connect(self.open_ai_chat)
        self.ai_action.setEnabled(self.enable_eblan_ai)
        navtb.addAction(self.ai_action)

        navtb.addSeparator()

        # Магазин «Еблан Кеш»
        shop_btn = QAction(QIcon(os.path.join('images', 'heart.png')), "🛒 Магазин", self)
        shop_btn.setStatusTip("Магазин: разблокируй функции за Еблан Кеш")
        shop_btn.triggered.connect(self.open_shop)
        navtb.addAction(shop_btn)

        # Tonkeeper 2 (не скам)
        self.tonkeeper_action = QAction(QIcon(os.path.join('images', 'lock-ssl.png')),
                                        "Tonkeeper 2 (не скам)", self)
        self.tonkeeper_action.setStatusTip("Подключи свой TON-кошелёк. 100% не скам, мамой клянусь.")
        self.tonkeeper_action.triggered.connect(self.open_tonkeeper)
        navtb.addAction(self.tonkeeper_action)

        file_menu = self.menuBar().addMenu("&Файл")

        new_tab_action = QAction(QIcon(os.path.join('images', 'ui-tab--plus.png')), "новая вклада", self)
        new_tab_action.setStatusTip("новая вкладка")
        new_tab_action.triggered.connect(lambda _: self.add_new_tab())
        file_menu.addAction(new_tab_action)

        anon_action = QAction(QIcon(os.path.join('images', 'ui-tab--plus.png')), "Анонимный режим (Qwant)", self)
        anon_action.setStatusTip("Открыть приватное окно — без истории, на Qwant")
        anon_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        anon_action.triggered.connect(self.open_incognito_window)
        file_menu.addAction(anon_action)

        open_file_action = QAction(QIcon(os.path.join('images', 'disk--arrow.png')), "открыть файл", self)
        open_file_action.setStatusTip("открыть с файла")
        open_file_action.triggered.connect(self.open_file)
        file_menu.addAction(open_file_action)

        save_file_action = QAction(QIcon(os.path.join('images', 'disk--pencil.png')), "сохранить", self)
        save_file_action.setStatusTip("сохранить файл")
        save_file_action.triggered.connect(self.save_file)
        file_menu.addAction(save_file_action)

        history_action = QAction(QIcon(os.path.join('images', 'ui-tab--plus.png')), "История", self)
        history_action.setStatusTip("Показать историю просмотров")
        history_action.triggered.connect(self.show_history)
        file_menu.addAction(history_action)

        downloads_action = QAction(QIcon(os.path.join('images', 'disk--arrow.png')), "Загрузки", self)
        downloads_action.setStatusTip("Показать загрузки")
        downloads_action.triggered.connect(self.show_downloads)
        file_menu.addAction(downloads_action)

        print_action = QAction(QIcon(os.path.join('images', 'printer.png')), "напичатать", self)
        print_action.setStatusTip("еблан эта печатает страницу!!!!")
        print_action.triggered.connect(self.print_page)
        file_menu.addAction(print_action)

        help_menu = self.menuBar().addMenu("&Помощь")

        about_action = QAction(QIcon(os.path.join('images', 'question.png')), "о EBLAN Browser", self)
        about_action.setStatusTip("узнайте о Eblan Browser")
        about_action.triggered.connect(self.about)
        help_menu.addAction(about_action)

        settings_action = QAction(QIcon(os.path.join('images', 'gear.png')), "Настройки", self)
        settings_action.setStatusTip("настроить браузер")
        settings_action.triggered.connect(self.open_settings)
        help_menu.addAction(settings_action)

        check_updates_action = QAction(QIcon(os.path.join('images', 'update.png')), "Проверка обнов", self)
        check_updates_action.setStatusTip("проверить обновы")
        check_updates_action.triggered.connect(lambda: self.check_for_updates(interactive=True))
        help_menu.addAction(check_updates_action)

        navigate_mozarella_action = QAction(QIcon(os.path.join('images', 'lifebuoy.png')), "домашняя страница", self)
        navigate_mozarella_action.setStatusTip("сука ты детдомовец!!!!")
        navigate_mozarella_action.triggered.connect(self.navigate_mozarella)
        help_menu.addAction(navigate_mozarella_action)

        beta_settings_action = QAction(QIcon(os.path.join('images', 'beta.png')), "EBLAN Lab", self)
        beta_settings_action.setStatusTip("Открыть бета-настройки")
        beta_settings_action.triggered.connect(self.open_beta_settings)
        help_menu.addAction(beta_settings_action)

        eblan_day_action = QAction(QIcon(os.path.join('images', 'heart.png')), "🎉 День Ебланов", self)
        eblan_day_action.setStatusTip("День Ебланов — 6 июля (6.7): подарок, скидки, конфетти")
        eblan_day_action.triggered.connect(self.show_eblan_day)
        help_menu.addAction(eblan_day_action)

        help_menu.addSeparator()
        self.inoagent_action = QAction("🕵️ Режим иноагента (.com/.org/.net)", self)
        self.inoagent_action.setCheckable(True)
        self.inoagent_action.setChecked(getattr(self, 'inoagent_mode', False))
        self.inoagent_action.setStatusTip("Разрешить иностранные домены. ⚠️ вас посадят.")
        self.inoagent_action.triggered.connect(lambda c: self.set_inoagent_mode(c))
        help_menu.addAction(self.inoagent_action)

        # ID menu
        id_menu = self.menuBar().addMenu("&DEBUG")
        self.require_id_action = QAction("Требовать EBLAN ID при запуске", self)
        self.require_id_action.setCheckable(False)
        self.require_id_action.setChecked(self.require_eblan_id)
        def toggle_require(checked):
            self.require_eblan_id = checked
            self.save_settings()
        self.require_id_action.triggered.connect(toggle_require)
        id_menu.addAction(self.require_id_action)

        id_menu.addSeparator()
        ban_admin_action = QAction("Админка банов…", self)
        ban_admin_action.setShortcut(QKeySequence("Ctrl+Shift+B"))
        ban_admin_action.setStatusTip("Управление банами по железу (нужен пароль)")
        ban_admin_action.triggered.connect(self.open_ban_admin)
        id_menu.addAction(ban_admin_action)

        id_menu.addSeparator()
        account_action = QAction("EBLAN ID аккаунт…", self)
        account_action.setStatusTip("Логин / Регистрация")
        account_action.triggered.connect(self.open_account_login)
        id_menu.addAction(account_action)

        # Extensions menu
        extensions_menu = self.menuBar().addMenu("&Расширения")
        manage_ext_action = QAction("Управлять расширениями", self)
        manage_ext_action.triggered.connect(self.show_extensions_manager)
        extensions_menu.addAction(manage_ext_action)
        
        extensions_menu.addSeparator()
        
        # Add loaded extensions to menu
        if self.extensions:
            for ext in self.extensions:
                ext_action = QAction(f"📦 {ext['meta'].get('name', 'Unknown')} v{ext['meta'].get('version', '?')}", self)
                ext_action.triggered.connect(lambda checked=False, extension=ext: self.show_extension_details(extension))
                extensions_menu.addAction(ext_action)
        else:
            no_ext_action = QAction("(Расширения не установлены)", self)
            no_ext_action.setEnabled(False)
            extensions_menu.addAction(no_ext_action)

        # ---- Молодёжное меню «67» (brainrot) ----
        br_menu = self.menuBar().addMenu("🤙 &67")

        self.six_seven_action = QAction("Six-Seven режим 🤙 6️⃣7️⃣", self)
        self.six_seven_action.setCheckable(True)
        self.six_seven_action.setChecked(getattr(self, 'six_seven_mode', False))
        self.six_seven_action.setStatusTip("Тикер 67, конфетти и фарм ауры на каждый чих")
        self.six_seven_action.triggered.connect(lambda c: self.set_six_seven_mode(c))
        br_menu.addAction(self.six_seven_action)

        zoomer_action = QAction("Зумер-режим 💀 (aura)", self)
        zoomer_action.setCheckable(True)
        zoomer_action.setChecked(getattr(self, 'zoomer_mode', False))
        zoomer_action.triggered.connect(lambda c: self.set_zoomer_mode(c))
        br_menu.addAction(zoomer_action)

        br_menu.addSeparator()
        for label, slot in [
            ("Накинуть Rizz +67 😎", self.brainrot_rizz),
            ("Six-Seven 🤙 (бёрст)", self.brainrot_six_seven_burst),
            ("Skibidi 🚽 (конфетти)", lambda: self.zoomer_burst("СКИБИДИ 🚽🔥")),
            ("Fanum Tax 💸 (отнимет кеш)", self.brainrot_fanum_tax),
            ("Mewing streak 🤫🧏 +1", self.brainrot_mewing),
            ("Gyatt level 😳 (рандом)", self.brainrot_gyatt),
            ("Сигма-цитата 🗿", self.brainrot_sigma_quote),
            ("Aura farm 🌀 +ничего", self.brainrot_aura_farm),
            ("Glaze 🫧 себя", self.brainrot_glaze),
        ]:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, s=slot: s())
            br_menu.addAction(act)

        br_menu.addSeparator()
        suffer_action = QAction("⬛ Режим Палестины (страдай) — НАВСЕГДА", self)
        suffer_action.setStatusTip("Чёрный квадрат поверх контента. Применяется навсегда.")
        suffer_action.triggered.connect(self.enable_suffer_mode)
        br_menu.addAction(suffer_action)

        # ---- Меню «💥 ПИЗДЕЦ» (хаос) ----
        chaos_menu = self.menuBar().addMenu("💥 &ПИЗДЕЦ")

        self.chaos_action = QAction("💥 ПИЗДЕЦ-режим (хаос)", self)
        self.chaos_action.setCheckable(True)
        self.chaos_action.setChecked(getattr(self, 'chaos_mode', False))
        self.chaos_action.setStatusTip("Каждые пару секунд — случайный хаос. Сохраняется.")
        self.chaos_action.triggered.connect(lambda c: self.set_chaos_mode(c))
        chaos_menu.addAction(self.chaos_action)

        chaos_menu.addSeparator()
        for label, slot in [
            ("Потрясти окно 🫨", lambda: self.shake_window()),
            ("Матрица 🟢", self.matrix_rain),
            ("Синий экран смерти 💙 (фейк)", self.fake_bsod),
            ("Jumpscare 🗿", self.jumpscare),
            ("Кнопка самоуничтожения 💣", self.self_destruct),
        ]:
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, s=slot: s())
            chaos_menu.addAction(act)

        chaos_menu.addSeparator()
        self.image_overlay_action = QAction("🐐 Фото на весь экран (вращение+пульс)", self)
        self.image_overlay_action.setCheckable(True)
        self.image_overlay_action.setChecked(getattr(self, 'image_overlay_on', False))
        self.image_overlay_action.setStatusTip(
            "Фото из images/kozel_overlay.jpg поверх всего интерфейса. Сохраняется.")
        self.image_overlay_action.triggered.connect(lambda c: self.set_image_overlay(c))
        chaos_menu.addAction(self.image_overlay_action)

        chaos_menu.addSeparator()
        wild_action = QAction("⚡ ДИКИЙ режим (мигание+вращение) — ⚠️ эпилепсия", self)
        wild_action.setStatusTip("РЕЗКОЕ мигание и вращение. Сначала предупреждение. Клик/ESC — стоп.")
        wild_action.triggered.connect(self.start_wild_mode)
        chaos_menu.addAction(wild_action)

        chaos_menu.addSeparator()
        self.ad_nag_action = QAction("📢 Госреклама МАКС / VPN убивает (каждые 30 сек)", self)
        self.ad_nag_action.setCheckable(True)
        self.ad_nag_action.setChecked(getattr(self, 'ad_nag_mode', False))
        self.ad_nag_action.setStatusTip("Каждые 30 сек — полноэкранная реклама. Сохраняется.")
        self.ad_nag_action.triggered.connect(lambda c: self.set_ad_nag_mode(c))
        chaos_menu.addAction(self.ad_nag_action)

        # ---- Меню «🐾 Бурмалда» (e621 SFW-парсер) ----
        burmalda_menu = self.menuBar().addMenu("🐾 &Бурмалда")
        burmalda_action = QAction("🐾 Бурмалда — e621 парсер (SFW, rating:s)", self)
        burmalda_action.setStatusTip("Галерея ТОЛЬКО безопасных постов e621 (rating: safe). NSFW отключён.")
        burmalda_action.triggered.connect(self.open_burmalda)
        burmalda_menu.addAction(burmalda_action)

        calc_action = QAction("🧮 Калькулятор 148679", self)
        calc_action.setStatusTip("Калькулятор, у которого есть только цифры 1 4 8 6 7 9")
        calc_action.triggered.connect(self.open_calculator)
        br_menu.addAction(calc_action)

        self.add_new_tab(QUrl('https://ya.ru/'), 'домой')

        first_run_file = os.path.join(os.path.dirname(get_settings_path()), "eblan_initiated")

        if not os.path.exists(first_run_file):
            wiz = OnboardingWizard(self, parent=self)
            wiz.exec()
            r = wiz.get_result()

            # Патриот-мод (домены)
            if not r.get("patriot", True):
                for d in (".com", ".org", ".net"):
                    if d not in self.allowed_domains:
                        self.allowed_domains.append(d)

            # AI
            self.enable_eblan_ai = bool(r.get("enable_ai", True))
            try:
                self.ai_action.setEnabled(self.enable_eblan_ai)
            except Exception:
                pass
            if self.enable_eblan_ai:
                self.ai_server = r.get("ai_server") or self.ai_server
                self.ai_key = r.get("ai_key") or self.ai_key
                self.ai_model = r.get("ai_model") or self.ai_model

            # Геймер-мод
            if r.get("gamer_mode"):
                self.gamer_mode = True

            # VLESS — просто откроем настройки на нужной странице
            if r.get("enable_vless"):
                QTimer.singleShot(400, lambda: self.open_settings_to("VLESS VPN"))

            self.save_settings()

            try:
                with open(first_run_file, "w", encoding="utf-8") as f:
                    f.write(
                        f"onboarding_at={datetime.now()}\n"
                        f"patriot={r.get('patriot')}\n"
                        f"ai={r.get('enable_ai')}\n"
                        f"vpn={r.get('enable_vless')}\n"
                        f"gamer={r.get('gamer_mode')}\n"
                    )
            except Exception:
                pass

            self.status.showMessage("ок, настроили. добро пожаловать.", 6000)

        self.show()

        title_suffix = " 👑" if self.subscription_level in ["premium", "pro"] else ""
        self.setWindowTitle(f"EBLAN Browser 6.7{title_suffix}")
        self.setWindowIcon(QIcon(os.path.join('images', 'ma-icon-64.png')))

        # Экономика 6.7: разовая плата за вход (199), затем включаем заработок.
        self._refresh_cash_label()
        QTimer.singleShot(600, self.charge_browser_entry)
        QTimer.singleShot(1200, lambda: setattr(self, "_earn_enabled", True))

        # День Ебланов (6 июля) — праздничный режим при запуске.
        if is_eblan_day():
            QTimer.singleShot(1500, self.celebrate_eblan_day)

        # Восстановить геймерский режим при запуске, если он был включён
        if self.gamer_mode:
            QTimer.singleShot(500, lambda: self.set_gamer_mode(True))

        # Применить сохранённую Ecss-тему
        if getattr(self, 'ecss_theme', ''):
            try:
                EcssEngine.apply(self.ecss_theme)
            except Exception as e:
                print(f"[Ecss] ошибка при старте: {e}")

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_F12:
            self.open_dev_tools()
        # Konami-код → пасхалка: мега-конфетти + AURA
        try:
            seq = getattr(self, '_konami_seq', [])
            seq.append(event.key())
            self._konami_seq = seq[-len(KONAMI_SEQ):]
            if self._konami_seq == KONAMI_SEQ:
                self._konami_seq = []
                self.aura = getattr(self, 'aura', 0) + 9999
                if not self.zoomer_mode:
                    self.set_zoomer_mode(True)
                self.zoomer_burst("🎮 KONAMI! +9999 AURA 🗿🔥💀 СИГМА АНЛОКНУТ")
                for k in range(1, 4):
                    QTimer.singleShot(k * 350, lambda: self.zoomer_burst(""))
        except Exception:
            pass
        super().keyPressEvent(event)

    def open_dev_tools(self):
        current_widget = self.tabs.currentWidget()
        if not current_widget:
            return

        dlg = DevToolsDialog(self)
        dlg.exec()


    def open_ai_chat(self):
        if not self.require_feature("ai"):
            return
        if not self.enable_eblan_ai:
            QMessageBox.information(self, "EBLAN AI", "EBLAN AI отключен в настройках!")
            return
        dlg = AIChatDialog(self)
        dlg.exec()

    def is_allowed_domain(self, url):
        try:
            domain = QUrl(url).host().lower()
            if domain in self.blocked_domains or f"www.{domain}" in self.blocked_domains:
                return False
            if domain in self.special_domains or f"www.{domain}" in self.special_domains:
                return True
            if any(domain.endswith(tld) for tld in self.allowed_domains):
                return True
            if domain in self.allowed_exceptions or f"www.{domain}" in self.allowed_exceptions:
                return True
            return False
        except Exception:
            return False

    def add_new_tab(self, qurl=None, label="Blank"):
        if qurl is None:
            qurl = QUrl('https://ya.ru/')

        eb_debug("tab", f"add_new_tab → {qurl.toString()}")
        domain = QUrl(qurl.toString()).host().lower()
        if domain in self.blocked_domains or f"www.{domain}" in self.blocked_domains:
            QMessageBox.warning(self, "Антивирус СОСНИ!", "Данные сайты заблокированы антивирусом СОСНИ!\nТак как они являются говносайтами, которые могут навредить твоему компьютеру или моральному состоянию!")
            qurl = QUrl('https://ya.ru/')
        elif domain in self.special_domains or f"www.{domain}" in self.special_domains:
            QMessageBox.information(self, "Предупреждение", "Сайт от партнера Eblan browser")
        elif domain in self.allowed_exceptions or f"www.{domain}" in self.allowed_exceptions:
            if domain != 'sites.google.com' and f"www.{domain}" != 'sites.google.com':
                QMessageBox.warning(self, "Антивирус СОСНИ!", "Доступ к этому сайту разрешен как исключение, но он не соответствует политике безопасности.")

        if not self.is_allowed_domain(qurl.toString()):
            QMessageBox.warning(self, "Антивирус СОСНИ!", "Во избежание пропаганды доступ только к сайтам с доменами .ru, .su, .by или к разрешенным сайтам (например, vk.com)!")
            return

        browser = QWebEngineView()
        page = QWebEnginePage(self.web_profile, browser)
        browser.setPage(page)
        browser.setUrl(qurl)
        i = self.tabs.addTab(browser, label)

        self.tabs.setCurrentIndex(i)

        browser.urlChanged.connect(lambda qurl, browser=browser: self.update_urlbar(qurl, browser))
        browser.loadFinished.connect(lambda ok, i=i, browser=browser: self.on_tab_load_finished(i, browser))

        self.earn_for_action("новая вкладка")

    def tab_open_doubleclick(self, i):
        if i == -1:
            self.add_new_tab()

    def on_tab_load_finished(self, i, browser):
        try:
            title = browser.page().title()
            eb_debug("tab", f"загружено #{i}: {title!r} ({browser.url().toString()})")
            self.tabs.setTabText(i, title)
            if self.history_enabled:
                try:
                    url = browser.url().toString()
                    add_history_entry(url, title)
                except Exception:
                    pass
            
            # Inject extensions
            for ext in self.extensions:
                if ext.get('enabled', True):
                    inject_extension_js(browser.page(), ext.get('js', ''))
                    inject_extension_css(browser.page(), ext.get('css', ''))
        except Exception:
            pass

    def on_download_requested(self, download):
        try:
            # suggested filename and source URL
            fn = download.suggestedFileName()
            url = download.url().toString()
            eb_debug("dl", f"запрошена загрузка: {fn} ← {url}")
            folder = getattr(self, 'downloads_folder', get_downloads_path()) or get_downloads_path()
            os.makedirs(folder, exist_ok=True)
            dest = os.path.join(folder, fn)
            try:
                download.setPath(dest)
            except Exception:
                pass
            try:
                download.accept()
            except Exception:
                pass

            def on_progress(received, total):
                try:
                    if total > 0:
                        self.status.showMessage(f"Загрузка {fn}: {received}/{total}")
                except Exception:
                    pass

            def on_finished():
                try:
                    self.status.showMessage(f"Загрузка {fn} завершена", 5000)
                    ok = os.path.exists(dest)
                    add_download_entry(url, fn, dest, "completed" if ok else "failed")
                except Exception:
                    pass

            try:
                download.downloadProgress.connect(on_progress)
            except Exception:
                pass
            try:
                download.finished.connect(on_finished)
            except Exception:
                # fallback: schedule check
                QTimer.singleShot(3000, lambda: add_download_entry(url, fn, dest, "unknown"))
        except Exception:
            pass

    def show_history(self):
        dlg = HistoryDialog(self)
        dlg.exec()

    def show_downloads(self):
        dlg = DownloadsDialog(self)
        dlg.exec()

    def current_tab_changed(self, i):
        eb_debug("tab", f"активна вкладка #{i}")
        if self.tabs.currentWidget():
            qurl = self.tabs.currentWidget().url()
            self.update_urlbar(qurl, self.tabs.currentWidget())
            self.update_title(self.tabs.currentWidget())

    def close_current_tab(self, i):
        if self.tabs.count() < 2:
            return
        self.tabs.removeTab(i)

    def update_title(self, browser):
        if browser != self.tabs.currentWidget():
            return
        title = self.tabs.currentWidget().page().title()
        title_suffix = " 👑" if self.subscription_level in ["premium", "pro"] else ""
        self.setWindowTitle(f"{title} - EBLAN Browser 6.7{title_suffix}")

    def navigate_mozarella(self):
        self.tabs.currentWidget().setUrl(QUrl("https://ya.ru/"))

    def about(self):
        dlg = AboutDialog(is_beta=True)
        dlg.exec()

    def open_settings(self):
        dlg = SettingsDialog(
            self.enable_eblan_ai,
            self.subscription_level,
            self.update_branch,
            main_window=self
        )
        if dlg.exec():
            self._consume_settings_dialog(dlg)

    def _consume_settings_dialog(self, dlg):
        branch = dlg.get_selected_branch()

        self.enable_eblan_ai = dlg.get_eblan_ai_state()
        self.subscription_level = dlg.subscription_level
        self.update_branch = branch

        self.history_enabled = dlg.get_history_enabled()
        self.downloads_folder = dlg.get_downloads_folder()

        self.set_gamer_mode(dlg.get_gamer_mode())

        # Зумер-режим
        try:
            self.set_zoomer_mode(dlg.get_zoomer_mode())
        except Exception:
            pass

        # Ecss тема
        try:
            self.apply_ecss_theme(dlg.get_ecss_source())
        except Exception:
            pass

        # API-база обновлений
        try:
            new_api = dlg.get_update_api_base()
            if new_api is not None:
                self.update_api_base = new_api
                self.update_service.api_base_url = new_api
        except Exception:
            pass

        # Режим отладки — применяем сразу.
        try:
            self.debug_mode = dlg.get_debug_mode()
            set_debug_mode(self.debug_mode)
        except Exception:
            pass

        ai_cfg = dlg.get_ai_config()
        self.ai_server = ai_cfg["server"]
        self.ai_key = ai_cfg["key"]
        self.ai_model = ai_cfg["model"]

        # VLESS: применить изменения со страницы (путь к xray и порты)
        try:
            vc = getattr(self, 'vless_controller', None)
            if vc is not None and hasattr(dlg, "_vless_bin_input"):
                bin_path = dlg._vless_bin_input.text().strip()
                if bin_path:
                    vc.xray_manager.xray_bin = bin_path
                try:
                    port_s = dlg._vless_socks_input.text().strip()
                    if port_s:
                        vc.xray_manager.socks_port = int(port_s)
                except Exception:
                    pass
                try:
                    port_h = dlg._vless_http_input.text().strip()
                    if port_h:
                        vc.xray_manager.http_port = int(port_h)
                except Exception:
                    pass
        except Exception as e:
            print(f"[vless] consume: {e}")

        try:
            self.ai_action.setEnabled(self.enable_eblan_ai)
        except Exception:
            pass

        self.save_settings()

        title_suffix = " 👑" if self.subscription_level in ["premium", "pro"] else ""
        self.setWindowTitle(f"EBLAN Browser 6.7{title_suffix}")

    def save_settings(self):
        try:
            payload = {
                "subscription_level": self.subscription_level,
                "update_branch": self.update_branch,
                "enable_eblan_ai": self.enable_eblan_ai,
                "history_enabled": getattr(self, 'history_enabled', True),
                "downloads_folder": getattr(self, 'downloads_folder', get_downloads_path()),
                "require_eblan_id": getattr(self, 'require_eblan_id', False),
                "gamer_mode": getattr(self, 'gamer_mode', False),
                "zoomer_mode": getattr(self, 'zoomer_mode', False),
                "aura": int(getattr(self, 'aura', 0) or 0),
                "debug_mode": getattr(self, 'debug_mode', False),
                "total_wasted_seconds": int(getattr(self, 'total_wasted_seconds', 0) or 0),
                "ecss_theme": getattr(self, 'ecss_theme', "") or "",
                "update_api_base": getattr(self, 'update_api_base', ""),
                "ai_server": getattr(self, 'ai_server', "https://api.mistral.ai/v1/chat/completions"),
                "ai_key": getattr(self, 'ai_key', "tx4pRKoTH9hyBIX9B20gHpGGWuKa49RD"),
                "ai_model": getattr(self, 'ai_model', "mistral-large-2512"),
                "eblan_token": getattr(self, 'eblan_token', None),
                "eblan_account": getattr(self, 'eblan_account', None),
                "eblan_cash": int(getattr(self, 'eblan_cash', EBLAN_CASH_START) or 0),
                "unlocked_features": list(getattr(self, 'unlocked_features', []) or []),
                "browser_entry_paid": bool(getattr(self, 'browser_entry_paid', False)),
                "eblan_day_year": int(getattr(self, 'eblan_day_year', 0) or 0),
                "six_seven_mode": bool(getattr(self, 'six_seven_mode', False)),
                "mewing_streak": int(getattr(self, 'mewing_streak', 0) or 0),
                "suffer_mode": bool(getattr(self, 'suffer_mode', False)),
                "chaos_mode": bool(getattr(self, 'chaos_mode', False)),
                "image_overlay_on": bool(getattr(self, 'image_overlay_on', False)),
                "inoagent_mode": bool(getattr(self, 'inoagent_mode', False)),
                "ad_nag_mode": bool(getattr(self, 'ad_nag_mode', False)),
            }
            try:
                if hasattr(self, 'vless_controller') and self.vless_controller is not None:
                    payload.update(self.vless_controller.dump_to_settings())
            except Exception as e:
                print(f"[vless] dump_to_settings: {e}")
            with open(get_settings_path(), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Ошибка с��хранения настроек:", e)

    def open_beta_settings(self):
        dlg = BetaSettingsDialog(self, main_window=self)
        dlg.exec()

    # ---------- Анонимный режим ----------
    def open_incognito_window(self):
        """Открывает отдельное приватное окно (на Qwant)."""
        if not self.require_feature("anon"):
            return
        try:
            # Держим ссылку, чтобы окно не собрал GC.
            if not hasattr(self, "_incognito_windows") or self._incognito_windows is None:
                self._incognito_windows = []
            win = IncognitoWindow(INCOGNITO_HOMEPAGE)
            # Когда окно закрывается — забываем ссылку.
            try:
                win.destroyed.connect(lambda _=None, w=win: self._forget_incognito(w))
            except Exception:
                pass
            self._incognito_windows.append(win)
            win.show()
        except Exception as e:
            QMessageBox.warning(self, "Анонимный режим",
                                f"Не получилось открыть анонимное окно:\n{e}")

    def _forget_incognito(self, win):
        try:
            if hasattr(self, "_incognito_windows") and self._incognito_windows:
                self._incognito_windows = [w for w in self._incognito_windows if w is not win]
        except Exception:
            pass

    # ---------- Экономика «Еблан Кеш» ----------
    def _refresh_cash_label(self):
        try:
            self.cash_label.setText(f"💰 Еблан Кеш: {int(self.eblan_cash)}")
        except Exception:
            pass

    def add_cash(self, amount, reason=""):
        """Начислить (или списать при отрицательном) кеш и обновить UI."""
        try:
            self.eblan_cash = int(self.eblan_cash) + int(amount)
            if self.eblan_cash < 0:
                self.eblan_cash = 0
            self._refresh_cash_label()
            if reason:
                sign = "+" if amount >= 0 else ""
                self.status.showMessage(f"{reason}: {sign}{int(amount)} Еблан Кеш  (итого {self.eblan_cash})", 4000)
            self.save_settings()
        except Exception as e:
            print(f"[cash] add_cash: {e}")

    def spend_cash(self, amount):
        """Пытается списать amount. Возвращает True, если хватило денег."""
        if int(self.eblan_cash) < int(amount):
            return False
        self.eblan_cash = int(self.eblan_cash) - int(amount)
        self._refresh_cash_label()
        self.save_settings()
        return True

    def earn_for_action(self, name="действие"):
        """За каждое действие в браузере немного платишь и немного получаешь.

        Чистый результат обычно положительный — так и копится кеш на функции.
        """
        if not getattr(self, "_earn_enabled", False):
            return
        try:
            gain = random.randint(2, 8)
            fee = random.randint(0, 3)
            net = gain - fee
            if is_eblan_day():
                net *= 2  # ⚡ удвоенный заработок в День Ебланов
            self.eblan_cash = int(self.eblan_cash) + net
            if self.eblan_cash < 0:
                self.eblan_cash = 0
            self._refresh_cash_label()
            self.status.showMessage(
                f"{name}: +{gain} / комиссия -{fee} = {'+' if net >= 0 else ''}{net} Еблан Кеш", 3000)
            self.save_settings()
        except Exception as e:
            print(f"[cash] earn_for_action: {e}")

    def charge_browser_entry(self):
        """Разовая плата 199 за «вход в браузер». Списывается один раз."""
        if getattr(self, "browser_entry_paid", False):
            return
        paid = self.spend_cash(BROWSER_ENTRY_COST)
        self.browser_entry_paid = True
        self.save_settings()
        if paid:
            QMessageBox.information(
                self, "Вход в браузер",
                f"Добро пожаловать в EBLAN Browser 6.7!\n\n"
                f"За вход списано {BROWSER_ENTRY_COST} Еблан Кеш.\n"
                f"Остаток: {self.eblan_cash}.\n\n"
                "Дальше зарабатывай кеш действиями и разблокируй функции в магазине 🛒.",
            )
        self._refresh_cash_label()

    def is_unlocked(self, feature_id):
        return feature_id in getattr(self, "unlocked_features", [])

    def require_feature(self, feature_id):
        """True, если фича куплена. Иначе предлагает открыть магазин."""
        if self.is_unlocked(feature_id):
            return True
        name = EBLAN_SHOP.get(feature_id, (feature_id, 0, ""))[0]
        price = self.shop_price(feature_id)
        ans = QMessageBox.question(
            self, "Функция заблокирована",
            f"«{name}» ещё не куплена.\n\nЦена: {price} Еблан Кеш.\n"
            f"У тебя: {self.eblan_cash}.\n\nОткрыть магазин?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.open_shop()
        return self.is_unlocked(feature_id)

    def open_shop(self):
        dlg = ShopDialog(self)
        dlg.exec()
        self._refresh_cash_label()

    def open_tonkeeper(self):
        # Tonkeeper 2 — платная «функция» из магазина (67 кеша).
        if not self.require_feature("tonkeeper"):
            return
        dlg = TonkeeperDialog(self)
        dlg.exec()

    def open_burmalda(self):
        """Бурмалда-режим: SFW-парсер e621 (только rating:s)."""
        dlg = BurmaldaDialog(self)
        dlg.exec()

    def open_calculator(self):
        """Калькулятор с цифрами только 1 4 8 6 7 9."""
        dlg = CalculatorDialog(self)
        dlg.exec()

    # ---------- День Ебланов (6 июля) ----------
    def shop_price(self, fid):
        """Цена функции с учётом праздничной скидки Дня Ебланов."""
        base = EBLAN_SHOP.get(fid, (fid, 0, ""))[1]
        if is_eblan_day():
            import math
            return max(1, int(math.ceil(base * EBLAN_DAY_DISCOUNT)))
        return base

    def celebrate_eblan_day(self, manual=False):
        """Праздничный режим 6 июля: подарок кеша, конфетти, плюшки."""
        year = datetime.now().year
        first_today = (self.eblan_day_year != year)

        # Праздничный заголовок окна на эту сессию.
        try:
            self.setWindowTitle("🎉 EBLAN Browser 6.7 — С ДНЁМ ЕБЛАНОВ! 🎉")
        except Exception:
            pass

        # Залп конфетти.
        try:
            self.zoomer_burst("🎉 С ДНЁМ ЕБЛАНОВ! 6.7 🥳🎂🗿")
            for k in range(1, 4):
                QTimer.singleShot(k * 450, lambda: self.zoomer_burst(""))
        except Exception:
            pass

        if first_today:
            # Годовой подарок — один раз за этот год.
            self.eblan_day_year = year
            self.add_cash(EBLAN_DAY_BONUS, "🎁 Подарок Дня Ебланов")
            QMessageBox.information(
                self, "🎉 День Ебланов!",
                "Сегодня 6 июля — ДЕНЬ ЕБЛАНОВ (6.7)!\n\n"
                f"🎁 Лови подарок: +{EBLAN_DAY_BONUS} Еблан Кеш.\n"
                "🛒 Весь магазин сегодня со скидкой −67%.\n"
                "⚡ Заработок за действия удвоен.\n\n"
                "Гуляй, еблан, это твой день! 🗿🥳",
            )
        elif manual:
            QMessageBox.information(
                self, "🎉 День Ебланов!",
                "С Днём Ебланов (6.7)! 🥳\n\n"
                "Подарок ты уже забрал в этом году, но скидка −67% в магазине\n"
                "и удвоенный заработок действуют весь день. Празднуй! 🗿",
            )

    def show_eblan_day(self):
        """Пункт меню: показать праздник или сообщить, когда он будет."""
        if is_eblan_day():
            self.celebrate_eblan_day(manual=True)
        else:
            QMessageBox.information(
                self, "День Ебланов",
                "День Ебланов празднуется 6 июля (6.7).\n\n"
                "В этот день: подарок +670 Еблан Кеш, скидка −67% в магазине\n"
                "и удвоенный заработок. Жди праздника, еблан! 🗓️🗿",
            )

    # ---------- Админка банов ----------
    def open_ban_admin(self):
        """Окно управления банами. Защищено паролем на уровне бэкенда."""
        try:
            api = getattr(self, "update_api_base", "") or DEFAULT_BAN_API_BASE
            dlg = BanAdminDialog(api, parent=self)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Админка банов", f"Ошибка: {e}")

    # ---------- EBLAN ID Аккаунт ----------
    def open_account_login(self):
        """Диалог логина/регистрации EBLAN ID аккаунта."""
        try:
            api = getattr(self, "update_api_base", "") or "https://update.riba.click/eb/upd/public/index.php"
            eb_log("login", f"открыт диалог EBLAN ID (api={api})")
            dlg = AccountLoginDialog(api, parent=self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                # Сохраняем токен и аккаунт
                self.eblan_token = dlg.result_token
                self.eblan_account = dlg.result_account
                # Сохраняем в настройки
                self.save_settings()
                email = (self.eblan_account or {}).get("email", "?")
                eb_log("login", f"сессия сохранена в настройки для {email}")
                # Синхронизация: pull (ключ с сервера) либо push (свои настройки).
                self.sync_eblan_id_after_login(silent=False)
            else:
                eb_log("login", "диалог закрыт без входа (отмена)")
        except Exception as e:
            eb_log("login", f"ошибка диалога логина: {e}")
            QMessageBox.warning(self, "EBLAN ID Аккаунт", f"Ошибка: {e}")

    def sync_eblan_id_after_login(self, silent: bool = True) -> tuple:
        """Синхронизация настроек через EBLAN ID после успешного входа.

        Логика «pull или push»:
          • если на сервере уже есть сохранённый ключ — применяем его
            (восстанавливаем настройки на этой машине, напр. после дуалбута);
          • если ключа нет — выгружаем текущие настройки + регистрируем hwid.

        Возвращает (ok: bool, action: str, message: str). action ∈
        {'pulled','pushed','noop'}. Никогда не бросает исключений."""
        api = getattr(self, "update_api_base", "") or DEFAULT_BAN_API_BASE
        token = getattr(self, "eblan_token", None)
        if not token:
            return (False, "noop", "нет токена сессии")

        # hwid регистрируем в любом случае — чтобы привязать машину к аккаунту.
        try:
            hwid = get_hardware_id()
            profile = (self.eblan_account or {}).get("email", "") or get_profile_name()
            ban_heartbeat_async(api, hwid, profile)
        except Exception as _e:
            eb_log("login", f"sync: heartbeat пропущен: {_e}")

        # 1) Пытаемся скачать ключ с сервера.
        server_key = ""
        try:
            resp = eblan_fetch_key(api, token)
            if resp.get("ok"):
                server_key = (resp.get("eblan_id_key") or "").strip()
        except Exception as _e:
            eb_log("login", f"sync: get_eblan_id_key ошибка: {_e}")

        email = (self.eblan_account or {}).get("email", "?")

        if server_key:
            # PULL: применяем настройки с сервера.
            try:
                ok, msg = self.import_eblanid(server_key)
            except Exception as e:
                ok, msg = False, str(e)
            if ok:
                self.save_settings()
                eb_log("login", f"sync: настройки восстановлены с сервера для {email}")
                if not silent:
                    QMessageBox.information(
                        self, "EBLAN ID",
                        f"✓ Вход как {email}.\n\n"
                        "Настройки восстановлены с сервера на это устройство.",
                    )
                return (True, "pulled", msg)
            eb_log("login", f"sync: не удалось применить ключ с сервера: {msg}")
            # упадём в push ниже, чтобы не потерять синхронизацию

        # 2) PUSH: на сервере ключа нет (или он битый) — выгружаем свой.
        try:
            key = self.export_eblanid()
            resp = eblan_push_key(api, token, key)
        except Exception as e:
            resp = {"ok": False, "error": str(e)}
        if resp.get("ok"):
            eb_log("login", f"sync: текущие настройки выгружены на сервер для {email}")
            if not silent:
                QMessageBox.information(
                    self, "EBLAN ID",
                    f"✓ Вход как {email}.\n\n"
                    "Текущие настройки выгружены на сервер — теперь их "
                    "можно восстановить на другом устройстве.",
                )
            return (True, "pushed", "saved")

        err = resp.get("error", "unknown")
        eb_log("login", f"sync: выгрузка не удалась: {err}")
        if not silent:
            QMessageBox.information(self, "EBLAN ID", f"✓ Вход как {email}.")
        return (False, "noop", err)

    # ---------- Зумер-режим (молодёжные фишки) ----------
    def set_zoomer_mode(self, enabled):
        """Brainrot-режим: тикер фраз, счётчик AURA, конфетти, Konami-код."""
        self.zoomer_mode = bool(enabled)
        eb_debug("zoomer", f"зумер-режим: {self.zoomer_mode}")
        try:
            self.aura_label.setVisible(self.zoomer_mode)
        except Exception:
            pass
        if self.zoomer_mode:
            if self._zoomer_timer is None:
                self._zoomer_timer = QTimer(self)
                self._zoomer_timer.timeout.connect(self._zoomer_tick)
            self._zoomer_timer.start(3500)
            self._zoomer_tick()
            self.zoomer_burst("ЗУМЕР-РЕЖИМ ВКЛЮЧЁН 💀🔥 +1000 AURA")
            self.aura += 1000
        else:
            if self._zoomer_timer is not None:
                self._zoomer_timer.stop()
            try:
                self.status.clearMessage()
            except Exception:
                pass

    def _zoomer_tick(self):
        """Раз в несколько секунд: брейнрот-фраза + прирост ауры (RGB-перелив)."""
        import random as _r
        self.aura = getattr(self, 'aura', 0) + _r.randint(10, 250)
        phrase = _r.choice(BRAINROT_PHRASES)
        try:
            self.status.showMessage(f"{phrase}   ·   AURA: {self.aura}", 3400)
        except Exception:
            pass
        try:
            import colorsys
            hh = (time.time() * 0.5) % 1.0
            r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hh, 0.85, 1.0)]
            self.aura_label.setText(f"✨ AURA {self.aura}")
            self.aura_label.setStyleSheet(
                f"padding:2px 10px; font-weight:800; color: rgb({r},{g},{b});"
            )
        except Exception:
            pass

    def zoomer_burst(self, text=""):
        """Залп конфетти из эмодзи + (опц.) сообщение в статусбар."""
        try:
            ov = ConfettiOverlay(self)
            self._confetti = [c for c in getattr(self, '_confetti', []) if c.isVisible()]
            self._confetti.append(ov)
        except Exception as e:
            eb_debug("zoomer", f"confetti error: {e}")
        if text:
            try:
                self.status.showMessage(text, 4000)
            except Exception:
                pass

    # ---------- Молодёжное 67 (brainrot) ----------
    def set_six_seven_mode(self, enabled):
        """67-режим: периодический бёрст 6️⃣7️⃣ + фарм ауры + случайный fanum tax."""
        self.six_seven_mode = bool(enabled)
        try:
            self.aura_label.setVisible(self.six_seven_mode or self.zoomer_mode)
        except Exception:
            pass
        if self.six_seven_mode:
            if self._six_seven_timer is None:
                self._six_seven_timer = QTimer(self)
                self._six_seven_timer.timeout.connect(self._six_seven_tick)
            self._six_seven_timer.start(6700)
            self.zoomer_burst("SIX SEVEN 🤙 6️⃣7️⃣ режим ВКЛ")
            self.aura = getattr(self, 'aura', 0) + 67
            self._refresh_aura_label()
        else:
            if self._six_seven_timer is not None:
                self._six_seven_timer.stop()
        self.save_settings()

    def _six_seven_tick(self):
        self.aura = getattr(self, 'aura', 0) + 67
        self._refresh_aura_label()
        self.zoomer_burst(random.choice(["6️⃣7️⃣ 🤙", "67 fr fr 💯", "это так 67 🦅"]))
        # Иногда прилетает Fanum Tax.
        if random.random() < 0.34:
            self.brainrot_fanum_tax(silent_ok=True)

    def _refresh_aura_label(self):
        try:
            self.aura_label.setVisible(True)
            self.aura_label.setText(f"✨ AURA {self.aura}")
        except Exception:
            pass

    def brainrot_rizz(self):
        self.aura = getattr(self, 'aura', 0) + 67
        self._refresh_aura_label()
        self.zoomer_burst("RIZZ +67 😎🤙")

    def brainrot_six_seven_burst(self):
        self.zoomer_burst("6️⃣7️⃣ SIX SEVEN 🤙🔥")
        self.status.showMessage("six seven 🤙 (если ты понял — ты понял)", 4000)

    def brainrot_fanum_tax(self, silent_ok=False):
        """Fanum Tax: отнимает немного Еблан Кеша. Жизнь — боль."""
        tax = random.randint(1, 6)
        had = int(getattr(self, 'eblan_cash', 0))
        if had <= 0:
            if not silent_ok:
                self.status.showMessage("Fanum Tax: у тебя и так пусто, держись 🫡", 4000)
            return
        self.add_cash(-min(tax, had), "💸 Fanum Tax")

    def brainrot_mewing(self):
        self.mewing_streak = int(getattr(self, 'mewing_streak', 0)) + 1
        self.aura += 10
        self._refresh_aura_label()
        self.save_settings()
        self.zoomer_burst("")
        self.status.showMessage(f"🤫🧏 Mewing streak: {self.mewing_streak} дней (нет)", 4000)

    def brainrot_gyatt(self):
        lvl = random.randint(0, 100)
        self.status.showMessage(f"😳 Gyatt level: {lvl}%  ·  {'CERTIFIED 🦅' if lvl > 67 else 'mid 💀'}", 4000)

    def brainrot_sigma_quote(self):
        QMessageBox.information(self, "🗿 Сигма-цитата", random.choice(SIGMA_QUOTES))

    def brainrot_aura_farm(self):
        gain = random.randint(50, 670)
        self.aura = getattr(self, 'aura', 0) + gain
        self._refresh_aura_label()
        self.zoomer_burst(f"🌀 AURA FARM +{gain}")

    def brainrot_glaze(self):
        self.zoomer_burst("🫧 ты лютый чад, не слушай хейтеров")
        self.status.showMessage("🫧 glazing... ты W, ты сигма, ты 67 🤙", 4000)

    # ---------- Режим Палестины / страдания ----------
    def enable_suffer_mode(self, *args, **kwargs):
        """Включает чёрный квадрат страдания. Навсегда (если confirm)."""
        confirm = kwargs.get("confirm", True)
        if confirm:
            ans = QMessageBox.warning(
                self, "Режим Палестины",
                "Сейчас включится ЧЁРНЫЙ КВАДРАТ поверх браузера.\n\n"
                "Он применяется НАВСЕГДА (переживёт перезапуск).\n"
                "Единственный выход — отстрадать: кликнуть по нему 67 раз.\n\n"
                "Точно страдать?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        self.suffer_mode = True
        self.save_settings()
        if self.suffer_overlay is None:
            self.suffer_overlay = SufferOverlay(self)
        self._position_suffer_overlay()
        self.suffer_overlay.show()
        self.suffer_overlay.raise_()

    def disable_suffer_mode(self):
        """Отстрадал — снимаем квадрат."""
        self.suffer_mode = False
        self.save_settings()
        if self.suffer_overlay is not None:
            try:
                self.suffer_overlay.hide()
                self.suffer_overlay.deleteLater()
            except Exception:
                pass
            self.suffer_overlay = None
        try:
            QMessageBox.information(self, "Свобода", "Ты отстрадал. На этот раз. 🕊️")
        except Exception:
            pass

    def _position_suffer_overlay(self):
        if self.suffer_overlay is None:
            return
        try:
            # Накрываем центральную область (веб-контент).
            central = self.centralWidget()
            if central is not None:
                geo = central.geometry()
                self.suffer_overlay.setGeometry(geo)
            else:
                self.suffer_overlay.setGeometry(self.rect())
            self.suffer_overlay.raise_()
        except Exception:
            pass

    # ---------- ПИЗДЕЦ-режим (хаос) ----------
    def shake_window(self, ticks=20):
        """Трясёт окно ~1 сек и возвращает на место."""
        try:
            if self._shake_timer is not None:
                return
            origin = self.pos()
            state = {"n": 0}
            self._shake_timer = QTimer(self)

            def _tick():
                state["n"] += 1
                if state["n"] > ticks:
                    self._shake_timer.stop()
                    self._shake_timer = None
                    self.move(origin)
                    return
                dx = random.randint(-14, 14)
                dy = random.randint(-14, 14)
                self.move(origin.x() + dx, origin.y() + dy)

            self._shake_timer.timeout.connect(_tick)
            self._shake_timer.start(35)
        except Exception:
            pass

    def matrix_rain(self):
        try:
            ov = MatrixOverlay(self)
            self._chaos_overlays = [o for o in self._chaos_overlays if o.isVisible()]
            self._chaos_overlays.append(ov)
        except Exception:
            pass

    def fake_bsod(self):
        try:
            ov = BsodOverlay(self)
            ov.showFullScreen()
            self._chaos_overlays.append(ov)
        except Exception:
            pass

    def jumpscare(self):
        try:
            ov = JumpscareOverlay(self)
            self._chaos_overlays.append(ov)
        except Exception:
            pass

    def self_destruct(self):
        """Кнопка самоуничтожения. Фейк, конечно. Ничего не ломает."""
        ans = QMessageBox.question(
            self, "💣 САМОУНИЧТОЖЕНИЕ",
            "Запустить самоуничтожение браузера?\n\n(на самом деле нет, но попугаю)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        for n in (3, 2, 1):
            self.status.showMessage(f"💣 Самоуничтожение через {n}...", 800)
        self.shake_window(30)
        QTimer.singleShot(2500, lambda: self.jumpscare())
        QTimer.singleShot(3300, lambda: self.zoomer_burst("ПОПАЛСЯ 🤣 ничего не взорвалось 🗿"))

    def set_chaos_mode(self, enabled):
        """ПИЗДЕЦ-режим: каждые ~2.5 сек случайное хаос-событие. Персист."""
        self.chaos_mode = bool(enabled)
        if self.chaos_mode:
            if self._chaos_timer is None:
                self._chaos_timer = QTimer(self)
                self._chaos_timer.timeout.connect(self._chaos_tick)
            self._chaos_timer.start(2500)
            self.zoomer_burst("💥 ПИЗДЕЦ-РЕЖИМ ВКЛЮЧЁН 💥🗿🔥")
        else:
            if self._chaos_timer is not None:
                self._chaos_timer.stop()
            try:
                self.setWindowTitle("EBLAN Browser 6.7")
            except Exception:
                pass
        self.save_settings()

    def _chaos_tick(self):
        events = [
            lambda: self.zoomer_burst(random.choice(BRAINROT_PHRASES)),
            lambda: self.shake_window(14),
            self.matrix_rain,
            self.jumpscare,
            lambda: self.status.showMessage(random.choice([
                "обновление винды 99% не выключай пк", "тебя засняли 📸",
                "вирус удаляет систему C:\\... шутка 🤡", "67 новых уведомлений 🔔",
            ]), 2200),
            lambda: self.setWindowTitle(random.choice([
                "EBLAN Browser 6.7 💀", "ТЫ ЕБЛАН 🗿", "six seven 🤙🤙🤙",
                "💥 ПИЗДЕЦ 💥", "обновись до 6.7 чмо",
            ])),
            lambda: setattr(self, "aura", getattr(self, "aura", 0) + 67) or self._refresh_aura_label(),
        ]
        random.choice(events)()

    # ---------- Фото-оверлей на весь интерфейс ----------
    def set_image_overlay(self, enabled):
        """Вращающееся пульсирующее фото поверх всего интерфейса. Персист."""
        self.image_overlay_on = bool(enabled)
        if self.image_overlay_on:
            if self.image_overlay is None:
                self.image_overlay = ImageOverlay(self)
            self._position_image_overlay()
            self.image_overlay.show()
            self.image_overlay.raise_()
        else:
            if self.image_overlay is not None:
                try:
                    self.image_overlay.hide()
                    self.image_overlay.deleteLater()
                except Exception:
                    pass
                self.image_overlay = None
        self.save_settings()

    def _position_image_overlay(self):
        if self.image_overlay is None:
            return
        try:
            self.image_overlay.setGeometry(self.geometry())
            self.image_overlay.raise_()
        except Exception:
            pass

    # ---------- ДИКИЙ режим (мигание + вращение) ----------
    def start_wild_mode(self):
        """Дикое мигание+вращение. Только после явного согласия в предупреждении."""
        if self.wild_overlay is not None:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("⚠️ ПРЕДУПРЕЖДЕНИЕ О ФОТОЧУВСТВИТЕЛЬНОСТИ")
        box.setText("ВНИМАНИЕ: дикое мигание и вращение")
        box.setInformativeText(
            "Сейчас включится РЕЗКОЕ МИГАНИЕ яркими цветами и быстрое вращение.\n\n"
            "Это может вызвать приступ у людей с фоточувствительной эпилепсией.\n"
            "Если у тебя или рядом есть склонные к приступам — НЕ ВКЛЮЧАЙ.\n\n"
            "В любой момент: клик мышью или клавиша ESC — мгновенный СТОП.\n"
            "Также эффект сам выключится через 15 секунд.\n\n"
            "Точно запустить? (по умолчанию — НЕТ)"
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.button(QMessageBox.StandardButton.Yes).setText("Да, я понимаю риск")
        box.button(QMessageBox.StandardButton.No).setText("Нет, не надо")
        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        self.wild_overlay = WildOverlay(self, on_stop=self._on_wild_stopped)
        try:
            self.wild_overlay.setGeometry(self.geometry())
            self.wild_overlay.show()
            self.wild_overlay.raise_()
            self.wild_overlay.activateWindow()
            self.wild_overlay.setFocus()
        except Exception:
            pass

        # Непрерывная тряска окна на время дикого режима.
        if self._wild_shake_timer is None:
            self._wild_shake_timer = QTimer(self)
            origin = self.pos()

            def _shake():
                try:
                    dx = random.randint(-18, 18); dy = random.randint(-18, 18)
                    self.move(origin.x() + dx, origin.y() + dy)
                except Exception:
                    pass
            self._wild_shake_timer.timeout.connect(_shake)
            self._wild_shake_timer._origin = origin
            self._wild_shake_timer.start(60)

    def _on_wild_stopped(self):
        self.wild_overlay = None
        if self._wild_shake_timer is not None:
            try:
                self._wild_shake_timer.stop()
                self.move(self._wild_shake_timer._origin)
            except Exception:
                pass
            self._wild_shake_timer = None

    def stop_wild_mode(self):
        if self.wild_overlay is not None:
            self.wild_overlay.stop()

    # ---------- Режим иноагента (.com/.org/.net) ----------
    def set_inoagent_mode(self, enabled):
        """Разрешает иностранные домены. Персист. С предупреждением при включении."""
        if enabled and not self.inoagent_mode:
            ans = QMessageBox.warning(
                self, "🕵️ Режим иноагента",
                "Сейчас откроется доступ к иностранным доменам "
                "(.com / .org / .net).\n\n"
                "⚠️ ВНИМАНИЕ: посещая вражеские сайты, ты автоматически "
                "становишься ИНОAГЕНТОМ.\n"
                "Тебя внесут в реестр, а потом ПОСАДЯТ. 🚔\n\n"
                "(Это шутка-пародия. Но домены реально откроются.)\n\n"
                "Точно стать иноагентом?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                # откатываем чекбокс
                try:
                    self.inoagent_action.setChecked(False)
                except Exception:
                    pass
                return
        self.inoagent_mode = bool(enabled)
        if self.inoagent_mode:
            for d in INOAGENT_TLDS:
                if d not in self.allowed_domains:
                    self.allowed_domains.append(d)
            self.status.showMessage("🕵️ Режим иноагента ВКЛ. Жди гостей 🚔", 5000)
        else:
            self.allowed_domains = [d for d in self.allowed_domains if d not in INOAGENT_TLDS]
            self.status.showMessage("Режим иноагента выкл. Ты снова патриот 🇷🇺", 4000)
        try:
            self.inoagent_action.setChecked(self.inoagent_mode)
        except Exception:
            pass
        self.save_settings()

    # ---------- Госреклама каждые 30 секунд ----------
    def set_ad_nag_mode(self, enabled):
        """Каждые 30 сек — полноэкранная реклама МАКС / «VPN убивает». Персист.

        ВАЖНО: отключить госрекламу НЕЛЬЗЯ. Попытка снять галку не выключает
        режим, а разворачивает наказание на весь экран.
        """
        if not enabled and getattr(self, 'ad_nag_mode', False):
            # «Нельзя отключить» — возвращаем галку и наказываем.
            try:
                self.ad_nag_action.setChecked(True)
            except Exception:
                pass
            self._show_ad_punish()
            return

        self.ad_nag_mode = bool(enabled)
        if self.ad_nag_mode:
            if self._ad_nag_timer is None:
                self._ad_nag_timer = QTimer(self)
                self._ad_nag_timer.timeout.connect(self._show_ad)
            self._ad_nag_timer.start(30000)  # каждые 30 секунд
            self.status.showMessage("📢 Госреклама активирована. Отключить нельзя 🤡", 4000)
        else:
            if self._ad_nag_timer is not None:
                self._ad_nag_timer.stop()
        try:
            self.ad_nag_action.setChecked(self.ad_nag_mode)
        except Exception:
            pass
        self.save_settings()

    def _show_ad_punish(self):
        """Полноэкранное наказание за попытку отключить госрекламу."""
        try:
            ov = AdOverlay(self, AD_PUNISH_CONTENT)
            ov.showFullScreen()
            ov.raise_()
            ov.activateWindow()
            self._ad_overlay = ov
        except Exception as e:
            print(f"[ad] punish: {e}")

    def _show_ad(self):
        # Не плодим окна: если предыдущее ещё открыто — пропускаем.
        if self._ad_overlay is not None and self._ad_overlay.isVisible():
            return
        content = random.choice(AD_NAG_CONTENTS)
        try:
            self._ad_overlay = AdOverlay(self, content)
            self._ad_overlay.showFullScreen()
            self._ad_overlay.raise_()
            self._ad_overlay.activateWindow()
        except Exception as e:
            print(f"[ad] {e}")

    def set_gamer_mode(self, enabled):
        """Включение/выключение геймерского режима с FPS-оверлеем."""
        if enabled and not self.is_unlocked("gamer"):
            self.require_feature("gamer")
            if not self.is_unlocked("gamer"):
                self.gamer_mode = False
                return
        self.gamer_mode = bool(enabled)
        if self.gamer_mode:
            if self.fps_overlay is None:
                self.fps_overlay = FPSOverlay(self)
                self._position_fps_overlay()
            self.fps_overlay.show()
            self.fps_overlay.raise_()
            try:
                self.status.showMessage("EBLAN SoftBoost™ активирован!!11", 4000)
            except Exception:
                pass
        else:
            if self.fps_overlay is not None:
                try:
                    self.fps_overlay.stop()
                except Exception:
                    pass
                self.fps_overlay = None

    def _position_fps_overlay(self):
        if self.fps_overlay is None:
            return
        try:
            g = self.geometry()
            x = g.x() + g.width() - self.fps_overlay.width() - 20
            y = g.y() + 80
            self.fps_overlay.move(max(0, x), max(0, y))
        except Exception:
            pass

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.fps_overlay is not None and self.fps_overlay.isVisible():
            self._position_fps_overlay()
        if getattr(self, 'image_overlay', None) is not None:
            self._position_image_overlay()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fps_overlay is not None and self.fps_overlay.isVisible():
            self._position_fps_overlay()
        if getattr(self, 'suffer_overlay', None) is not None:
            self._position_suffer_overlay()
        if getattr(self, 'image_overlay', None) is not None:
            self._position_image_overlay()

    # ------------ Счётчик «Сколько времени проебал» ------------

    def _current_wasted_total(self):
        try:
            return int(self.total_wasted_seconds + max(0, time.time() - self.session_start))
        except Exception:
            return int(self.total_wasted_seconds or 0)

    def _refresh_wasted_label(self):
        try:
            total = self._current_wasted_total()
            level, _ = wasted_level(total)
            self.wasted_label.setText(f"Проёбано: {format_wasted(total)}  ·  {level}")
        except Exception:
            pass

    def _refresh_vpn_label(self):
        try:
            vc = getattr(self, 'vless_controller', None)
            if vc is None:
                self.vpn_label.setText("VPN: off")
                return
            if vc.is_connected() and 0 <= vc.active_server_idx < len(vc.servers):
                s = vc.servers[vc.active_server_idx]
                name = s.name or s.host
                self.vpn_label.setText(f"VPN: {name}")
            else:
                self.vpn_label.setText("VPN: off")
        except Exception:
            pass

    def reset_wasted(self):
        confirm = QMessageBox.question(
            self,
            "Обнулить счётчик?",
            "Уверен что хочешь обнулить? Прожитое не вернёшь, но цифру — да.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.total_wasted_seconds = 0
            self.session_start = time.time()
            self._refresh_wasted_label()
            try:
                self.save_settings()
            except Exception:
                pass
            QMessageBox.information(self, "Готово", "Счётчик обнулён. Начинаем проёбывать заново.")

    # ------------ EBLAN ID (синхронизация настроек) ------------

    # Настройки, которые не надо тянуть между машинами
    # (в т.ч. пути к бинарям и папкам — они на другой системе не валидны).
    _EBLANID_SKIP_KEYS = {
        "downloads_folder",
        "vless_xray_bin",
    }
    _EBLANID_PREFIX = "ebl_"

    def _collect_settings_payload(self):
        """Собирает настройки точно так же, как save_settings, но не трогает диск."""
        payload = {
            "subscription_level": self.subscription_level,
            "update_branch": self.update_branch,
            "enable_eblan_ai": self.enable_eblan_ai,
            "history_enabled": getattr(self, 'history_enabled', True),
            "downloads_folder": getattr(self, 'downloads_folder', get_downloads_path()),
            "require_eblan_id": getattr(self, 'require_eblan_id', False),
            "gamer_mode": getattr(self, 'gamer_mode', False),
            "total_wasted_seconds": int(getattr(self, 'total_wasted_seconds', 0) or 0),
            "ecss_theme": getattr(self, 'ecss_theme', "") or "",
            "update_api_base": getattr(self, 'update_api_base', ""),
            "ai_server": getattr(self, 'ai_server', ""),
            "ai_key": getattr(self, 'ai_key', ""),
            "ai_model": getattr(self, 'ai_model', ""),
        }
        try:
            if getattr(self, 'vless_controller', None) is not None:
                payload.update(self.vless_controller.dump_to_settings())
        except Exception:
            pass
        return payload

    def export_eblanid(self):
        """Упаковывает текущие настройки в компактный ключ `ebl_<base64>`."""
        import zlib
        payload = self._collect_settings_payload()
        # Выкидываем машинозависимые поля
        for k in self._EBLANID_SKIP_KEYS:
            payload.pop(k, None)
        meta = {
            "v": 1,
            "created_at": int(time.time()),
            "app": "EBLAN",
        }
        blob = {"meta": meta, "data": payload}
        raw = json.dumps(blob, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        packed = zlib.compress(raw, 9)
        b64 = base64.urlsafe_b64encode(packed).decode("ascii").rstrip("=")
        return self._EBLANID_PREFIX + b64

    def import_eblanid(self, key):
        """Применяет настройки из ключа. Возвращает (ok, message)."""
        import zlib
        if not key:
            return False, "Пустой ключ"
        key = key.strip().replace("\n", "").replace("\r", "").replace(" ", "")
        if not key.startswith(self._EBLANID_PREFIX):
            return False, f"Ключ должен начинаться с '{self._EBLANID_PREFIX}'"
        body = key[len(self._EBLANID_PREFIX):]
        try:
            padded = body + "=" * (-len(body) % 4)
            packed = base64.urlsafe_b64decode(padded.encode("ascii"))
            raw = zlib.decompress(packed)
            blob = json.loads(raw.decode("utf-8"))
        except Exception as e:
            return False, f"Не удалось разобрать ключ: {e}"

        if not isinstance(blob, dict) or "data" not in blob:
            return False, "Неверный формат ключа"
        data = blob.get("data") or {}
        if not isinstance(data, dict):
            return False, "В ключе нет настроек"

        # Применяем по одному полю, максимально мягко
        self.subscription_level = data.get("subscription_level", self.subscription_level)
        self.update_branch = data.get("update_branch", self.update_branch)
        self.enable_eblan_ai = bool(data.get("enable_eblan_ai", self.enable_eblan_ai))
        self.history_enabled = bool(data.get("history_enabled", getattr(self, 'history_enabled', True)))
        self.require_eblan_id = bool(data.get("require_eblan_id", getattr(self, 'require_eblan_id', False)))
        self.gamer_mode = bool(data.get("gamer_mode", getattr(self, 'gamer_mode', False)))
        try:
            self.total_wasted_seconds = int(data.get("total_wasted_seconds",
                                                     getattr(self, 'total_wasted_seconds', 0)) or 0)
        except Exception:
            pass
        if "update_api_base" in data and data["update_api_base"]:
            self.update_api_base = data["update_api_base"]
            try:
                self.update_service.api_base_url = self.update_api_base
            except Exception:
                pass
        self.ai_server = data.get("ai_server", self.ai_server)
        self.ai_key = data.get("ai_key", self.ai_key)
        self.ai_model = data.get("ai_model", self.ai_model)

        # Тема
        if "ecss_theme" in data:
            try:
                self.apply_ecss_theme(data.get("ecss_theme") or "")
            except Exception:
                pass

        # VLESS — перезаливаем весь контроллер (без bin_path/портов, их не экспортим)
        try:
            if getattr(self, 'vless_controller', None) is not None:
                # Подсунем данные в формате load_from_settings
                vless_data = {
                    "vless_subscriptions": data.get("vless_subscriptions", []),
                    "vless_servers_cache": data.get("vless_servers_cache", []),
                    "vless_socks_port": data.get("vless_socks_port",
                                                 self.vless_controller.xray_manager.socks_port),
                    "vless_http_port": data.get("vless_http_port",
                                                self.vless_controller.xray_manager.http_port),
                }
                # Сбросить текущий список, чтобы новый подгрузился поверх
                self.vless_controller.servers = []
                self.vless_controller.load_from_settings(vless_data)
        except Exception as e:
            print(f"[eblanid] vless import: {e}")

        # UI-обновления, которые зависят от флагов
        try:
            if hasattr(self, 'ai_action'):
                self.ai_action.setEnabled(self.enable_eblan_ai)
        except Exception:
            pass
        try:
            self._refresh_vpn_label()
        except Exception:
            pass

        self.save_settings()
        return True, f"Настройки применены. Полей: {len(data)}"

    # ------------ Ecss ------------

    def apply_ecss_theme(self, source):
        self.ecss_theme = source or ""
        try:
            EcssEngine.apply(self.ecss_theme)
        except Exception as e:
            print(f"[Ecss] apply error: {e}")
        # Пробежаться по открытым окнам и снять их локальный QSS, если тема активна,
        # либо вернуть дефолтный QSS SettingsDialog, если тема пуста.
        try:
            app = QApplication.instance()
            if app is None:
                return
            has_theme = bool(self.ecss_theme.strip())
            for w in app.topLevelWidgets():
                if w is self:
                    continue
                try:
                    if has_theme:
                        if w.styleSheet():
                            w.setStyleSheet("")
                    else:
                        if isinstance(w, SettingsDialog):
                            w.setStyleSheet(w._build_qss(w._detect_dark_theme()))
                except Exception:
                    pass
        except Exception:
            pass

    # ------------ Навигация по настройкам ------------

    def open_settings_to(self, section_name):
        try:
            dlg = SettingsDialog(
                self.enable_eblan_ai,
                self.subscription_level,
                self.update_branch,
                main_window=self
            )
            try:
                for i in range(dlg.nav.count()):
                    if dlg.nav.item(i).text() == section_name:
                        dlg.nav.setCurrentRow(i)
                        break
            except Exception:
                pass
            if dlg.exec():
                self._consume_settings_dialog(dlg)
        except Exception as e:
            print(f"[open_settings_to] {e}")

    # ------------ Обновления (через UpdateService) ------------

    def check_for_updates(self, interactive=False):
        """
        Запрашивает манифест с бэкенда. `interactive=True` — показать
        диалог «нет обновлений», когда всё актуально.
        """
        self._updates_interactive = bool(interactive)
        eb_debug("upd", f"проверка обновлений (interactive={interactive}) → {self.update_service.api_base_url}")
        if not self.update_service.api_base_url:
            if interactive:
                QMessageBox.warning(self, "Обновления",
                                    "API сервера обновлений не настроен.\nНастройки → Обновления.")
            return
        self.update_service.fetch_manifest()

    def _on_manifest_loaded(self, ok, data, err):
        """Колбек UpdateService.manifestLoaded."""
        interactive = getattr(self, "_updates_interactive", False)
        self._updates_interactive = False

        if not ok:
            print(f"[updates] ошибка: {err}")
            if interactive:
                QMessageBox.critical(self, "Обновления",
                                     f"Не удалось связаться с сервером обновлений:\n{err}")
            return

        self.last_manifest = data
        self.rollback_data = data.get("rollback") or []

        info = (data.get("branches") or {}).get(self.update_branch)
        if not info:
            if interactive:
                QMessageBox.information(self, "Обновления",
                                        f"На ветке «{self.update_branch}» ничего не опубликовано.")
            return

        if info.get("version") == self.current_version:
            if interactive:
                QMessageBox.information(self, "Обновления",
                                        f"У тебя последняя версия: {self.current_version}.")
            return

        dlg = UpdateDialog2(self.current_version, info, self)
        if info.get("force", False):
            dlg.setModal(True)
        dlg.exec()

    def closeEvent(self, event):
        # Сохраняем «проёбанное» время
        try:
            elapsed = max(0, int(time.time() - self.session_start))
            self.total_wasted_seconds = int(self.total_wasted_seconds or 0) + elapsed
            self.session_start = time.time()
            self.save_settings()
        except Exception:
            pass
        if self.fps_overlay is not None:
            try:
                self.fps_overlay.stop()
            except Exception:
                pass
            self.fps_overlay = None
        # Корректно гасим xray-процесс, если он был запущен.
        # active-состояние в vless_state.json оставляем — чтобы при следующем
        # запуске VLESS снова поднялся автоматически.
        try:
            if hasattr(self, 'vless_controller') and self.vless_controller is not None:
                if self.vless_controller.xray_manager.is_running():
                    self.vless_controller.xray_manager.stop()
        except Exception:
            pass
        super().closeEvent(event)

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "открыть файл", "",
                                                  "Хтмлы (*.htm *.html);;"
                                                  "другое (*.*)")
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    html = f.read()
                self.tabs.currentWidget().setHtml(html)
                self.urlbar.setText(filename)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось открыть файл: {e}")

    def save_file(self):
        filename, _ = QFileDialog.getSaveFileName(self, "сохранить как", "",
                                                  "хтмлы (*.htm *.html);;"
                                                  "другое (*.*)")
        if filename:
            try:
                def _write_html(html_text, path):
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(html_text)

                page = self.tabs.currentWidget().page()
                def callback(html):
                    try:
                        _write_html(html, filename)
                    except Exception as e:
                        QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить файл: {e}")

                page.toHtml(callback)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить файл: {e}")

    def print_page(self):
        dlg = QPrintPreviewDialog()
        dlg.paintRequested.connect(lambda printer: self.tabs.currentWidget().page().print(printer, lambda success: None))
        dlg.exec()

    def navigate_home(self):
        eb_debug("nav", "домой → https://ya.ru/")
        self.tabs.currentWidget().setUrl(QUrl("https://ya.ru/"))
        self.earn_for_action("домой")

    def navigate_to_url(self):
        url_text = self.urlbar.text()
        eb_debug("nav", f"переход по адресной строке: {url_text!r}")
        q = QUrl(url_text)
        if q.scheme() == "":
            q.setScheme("https")

        domain = q.host().lower()
        if domain in self.blocked_domains or f"www.{domain}" in self.blocked_domains:
            QMessageBox.warning(self, "Антивирус СОСНИ!", "Сайт распространяет дезинформацию, нарушает законы нескольких стран.")
            self.tabs.currentWidget().setUrl(QUrl("https://ya.ru/"))
            return
        elif domain in self.special_domains or f"www.{domain}" in self.special_domains:
            QMessageBox.information(self, "Предупреждение", "Сайт от больного ДЦП, относитесь с уважением.")
        elif domain in self.allowed_exceptions or f"www.{domain}" in self.allowed_exceptions:
            if domain != 'sites.google.com' and f"www.{domain}" != 'sites.google.com':
                QMessageBox.warning(self, "Антивирус СОСНИ!", "Доступ к этому сайту разрешен как исключение, но он не соответствует политике безопасности.")

        if not self.is_allowed_domain(url_text):
            QMessageBox.warning(self, "Антивирус СОСНИ!", "Во избежание пропаганды доступ только к сайтам с доменами .ru, .su, .by или к разрешенным сайтам (например, vk.com)!")
            return

        self.tabs.currentWidget().setUrl(q)
        self.earn_for_action("переход")

    def update_urlbar(self, q, browser=None):
        if browser != self.tabs.currentWidget():
            return
        if q.scheme() == 'https':
            self.httpsicon.setPixmap(QPixmap(os.path.join('images', 'lock-ssl.png')))
        else:
            self.httpsicon.setPixmap(QPixmap(os.path.join('images', 'lock-nossl.png')))
        self.urlbar.setText(q.toString())
        self.urlbar.setCursorPosition(0)

    def start_download_and_install(self, url, new_version, progress_bar=None):
        if self.download_reply:
            self.download_reply.abort()
            self.download_reply.deleteLater()

        temp_zip = os.path.join(tempfile.gettempdir(), "eblan_update.zip")
        if os.path.exists(temp_zip):
            os.remove(temp_zip)

        request = QNetworkRequest(QUrl(url))
        self.download_reply = self.network_manager.get(request)

        file = QFile(temp_zip)
        if not file.open(QIODeviceBase.OpenModeFlag.WriteOnly):
            QMessageBox.critical(self, "Ошибка", "Не удалось создать временный файл.")
            return

        total = 0
        content_length = 0

        header = self.download_reply.rawHeader(b"Content-Length")
        if header:
            content_length = int(bytes(header).decode())

        if progress_bar and content_length:
            progress_bar.setMaximum(content_length)
            progress_bar.setValue(0)

        def on_data():
            nonlocal total
            data = self.download_reply.readAll()
            total += len(data)
            file.write(data)

            if progress_bar and content_length:
                progress_bar.setValue(total)

        def on_finished():
            file.close()

            if self.download_reply.error() != QNetworkReply.NetworkError.NoError:
                QMessageBox.critical(self, "Ошибка", self.download_reply.errorString())
                self.download_reply.deleteLater()
                return

            status_code = self.download_reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if status_code != 200:
                QMessageBox.critical(self, "Ошибка", f"HTTP ошибка: {status_code}")
                self.download_reply.deleteLater()
                return

            if content_length and total != content_length:
                QMessageBox.critical(self, "Ошибка", "Файл скачан не полностью.")
                self.download_reply.deleteLater()
                return

            current_dir = os.path.abspath(
                os.path.dirname(sys.executable)
                if getattr(sys, 'frozen', False)
                else os.path.dirname(__file__)
            )

            backup_dir = os.path.join(current_dir, "backup_last")
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir)
            shutil.copytree(current_dir, backup_dir, dirs_exist_ok=True)

            try:
                with zipfile.ZipFile(temp_zip) as z:
                    z.extractall(current_dir)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не распаковалось:\n{e}")
                self.download_reply.deleteLater()
                return

            QMessageBox.information(
                self,
                "Готово",
                f"Версия {new_version} установл��на.\nПерезапуск..."
            )

            self.download_reply.deleteLater()

            if getattr(sys, 'frozen', False):
                os.startfile(sys.executable)
            else:
                os.startfile(__file__)

            QApplication.quit()

        self.download_reply.readyRead.connect(on_data)
        self.download_reply.finished.connect(on_finished)

    def show_rollback_dialog(self):
        if not self.rollback_data:
            QMessageBox.warning(self, "Ой", "Список старых версий ещё не загрузился")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("↩ Откат на старую версию")
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Откатится можно только на версии которые поддерживаются\nНа остальных скачивайте отдельно с архива"))

        listw = QListWidget()
        for item in self.rollback_data:
            name = item.get("name", item["version"])
            listw.addItem(f"{name} → {item['version']}")
        layout.addWidget(listw)

        btn = QPushButton("Скачать и откатиться")
        def do_it():
            idx = listw.currentRow()
            if idx < 0:
                return
            ver = self.rollback_data[idx]["version"]
            url = f"https://twgood.serv00.net/browser/dl/Eblan_{ver}.zip"
            QMessageBox.information(dlg, "Пошло", f"Качаем {ver}...")
            self.start_download_and_install(url, ver)
            dlg.accept()
        btn.clicked.connect(do_it)
        layout.addWidget(btn)
        dlg.exec()

    def show_extension_details(self, ext):
        """Open detailed view of extension"""
        dlg = QDialog(self)
        dlg.setWindowTitle(f"📦 {ext['meta'].get('name', 'Unknown')}")
        dlg.setMinimumSize(700, 600)
        
        layout = QVBoxLayout(dlg)
        
        # Header with name and version
        header_layout = QHBoxLayout()
        title = QLabel(f"<h2>{ext['meta'].get('name', 'Unknown')}</h2>")
        version_label = QLabel(f"<b>v{ext['meta'].get('version', '?')}</b>")
        version_label.setStyleSheet("color: #0e639c;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(version_label)
        layout.addLayout(header_layout)
        
        # Metadata
        meta_group = QGroupBox("📋 Информация")
        meta_layout = QFormLayout()
        
        meta_layout.addRow("Название:", QLabel(ext['meta'].get('name', 'Unknown')))
        meta_layout.addRow("Версия:", QLabel(ext['meta'].get('version', '?')))
        meta_layout.addRow("Автор:", QLabel(ext['meta'].get('author', 'Unknown')))
        meta_layout.addRow("Описание:", QLabel(ext['meta'].get('description', '(нет описания)')))
        meta_layout.addRow("Файл:", QLabel(ext['filename']))
        meta_layout.addRow("Путь:", QLabel(ext['path']))
        
        meta_group.setLayout(meta_layout)
        layout.addWidget(meta_group)
        
        # Tabs for code
        tabs = QTabWidget()
        
        # JavaScript tab
        js_tab = QTextEdit()
        js_tab.setPlainText(ext['js'] if ext['js'] else "(нет кода)")
        js_tab.setReadOnly(True)
        js_tab.setFont(QFont('Courier New', 9))
        tabs.addTab(js_tab, ">_ JavaScript")
        
        # CSS tab
        css_tab = QTextEdit()
        css_tab.setPlainText(ext['css'] if ext['css'] else "(нет стилей)")
        css_tab.setReadOnly(True)
        css_tab.setFont(QFont('Courier New', 9))
        tabs.addTab(css_tab, "🎨 CSS")
        
        layout.addWidget(QLabel("📝 Код расширения:"))
        layout.addWidget(tabs)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        edit_btn = QPushButton("✏️ Редактировать")
        def edit_extension():
            import subprocess
            try:
                subprocess.Popen(['notepad', ext['path']])
            except:
                QMessageBox.warning(dlg, "Ошибка", "Не удалось открыть файл в редакторе")
        edit_btn.clicked.connect(edit_extension)
        btn_layout.addWidget(edit_btn)
        
        reload_btn = QPushButton("🔄 Перезагрузить")
        def reload_single_ext():
            parsed = parse_eblp_file(ext['path'])
            if parsed and parsed['meta']:
                # Find and update extension
                for i, e in enumerate(self.extensions):
                    if e['filename'] == ext['filename']:
                        self.extensions[i] = {
                            'filename': ext['filename'],
                            'path': ext['path'],
                            'meta': parsed['meta'],
                            'js': parsed['js'],
                            'css': parsed['css'],
                            'enabled': True
                        }
                        QMessageBox.information(dlg, "Успешно", "Расширение перезагружено!")
                        dlg.close()
                        return
            QMessageBox.warning(dlg, "Ошибка", "Не удалось перезагрузить расширение")
        reload_btn.clicked.connect(reload_single_ext)
        btn_layout.addWidget(reload_btn)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(dlg.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        dlg.exec()

    def show_extensions_manager(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Управление расширениями")
        dlg.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(dlg)
        
        layout.addWidget(QLabel("📦 Установленные расширения:"))
        
        ext_list = QListWidget()
        
        if self.extensions:
            for ext in self.extensions:
                name = ext['meta'].get('name', 'Unknown')
                version = ext['meta'].get('version', '?')
                author = ext['meta'].get('author', 'Unknown')
                item_text = f"✓ {name} v{version} by {author}"
                ext_list.addItem(item_text)
        else:
            ext_list.addItem("(Расширения не установлены)")
            ext_list.item(0).setFlags(ext_list.item(0).flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
        
        layout.addWidget(ext_list)
        
        btn_layout = QHBoxLayout()
        
        open_folder_btn = QPushButton("📂 Открыть папку расширений")
        def open_extensions_folder():
            ext_path = get_extensions_path()
            QDesktopServices.openUrl(QUrl.fromLocalFile(ext_path))
        open_folder_btn.clicked.connect(open_extensions_folder)
        btn_layout.addWidget(open_folder_btn)
        
        reload_btn = QPushButton("🔄 Перезагрузить")
        def reload_extensions():
            self.extensions = load_extensions(self)
            QMessageBox.information(dlg, "Успешно", f"Загружено {len(self.extensions)} расширений")
        reload_btn.clicked.connect(reload_extensions)
        btn_layout.addWidget(reload_btn)
        
        layout.addLayout(btn_layout)
        
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setMaximumHeight(120)
        help_text.setText("""
Структура файла .eblp:

JS
console.log('Hello from extension!');

---

Meta
name: My Extension
version: 1.0.0
author: Your Name

---

CSS
body { background: #f0f0f0; }
        """.strip())
        
        layout.addWidget(QLabel("📝 Структура расширения:"))
        layout.addWidget(help_text)
        
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        
        dlg.exec()


# ============================================================
#   Логин EBLAN ID аккаунта (БЕЗ ПАРОЛЯ — только email + код).
# ============================================================
EB_DEBUG = False
_EB_QT_HANDLER_INSTALLED = False


def eb_log(tag: str, msg: str):
    """Важные события — печатаются всегда: [время] [tag] сообщение."""
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [{tag}] {msg}", flush=True)
    except Exception:
        pass


def eb_debug(tag: str, msg: str):
    """Подробный лог — печатается ТОЛЬКО при включённой «Отладке»."""
    if EB_DEBUG:
        eb_log(f"debug:{tag}", msg)


def _eb_qt_message_handler(mode, context, message):
    """Перенаправляем внутренние сообщения Qt/WebEngine в наш лог."""
    try:
        eb_log("qt", str(message))
    except Exception:
        pass


def set_debug_mode(enabled: bool, announce: bool = True):
    """Включает/выключает глобальный режим отладки на лету.

    При включении: подробные правила логирования Qt/WebEngine + перехват
    Qt-сообщений + флаг EB_DEBUG (его проверяет eb_debug по всему коду)."""
    global EB_DEBUG, _EB_QT_HANDLER_INSTALLED
    EB_DEBUG = bool(enabled)
    try:
        if EB_DEBUG:
            QLoggingCategory.setFilterRules("*.debug=true")
            if not _EB_QT_HANDLER_INSTALLED:
                qInstallMessageHandler(_eb_qt_message_handler)
                _EB_QT_HANDLER_INSTALLED = True
        else:
            QLoggingCategory.setFilterRules("")
            if _EB_QT_HANDLER_INSTALLED:
                qInstallMessageHandler(None)
                _EB_QT_HANDLER_INSTALLED = False
    except Exception:
        pass
    if announce:
        eb_log("debug", "режим отладки ВКЛЮЧЁН — логов будет дохуя"
               if EB_DEBUG else "режим отладки выключен")


class AccountLoginDialog(QDialog):
    """Логин/регистрация EBLAN ID аккаунта через email + 6-значный код."""

    def __init__(self, api_base: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EBLAN ID — Вход")
        self.resize(380, 260)
        self._api_base = (api_base or "https://update.riba.click/eb/upd/public/index.php").rstrip("/")
        self.result_token = None
        self.result_account = None
        self._pending_email = ""

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        root.addWidget(QLabel("Введи email — на него придёт 6-значный код:"))

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("твоя@почта.com")
        root.addWidget(self.email_input)

        self.send_code_btn = QPushButton("Отправить код")
        self.send_code_btn.clicked.connect(self._send_code)
        root.addWidget(self.send_code_btn)

        # Виджет для ввода кода (скрыт до отправки)
        self.code_widget = QWidget()
        self.code_widget.setVisible(False)
        code_layout = QVBoxLayout(self.code_widget)
        code_layout.setContentsMargins(0, 8, 0, 0)
        code_layout.setSpacing(8)

        code_layout.addWidget(QLabel("Код из письма:"))
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("123456")
        self.code_input.setMaxLength(6)
        code_layout.addWidget(self.code_input)

        self.confirm_btn = QPushButton("Войти")
        self.confirm_btn.clicked.connect(self._confirm_code)
        code_layout.addWidget(self.confirm_btn)

        root.addWidget(self.code_widget)

        self.status_label = QLabel("")
        root.addWidget(self.status_label)

        root.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Отмена")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)
        root.addLayout(btn_layout)

    def _set_status(self, text: str, error: bool = False):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color:{'#d70022' if error else '#0a0'};" if text else "")

    def _send_code(self):
        email = (self.email_input.text() or "").strip()
        if not email or "@" not in email:
            eb_log("login", f"некорректный email отклонён: {email!r}")
            self._set_status("Введи корректный email", error=True)
            return

        self._pending_email = email
        eb_log("login", f"→ auth_start: запрашиваю код на {email}")
        # Сразу показываем поле ввода кода и НЕ ждём ответа сервера: письмо
        # приходит, а HTTP-ответ может задержаться/зависнуть — клиент не должен
        # из-за этого блокироваться. Реальные отказы покажем в _on_code_sent.
        self._set_status("Код отправлен — проверь почту")
        self.code_widget.setVisible(True)
        self.code_input.setFocus()
        self.send_code_btn.setText("Отправить заново")
        self.send_code_btn.setEnabled(True)
        self.email_input.setEnabled(False)

        def _go():
            url = f"{self._api_base}?route=auth_start"
            try:
                r = eb_api_request(url, {"email": email}, timeout=10)
                eb_log("login", f"auth_start HTTP {r.status_code} ({len(r.content)} байт)")
                data = r.json() if r.status_code in (200, 400) else {"ok": False, "error": r.text}
            except Exception as e:
                eb_log("login", f"auth_start сетевая ошибка: {e}")
                data = {"ok": False, "error": str(e)}
            QtCore.QTimer.singleShot(0, lambda: self._on_code_sent(data))

        threading.Thread(target=_go, daemon=True).start()

    def _on_code_sent(self, data: dict):
        # Поле кода уже показано в _send_code — здесь его НЕ прячем (код мог уйти
        # на почту даже при отказе вроде too_many_requests). Только статус.
        if data.get("ok"):
            is_new = data.get("is_new", False)
            eb_log("login", f"✓ код отправлен на {self._pending_email} (новый аккаунт={is_new})")
            self._set_status("Код отправлен! (новый аккаунт)" if is_new else "Код отправлен!")
            return
        err = data.get("error", "неизвестная ошибка")
        eb_log("login", f"✗ auth_start отказ: {err}")
        if err == "ip_limit_reached":
            self._set_status("Ошибка: с этого IP уже есть аккаунт", error=True)
        elif err == "invalid_email":
            # Email явно битый — прячем поле кода и даём исправить адрес.
            self.code_widget.setVisible(False)
            self.email_input.setEnabled(True)
            self._set_status("Ошибка: некорректный email", error=True)
        elif err == "mail_failed":
            self._set_status("Ошибка: не удалось отправить письмо", error=True)
        elif err == "too_many_requests":
            # Код уже отправляли недавно — он ещё действителен, вводи его.
            self._set_status("Код уже отправлен ранее — введи его из письма")
        else:
            self._set_status(f"Ошибка: {err}", error=True)

    def _confirm_code(self):
        code = (self.code_input.text() or "").strip()
        if len(code) != 6 or not code.isdigit():
            eb_log("login", f"код отклонён локально (длина={len(code)}, цифры={code.isdigit()})")
            self._set_status("Код должен быть 6 цифр", error=True)
            return

        eb_log("login", f"→ auth_complete: проверяю код для {self._pending_email} (6 цифр)")
        self._set_status("Проверяю...")
        self.confirm_btn.setEnabled(False)
        self.code_input.setEnabled(False)

        def _go():
            url = f"{self._api_base}?route=auth_complete"
            try:
                r = eb_api_request(url, {"email": self._pending_email, "code": code}, timeout=10)
                eb_log("login", f"auth_complete HTTP {r.status_code} ({len(r.content)} байт)")
                data = r.json() if r.status_code in (200, 400, 401) else {"ok": False, "error": r.text}
            except Exception as e:
                eb_log("login", f"auth_complete сетевая ошибка: {e}")
                data = {"ok": False, "error": str(e)}
            QtCore.QTimer.singleShot(0, lambda: self._on_auth_complete(data))

        threading.Thread(target=_go, daemon=True).start()

    def _on_auth_complete(self, data: dict):
        self.confirm_btn.setEnabled(True)
        self.code_input.setEnabled(True)
        if data.get("ok"):
            self.result_token = data.get("token")
            self.result_account = data.get("account")
            email = (self.result_account or {}).get("email", "?")
            acc_id = (self.result_account or {}).get("id", "?")
            eb_log("login", f"✓ вход выполнен: {email} (id={acc_id}), токен получен (len={len(self.result_token or '')})")
            self._set_status(f"Привет, {email}!")
            QMessageBox.information(
                self,
                "АХУЕТЬ ТЫ ВОШЕЛ!!!!",
                f"Ты вошёл как {email}!\n\n"
                "Теперь ты можешь синхронизировать настройки "
                "между устройствами!!!!!!",
            )
            self.accept()
        else:
            err = data.get("error", "неизвестная ошибка")
            eb_log("login", f"✗ auth_complete отказ: {err}"
                   + (f" / {data.get('reason')}" if data.get("reason") else ""))
            if err == "invalid_code":
                err = "Неверный код"
            elif err == "too_many_attempts":
                err = "Слишком много попыток — запроси код заново"
            elif err == "account_banned":
                reason = data.get("reason", "")
                err = f"Аккаунт забанен: {reason}" if reason else "Аккаунт забанен"
            self._set_status(f"Ошибка: {err}", error=True)


# ============================================================
#   Анонимный режим (инкогнито).
#
#   - Использует off-the-record QWebEngineProfile (никаких куки/кеша/истории)
#   - Стартовая страница — Murena Qwant (https://murena.qwant.com)
#   - Минимальный UI: назад/вперёд/перезагрузка/URL-бар, без статистики
#     «времени проёба», без AI и без VLESS-индикаторов
# ============================================================
class IncognitoWindow(QMainWindow):
    """Отдельное приватное окно, не связанное с основным профилем."""

    def __init__(self, start_url: str = INCOGNITO_HOMEPAGE):
        super().__init__()
        self.setWindowTitle("EBLAN Browser — Анонимный режим")
        try:
            self.setWindowIcon(QIcon(os.path.join('images', 'ma-icon-64.png')))
        except Exception:
            pass
        self.resize(1100, 760)

        # Off-the-record профиль: имя НЕ задаём — это ключ к OTR-режиму.
        self._profile = QWebEngineProfile(self)
        self._profile.setHttpUserAgent(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        # Без сохранения cookies/кеша на диск.
        try:
            self._profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            )
            self._profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
            self._profile.setPersistentStoragePath("")
            self._profile.setCachePath("")
        except Exception:
            pass

        self._view = QWebEngineView(self)
        page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(page)

        # Тулбар
        navtb = QToolBar("Anon Navigation")
        navtb.setIconSize(QtCore.QSize(16, 16))
        self.addToolBar(navtb)

        try:
            back_btn = QAction(QIcon(os.path.join('images', 'arrow-180.png')), "назад", self)
            back_btn.triggered.connect(self._view.back)
            navtb.addAction(back_btn)

            fwd_btn = QAction(QIcon(os.path.join('images', 'arrow-000.png')), "вперёд", self)
            fwd_btn.triggered.connect(self._view.forward)
            navtb.addAction(fwd_btn)

            reload_btn = QAction(QIcon(os.path.join('images', 'arrow-circle-315.png')), "перезагрузить", self)
            reload_btn.triggered.connect(self._view.reload)
            navtb.addAction(reload_btn)

            home_btn = QAction(QIcon(os.path.join('images', 'home.png')), "Qwant", self)
            home_btn.triggered.connect(lambda: self._view.setUrl(QUrl(INCOGNITO_HOMEPAGE)))
            navtb.addAction(home_btn)
        except Exception:
            pass

        navtb.addSeparator()

        self._urlbar = QLineEdit(self)
        self._urlbar.setPlaceholderText("Анонимно: вводи адрес или поиск Qwant…")
        self._urlbar.returnPressed.connect(self._on_url_entered)
        navtb.addWidget(self._urlbar)

        # Бейдж приватности справа от URL-бара.
        anon_badge = QLabel("  АНОНИМ  ")
        anon_badge.setStyleSheet(
            "background:#0c0c0d;color:#ff80ab;border:1px solid #ff4081;"
            "border-radius:4px;padding:3px 8px;font-weight:700;"
        )
        navtb.addWidget(anon_badge)

        self.setCentralWidget(self._view)

        try:
            self._view.urlChanged.connect(self._on_url_changed)
            self._view.titleChanged.connect(self._on_title_changed)
        except Exception:
            pass

        self._view.setUrl(QUrl(start_url or INCOGNITO_HOMEPAGE))

    def _on_url_entered(self):
        text = (self._urlbar.text() or "").strip()
        if not text:
            return
        # Если не похоже на URL — ищем в Qwant.
        if "://" not in text and "." not in text:
            q = urllib.parse.quote_plus(text)
            self._view.setUrl(QUrl(f"https://murena.qwant.com/?q={q}"))
            return
        if "://" not in text:
            text = "https://" + text
        self._view.setUrl(QUrl(text))

    def _on_url_changed(self, qurl):
        try:
            self._urlbar.setText(qurl.toString())
            self._urlbar.setCursorPosition(0)
        except Exception:
            pass

    def _on_title_changed(self, title: str):
        try:
            t = (title or "").strip() or "Аноним��ый режим"
            self.setWindowTitle(f"{t} — EBLAN Browser (Аноним)")
        except Exception:
            pass


# ============================================================
#   Админ-панель банов: видишь всех юзеров, можешь забанить/разбанить
#   с указанием причины. Защищена секретным паролем.
# ============================================================
class BanAdminDialog(QDialog):
    """Админка банов с дефолтным системным внешним видом — без QSS/тем."""

    def __init__(self, api_base: str, parent=None):
        # parent=None намеренно: чтобы не наследовать QSS главного окна
        # (EcssEngine, тёмные темы и т.д.) и оставить нативный вид.
        super().__init__(None)
        self.setWindowTitle("EBLAN — Админка банов")
        self.resize(820, 540)
        # Явно сбрасываем любые унаследованные стили на всякий случай.
        self.setStyleSheet("")
        self._api_base = api_base or DEFAULT_BAN_API_BASE
        self._password = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Шапка с паролем + endpoint
        head = QHBoxLayout()
        head.setSpacing(8)

        head.addWidget(QLabel("API:"))
        self.api_input = QLineEdit(self._api_base)
        self.api_input.setMinimumWidth(280)
        head.addWidget(self.api_input, 1)

        head.addWidget(QLabel("Пароль:"))
        self.pw_input = QLineEdit()
        self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_input.setPlaceholderText("секретный")
        self.pw_input.setMinimumWidth(180)
        head.addWidget(self.pw_input)

        load_btn = QPushButton("Войти / Обновить")
        load_btn.clicked.connect(self._reload)
        head.addWidget(load_btn)

        root.addLayout(head)

        # Таблица пользователей
        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels([
            "Профиль", "HWID", "Статус", "Причина", "Последний вход", "IP",
        ])
        try:
            self.table.horizontalHeader().setStretchLastSection(False)
            self.table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.ResizeToContents
            )
            self.table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeMode.ResizeToContents
            )
            self.table.horizontalHeader().setSectionResizeMode(
                3, QHeaderView.ResizeMode.Stretch
            )
        except Exception:
            pass
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self.table, 1)

        # Кнопки действий
        actions = QHBoxLayout()
        actions.setSpacing(8)

        ban_btn = QPushButton("Забанить (с причиной)")
        ban_btn.clicked.connect(self._action_ban)
        actions.addWidget(ban_btn)

        unban_btn = QPushButton("Разбанить")
        unban_btn.clicked.connect(self._action_unban)
        actions.addWidget(unban_btn)

        forget_btn = QPushButton("Забыть запись")
        forget_btn.clicked.connect(self._action_forget)
        actions.addWidget(forget_btn)

        actions.addStretch(1)

        chpw_btn = QPushButton("Сменить пароль…")
        chpw_btn.clicked.connect(self._action_change_password)
        actions.addWidget(chpw_btn)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)

        root.addLayout(actions)

        self.status = QLabel("")
        root.addWidget(self.status)

    # ---------- helpers ----------
    def _set_status(self, text: str, error: bool = False):
        # Префикс вместо цвета — раз GUI без QSS, отличаем сообщения текстом.
        prefix = "ОШИБКА: " if error and text else ""
        self.status.setText(prefix + (text or ""))

    def _selected_row(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        # HWID лежит в колонке 1
        item = self.table.item(row, 1)
        if not item:
            return None
        return {
            "hwid":    item.text(),
            "profile": (self.table.item(row, 0).text() if self.table.item(row, 0) else ""),
            "active":  (self.table.item(row, 2).text() == "БАН") if self.table.item(row, 2) else False,
            "reason":  (self.table.item(row, 3).text() if self.table.item(row, 3) else ""),
        }

    def _api(self) -> str:
        return (self.api_input.text() or "").strip() or DEFAULT_BAN_API_BASE

    def _pw(self) -> str:
        return self.pw_input.text() or ""

    # ---------- actions ----------
    def _reload(self):
        api = self._api()
        pw = self._pw()
        if not pw:
            self._set_status("Введи пароль и нажми «Войти».", error=True)
            return
        data = ban_admin_request(api, "bans", pw)
        if not data.get("ok"):
            err = data.get("error", "unknown")
            self._set_status(f"Не пускает: {err}", error=True)
            self.table.setRowCount(0)
            return
        self._password = pw
        self._api_base = api
        users = data.get("users") or []
        self.table.setRowCount(len(users))
        for r, u in enumerate(users):
            ts = u.get("last_seen") or u.get("first_seen") or 0
            try:
                last = datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M") if ts else "—"
            except Exception:
                last = "—"
            cells = [
                str(u.get("profile") or "—"),
                str(u.get("hwid") or ""),
                "БАН" if u.get("active") else "ok",
                str(u.get("reason") or ""),
                last,
                str(u.get("last_ip") or ""),
            ]
            for c, val in enumerate(cells):
                item = QTableWidgetItem(val)
                self.table.setItem(r, c, item)
        self._set_status(f"Загружено: {len(users)}.")

    def _action_ban(self):
        sel = self._selected_row()
        if not sel:
            self._set_status("Выбери строку.", error=True)
            return
        reason, ok = QInputDialog.getMultiLineText(
            self, "Причина бана",
            f"За что банишь {sel['profile']}?",
            sel.get("reason") or "",
        )
        if not ok:
            return
        data = ban_admin_request(
            self._api(), "ban", self._password,
            hwid=sel["hwid"], profile=sel["profile"], reason=reason,
        )
        if data.get("ok"):
            self._set_status(f"Забанен: {sel['profile']}")
            self._reload()
        else:
            self._set_status(f"Ошибка: {data.get('error','?')}", error=True)

    def _action_unban(self):
        sel = self._selected_row()
        if not sel:
            self._set_status("Выбери строку.", error=True)
            return
        data = ban_admin_request(
            self._api(), "unban", self._password, hwid=sel["hwid"],
        )
        if data.get("ok"):
            self._set_status(f"Разбанен: {sel['profile']}")
            self._reload()
        else:
            self._set_status(f"Ошибка: {data.get('error','?')}", error=True)

    def _action_forget(self):
        sel = self._selected_row()
        if not sel:
            self._set_status("Выбери строку.", error=True)
            return
        confirm = QMessageBox.question(
            self, "Удалить запись?",
            f"Полностью убрать {sel['profile']} из списка?\n"
            "Если запустит браузер снова — появится опять.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        data = ban_admin_request(
            self._api(), "forget", self._password, hwid=sel["hwid"],
        )
        if data.get("ok"):
            self._set_status(f"Удалено: {sel['profile']}")
            self._reload()
        else:
            self._set_status(f"Ошибка: {data.get('error','?')}", error=True)

    def _action_change_password(self):
        new_pw, ok = QInputDialog.getText(
            self, "Новый пароль",
            "Введи новый секретный пароль:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not new_pw:
            return
        data = ban_admin_request(
            self._api(), "admin_password", self._password, new=new_pw,
        )
        if data.get("ok"):
            self._password = new_pw
            self.pw_input.setText(new_pw)
            self._set_status("Пароль обновлён.")
        else:
            self._set_status(f"Ошибка: {data.get('error','?')}", error=True)


if __name__ == "__main__":
    try:
        # ВАЖНО: поднять VLESS ДО создания QApplication, чтобы Chromium увидел
        # флаг --proxy-server через переменную окружения QTWEBENGINE_CHROMIUM_FLAGS.
        try:
            _vless_bootstrap()
        except Exception as _e:
            print(f"[vless] bootstrap: {_e}")

        app = QApplication(sys.argv)
        app.setApplicationName("EBLAN Browser")
        app.setOrganizationName("EBLAN Browser")
        app.setOrganizationDomain("eblanbrowser.ru")

        # Шуточный локальный бан после Tonkeeper 2 — встречаем «еблана».
        try:
            check_local_seed_ban()
        except SystemExit:
            raise
        except Exception as _e:
            print(f"[ban] local seed-ban check error: {_e}")

        # EBLAN ID check may be optional depending on settings
        settings = load_settings()
        require_id = settings.get("require_eblan_id", False)

        # ---------- Проверка бана по железу ----------
        # Если админ забанил эту машину — не пускаем, кричим «пошёл нахуй» и выходим.
        try:
            _ban_api = settings.get("update_api_base") or DEFAULT_BAN_API_BASE
            _hwid = get_hardware_id()
            _profile = settings.get("user_profile_name") or get_profile_name()
            # Полный отпечаток железа — для нечёткого совпадения на сервере.
            try:
                _components = collect_hw_components()
            except Exception:
                _components = None
            _ban_info = check_ban_at_startup(_ban_api, _hwid, _components)
            if _ban_info.get("banned"):
                _reason = (_ban_info.get("reason") or "").strip() or "— без объяснения, заслужил."
                QMessageBox.critical(
                    None,
                    "ПОШЁЛ НАХУЙ",
                    "Ты забанен в EBLAN Browser, чмо.\n\n"
                    f"Причина:\n{_reason}\n\n"
                    f"Профиль: {_ban_info.get('profile') or _profile}\n"
                    f"HWID: {_hwid[:12]}…",
                )
                sys.exit(0)
            # Не забанен — регистрируемся в админке (молча, в фоне).
            ban_heartbeat_async(_ban_api, _hwid, _profile, _components)
        except Exception as _e:
            print(f"[ban] startup check error: {_e}")

        eblan_id = load_eblan_id()

        if require_id:
            if not eblan_id or not check_eblan_id_alive(eblan_id):
                dlg = EblanIdDialog()
                if not dlg.exec():
                    try:
                        if SKIP_EBLAN_ID:
                            eblan_id = None
                        else:
                            sys.exit(0)
                    except Exception:
                        sys.exit(0)
                else:
                    eblan_id = dlg.eblan_id

                try:
                    if not SKIP_EBLAN_ID:
                        if eblan_id and not check_eblan_id_alive(eblan_id):
                            QMessageBox.critical(
                                None,
                                "Доступ запрещён",
                                "EBLAN ID не прошёл проверку.\n\nТы умрёшь."
                            )
                            sys.exit(0)
                except Exception:
                    pass

        window = MainWindow()
        window.eblan_id = eblan_id  # ← ID доступен всему браузеру
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        print(f"[FATAL] Ошибка запуска приложения: {str(e)}")
