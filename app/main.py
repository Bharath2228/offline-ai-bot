from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from threading import Event
from urllib.parse import urlparse

from PySide6.QtCore import QProcess, QRectF, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtTextToSpeech import QTextToSpeech
from PySide6.QtGui import (
    QColor,
    QCloseEvent,
    QFont,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QTextCursor,
    QShortcut,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
)

from lm_studio_client import ChatMessage, LMStudioClient, LMStudioError, choose_preferred_model
from local_runtime import LocalModelRuntime, LocalRuntimeError, discover_runtime_assets
from model_browser import ModelBrowser
from image_studio import ImageStudio
from assistant_profiles import PROFILES, PROFILE_TEMPERATURES, build_system_prompt


from ui_theme import APP_STYLE, BRASS, BRASS_HOVER, EMBER, INK, PARCHMENT


def friendly_model_name(model_id: str) -> str:
    lowered = model_id.lower()
    if "qwen3" in lowered and ("vl" in lowered or "vision" in lowered):
        size = "4B" if "4b" in lowered else "Vision"
        return f"Qwen 3 VL  ·  {size}  ·  Local"
    if "qwen3" in lowered and "8b" in lowered:
        return "Qwen 3  ·  8B  ·  Best for text"
    name = model_id.replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith(".gguf"):
        name = name[:-5]
    return name.replace("-", " ")[:52]


def _paint_keyhole(painter: QPainter, bounds: QRectF, ink, brass: QColor) -> None:
    """A keyhole on a dark rounded tile — Keep's mark: what it protects stays shut."""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(ink)
    radius = bounds.width() * 0.26
    painter.drawRoundedRect(bounds, radius, radius)

    center = bounds.center()
    unit = bounds.width()
    ring_d = unit * 0.30
    ring_cy = center.y() - unit * 0.12
    path = QPainterPath()
    path.addEllipse(QRectF(center.x() - ring_d / 2, ring_cy - ring_d / 2, ring_d, ring_d))
    wedge = QPainterPath()
    wedge.moveTo(center.x() - unit * 0.075, ring_cy + unit * 0.05)
    wedge.lineTo(center.x() + unit * 0.075, ring_cy + unit * 0.05)
    wedge.lineTo(center.x() + unit * 0.035, center.y() + unit * 0.27)
    wedge.lineTo(center.x() - unit * 0.035, center.y() + unit * 0.27)
    wedge.closeSubpath()
    path = path.united(wedge)
    painter.setBrush(brass)
    painter.drawPath(path)


def make_keep_icon() -> QIcon:
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(8, 8, 120, 120)
    gradient.setColorAt(0, QColor("#20252b"))
    gradient.setColorAt(1, QColor("#14171b"))
    _paint_keyhole(painter, QRectF(6, 6, 116, 116), gradient, QColor("#c89b4c"))
    painter.end()
    return QIcon(pixmap)


class ApiWorker(QThread):
    models_ready = Signal(object)
    token_ready = Signal(str)
    response_ready = Signal(str)
    failed = Signal(str)

    def __init__(self, client: LMStudioClient, action: str, **kwargs) -> None:
        super().__init__()
        self.client = client
        self.action = action
        self.kwargs = kwargs
        self.cancel_event = Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            if self.action == "models":
                self.models_ready.emit(self.client.list_models())
                return
            if self.action == "runtime":
                runtime = self.kwargs["runtime"]
                if self.kwargs.get("assets"):
                    runtime.stop()
                    runtime.assets = self.kwargs["assets"]
                runtime.start()
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline and not self.cancel_event.is_set():
                    if runtime.has_exited():
                        raise LocalRuntimeError(
                            "The local model process exited. See keep-runtime.log for details."
                        )
                    try:
                        self.models_ready.emit(self.client.list_models())
                        return
                    except LMStudioError:
                        time.sleep(0.2)
                if not self.cancel_event.is_set():
                    raise LocalRuntimeError("The local model took too long to start.")
                return
            answer = ""
            pending_tokens: list[str] = []
            pending_chars = 0
            last_emit = time.monotonic()
            for token in self.client.stream_chat(cancel_event=self.cancel_event, **self.kwargs):
                if self.cancel_event.is_set():
                    break
                answer += token
                pending_tokens.append(token)
                pending_chars += len(token)
                now = time.monotonic()
                if pending_chars >= 96 or now - last_emit >= 0.035:
                    self.token_ready.emit("".join(pending_tokens))
                    pending_tokens.clear()
                    pending_chars = 0
                    last_emit = now
            if pending_tokens:
                self.token_ready.emit("".join(pending_tokens))
            self.response_ready.emit(answer)
        except (LMStudioError, LocalRuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Unexpected local error: {exc}")


class OfflineTextBrowser(QTextBrowser):
    def loadResource(self, resource_type, url):
        # Markdown may contain arbitrary image URLs or local file references.
        return None


class KeepCore(QWidget):
    """Keep's identity: a keyhole on a dark tile — what it holds stays shut."""

    def __init__(self, diameter: int = 176, compact: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.compact = compact
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        inset = side * 0.03
        bounds = QRectF(inset, inset, side - inset * 2, side - inset * 2)
        gradient = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        gradient.setColorAt(0, QColor("#20252b"))
        gradient.setColorAt(1, QColor("#14171b"))
        _paint_keyhole(painter, bounds, gradient, QColor("#c89b4c"))
        painter.end()


class MessageBubble(QFrame):
    speak_requested = Signal(str)

    def __init__(self, role: str, text: str, image_path: str | None = None) -> None:
        super().__init__()
        self.role = role
        self.setObjectName("turnUser" if role == "user" else "turnAssistant")
        self.setMaximumWidth(820)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 14)
        layout.setSpacing(8)
        self.raw_text = text

        role_label = QLabel("You" if role == "user" else "Keep")
        role_label.setObjectName("bubbleRoleUser" if role == "user" else "bubbleRoleAssistant")
        heading = QHBoxLayout()
        heading.addWidget(role_label)
        heading.addStretch()
        if role == "assistant":
            self.speak_button = QPushButton("Read aloud")
            self.speak_button.setObjectName("copy")
            self.speak_button.clicked.connect(lambda: self.speak_requested.emit(self.raw_text))
            heading.addWidget(self.speak_button)
            self.copy_button = QPushButton("Copy")
            self.copy_button.setObjectName("copy")
            self.copy_button.clicked.connect(self.copy_text)
            heading.addWidget(self.copy_button)
        layout.addLayout(heading)

        if image_path:
            preview = QLabel()
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                preview.setPixmap(
                    pixmap.scaled(
                        320,
                        190,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                layout.addWidget(preview)

        self.text_view = OfflineTextBrowser()
        self.text_view.setOpenExternalLinks(False)
        self.text_view.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.text_view)
        self.set_text(text)

    def _resize_document(self) -> None:
        self.text_view.setFixedHeight(max(28, int(self.text_view.document().size().height()) + 8))

    def set_text(self, text: str) -> None:
        # Plain text prevents model-produced Markdown/HTML from requesting remote
        # resources, preserving the application's offline guarantee.
        self.raw_text = text
        self.text_view.setPlainText(text or ("Thinking…" if self.role == "assistant" else ""))
        QTimer.singleShot(0, self._resize_document)

    def finish(self):
        if self.role == "assistant":
            self.text_view.setMarkdown(self.raw_text)
            QTimer.singleShot(0, self._resize_document)

    def copy_text(self):
        QApplication.clipboard().setText(self.raw_text)
        self.copy_button.setText("Copied")
        QTimer.singleShot(1500, lambda: self.copy_button.setText("Copy"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._resize_document)


class SettingsDialog(QDialog):
    def __init__(self, temperature: float, max_tokens: int, custom_instructions: str,
                 speech_rate: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keep · Settings")
        self.setModal(True)
        self.setMinimumWidth(390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Settings")
        title.setObjectName("chatTitle")
        layout.addWidget(title)
        row = QHBoxLayout()
        row.addWidget(QLabel("Temperature"))
        row.addStretch()
        self.temperature_value = QLabel(f"{temperature:.1f}")
        self.temperature_value.setStyleSheet(f"color: {BRASS};")
        row.addWidget(self.temperature_value)
        layout.addLayout(row)
        self.temperature_slider = QSlider(Qt.Orientation.Horizontal)
        self.temperature_slider.setRange(0, 20)
        self.temperature_slider.setValue(round(temperature * 10))
        self.temperature_slider.valueChanged.connect(
            lambda value: self.temperature_value.setText(f"{value / 10:.1f}")
        )
        layout.addWidget(self.temperature_slider)
        hint = QLabel("Lower is focused; higher is more creative.")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        token_row = QHBoxLayout()
        token_row.addWidget(QLabel("Maximum response tokens"))
        token_row.addStretch()
        self.max_tokens_input = QSpinBox()
        self.max_tokens_input.setRange(64, 32768)
        self.max_tokens_input.setSingleStep(256)
        self.max_tokens_input.setValue(max_tokens)
        token_row.addWidget(self.max_tokens_input)
        layout.addLayout(token_row)
        layout.addWidget(QLabel("Personal instructions (optional)"))
        self.custom_instructions_input = QTextEdit()
        self.custom_instructions_input.setObjectName("composer")
        self.custom_instructions_input.setPlaceholderText("For example: Keep answers concise. Use metric units.")
        self.custom_instructions_input.setPlainText(custom_instructions)
        self.custom_instructions_input.setFixedHeight(90)
        layout.addWidget(self.custom_instructions_input)
        speech_row = QHBoxLayout()
        speech_row.addWidget(QLabel("Read-aloud speed"))
        speech_row.addStretch()
        self.speech_rate_value = QLabel(f"{speech_rate:+.1f}")
        speech_row.addWidget(self.speech_rate_value)
        layout.addLayout(speech_row)
        self.speech_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.speech_rate_slider.setRange(-10, 10)
        self.speech_rate_slider.setValue(round(speech_rate * 10))
        self.speech_rate_slider.valueChanged.connect(
            lambda value: self.speech_rate_value.setText(f"{value / 10:+.1f}"))
        layout.addWidget(self.speech_rate_slider)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        save.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    @property
    def temperature(self) -> float:
        return self.temperature_slider.value() / 10

    @property
    def max_tokens(self) -> int:
        return self.max_tokens_input.value()

    @property
    def custom_instructions(self) -> str:
        return self.custom_instructions_input.toPlainText().strip()

    @property
    def speech_rate(self) -> float:
        return self.speech_rate_slider.value() / 10


class MainWindow(QMainWindow):
    def __init__(self, client: LMStudioClient | None = None) -> None:
        super().__init__()
        if client is None:
            self.client = LMStudioClient(
                os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
            )
            runtime_port = urlparse(self.client.base_url).port or 80
            self.runtime = LocalModelRuntime(port=runtime_port)
        else:
            self.client = client
            self.runtime = None
        self.settings = QSettings("Keep", "KeepDesktop")
        self.temperature = float(self.settings.value("temperature", 0.7))
        self.max_tokens = int(self.settings.value("max_tokens", 2048))
        self.profile = str(self.settings.value("profile", "Balanced"))
        if self.profile not in PROFILES:
            self.profile = "Balanced"
        self.custom_instructions = str(self.settings.value("custom_instructions", ""))
        self.speech_rate = float(self.settings.value("speech_rate", 0.0))
        self.speech = QTextToSpeech("sapi", self)
        self.speech.setRate(self.speech_rate)
        self.voice_root = Path(str(self.settings.value("voice_runtime_root", Path(__file__).resolve().parent.parent)))
        self.voice_process: QProcess | None = None
        self.voice_buffer = ""
        self.voice_error = ""
        self.messages: list[ChatMessage] = []
        self.message_rows: list[QWidget] = []
        self.pending_image: str | None = None
        self.worker: ApiWorker | None = None
        self.active_bubble: MessageBubble | None = None
        self.active_answer = ""
        self.stream_render_timer = QTimer(self)
        self.stream_render_timer.setSingleShot(True)
        self.stream_render_timer.setInterval(33)
        self.stream_render_timer.timeout.connect(self._flush_stream_render)
        self.start_fallback_after_worker = False
        self.generation_started = 0.0
        self.sessions = []
        self.session_index = -1

        self.setWindowTitle("Keep — Private local AI")
        self.setMinimumSize(980, 680)
        self.resize(1280, 800)
        self._build_ui()
        self.new_chat()
        self.send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.send_shortcut.activated.connect(self.send_or_stop)
        self.new_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self.new_shortcut.activated.connect(self.new_chat)
        QTimer.singleShot(100, self.load_models)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(258)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 24, 20, 18)
        side.setSpacing(18)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        logo = KeepCore(44, compact=True)
        brand_row.addWidget(logo)
        brand_words = QVBoxLayout()
        brand_words.setSpacing(0)
        brand = QLabel("Keep")
        brand.setObjectName("brand")
        caption = QLabel("Runs only on this computer")
        caption.setObjectName("brandCaption")
        brand_words.addWidget(brand)
        brand_words.addWidget(caption)
        brand_row.addLayout(brand_words)
        brand_row.addStretch()
        side.addLayout(brand_row)

        self.new_chat_button = QPushButton("＋   New conversation")
        self.new_chat_button.setObjectName("newChat")
        self.new_chat_button.clicked.connect(self.new_chat)
        side.addWidget(self.new_chat_button)
        session_label = QLabel("Conversations")
        session_label.setObjectName("eyebrow")
        side.addWidget(session_label)
        self.chat_search = QLineEdit()
        self.chat_search.setPlaceholderText("Search conversations")
        self.chat_search.textChanged.connect(self._filter_sessions)
        side.addWidget(self.chat_search)
        self.chat_list = QListWidget()
        self.chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.chat_list.currentRowChanged.connect(self.switch_chat)
        side.addWidget(self.chat_list, 1)

        dock = QHBoxLayout()
        dock.setSpacing(8)
        self.models_button = QPushButton("◇  Models")
        self.models_button.setToolTip("Model library")
        self.models_button.clicked.connect(self.choose_installed_model)
        dock.addWidget(self.models_button)
        self.image_studio_button = QPushButton("✦  Images")
        self.image_studio_button.setToolTip("Image studio")
        self.image_studio_button.clicked.connect(self.open_image_studio)
        dock.addWidget(self.image_studio_button)
        side.addLayout(dock)

        privacy_note = QFrame()
        privacy_note.setObjectName("privacyNote")
        privacy_layout = QVBoxLayout(privacy_note)
        privacy_layout.setContentsMargins(2, 14, 2, 2)
        privacy_layout.setSpacing(6)
        privacy_title = QLabel("Nothing leaves this machine")
        privacy_title.setObjectName("privacyTitle")
        privacy_text = QLabel("Chats, images, and voice all run locally — no account, no cloud.")
        privacy_text.setObjectName("privacyText")
        privacy_text.setWordWrap(True)
        privacy_layout.addWidget(privacy_title)
        privacy_layout.addWidget(privacy_text)
        side.addWidget(privacy_note)
        self.status_label = QLabel("●  Getting things ready…")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(42)
        side.addWidget(self.status_label)
        root_layout.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = QVBoxLayout(topbar)
        top.setContentsMargins(44, 16, 32, 14)
        top.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        self.chat_title = QLabel("New conversation")
        self.chat_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.chat_title.setObjectName("chatTitle")
        title_row.addWidget(self.chat_title, 1)
        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self.export_chat)
        title_row.addWidget(self.export_button)
        self.regenerate_button = QPushButton("Regenerate")
        self.regenerate_button.setToolTip("Try the last response again")
        self.regenerate_button.setEnabled(False)
        self.regenerate_button.clicked.connect(self.regenerate_response)
        title_row.addWidget(self.regenerate_button)
        self.settings_button = QPushButton("⚙  Settings")
        self.settings_button.clicked.connect(self.open_settings)
        title_row.addWidget(self.settings_button)
        top.addLayout(title_row)

        control_row = QHBoxLayout()
        control_row.setSpacing(18)
        model_column = QVBoxLayout()
        model_column.setSpacing(3)
        model_label = QLabel("Model")
        model_label.setObjectName("fieldLabel")
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        self.model_combo.setMaximumWidth(360)
        self.model_combo.addItem("Connecting to LM Studio…", None)
        model_column.addWidget(model_label)
        model_column.addWidget(self.model_combo)
        control_row.addLayout(model_column)
        profile_column = QVBoxLayout()
        profile_column.setSpacing(3)
        profile_label = QLabel("Style")
        profile_label.setObjectName("fieldLabel")
        self.profile_combo = QComboBox()
        self.profile_combo.setToolTip("Choose how Keep should answer")
        self.profile_combo.addItems(PROFILES)
        self.profile_combo.setCurrentText(self.profile)
        self.profile_combo.currentTextChanged.connect(self._profile_changed)
        profile_column.addWidget(profile_label)
        profile_column.addWidget(self.profile_combo)
        control_row.addLayout(profile_column)
        self.retry_button = QPushButton("Retry")
        self.retry_button.clicked.connect(self.load_models)
        control_row.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignBottom)
        control_row.addStretch()
        top.addLayout(control_row)
        content_layout.addWidget(topbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.message_host = QWidget()
        self.message_layout = QVBoxLayout(self.message_host)
        self.message_layout.setContentsMargins(48, 38, 48, 30)
        self.message_layout.setSpacing(6)
        self.welcome = self._make_welcome()
        self.message_layout.addWidget(self.welcome, 1)
        self.message_layout.addStretch()
        self.scroll.setWidget(self.message_host)
        content_layout.addWidget(self.scroll, 1)

        composer_area = QFrame()
        composer_area.setObjectName("composerPanel")
        composer_layout = QVBoxLayout(composer_area)
        self.composer_layout = composer_layout
        composer_layout.setContentsMargins(44, 16, 44, 20)
        composer_layout.setSpacing(10)
        self.image_chip = QFrame()
        self.image_chip.setObjectName("imageChip")
        chip_layout = QHBoxLayout(self.image_chip)
        chip_layout.setContentsMargins(10, 7, 10, 7)
        self.image_preview = QLabel()
        self.image_name = QLabel()
        remove_image = QPushButton("Remove")
        remove_image.clicked.connect(self.clear_pending_image)
        chip_layout.addWidget(self.image_preview)
        chip_layout.addWidget(self.image_name)
        chip_layout.addStretch()
        chip_layout.addWidget(remove_image)
        self.image_chip.hide()
        composer_layout.addWidget(self.image_chip)

        toolbar_row = QHBoxLayout()
        toolbar_row.setSpacing(10)
        self.mic_button = QPushButton("◉  Speak")
        self.mic_button.setToolTip("Dictate with the offline Whisper model")
        self.mic_button.clicked.connect(self.toggle_voice_input)
        toolbar_row.addWidget(self.mic_button)
        self.attach_button = QPushButton("＋  Image")
        self.attach_button.setToolTip("Attach a JPEG, PNG, or WebP image")
        self.attach_button.clicked.connect(self.attach_image)
        toolbar_row.addWidget(self.attach_button)
        toolbar_row.addStretch()
        hint = QLabel("Ctrl + Enter to send  ·  private and local to this device")
        hint.setObjectName("muted")
        toolbar_row.addWidget(hint)
        composer_layout.addLayout(toolbar_row)

        self.composer = QTextEdit()
        self.composer.setObjectName("composer")
        self.composer.setPlaceholderText("Ask Keep anything, or add an image…")
        self.composer.setAcceptRichText(False)
        self.composer.setFixedHeight(92)
        composer_layout.addWidget(self.composer)

        send_row = QHBoxLayout()
        send_row.addStretch()
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("primary")
        self.send_button.setFixedSize(104, 40)
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.send_or_stop)
        send_row.addWidget(self.send_button)
        composer_layout.addLayout(send_row)

        content_layout.addWidget(composer_area)
        root_layout.addWidget(content, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'message_layout'):
            margin = max(28, (self.width() - 258 - 860) // 2)
            self.message_layout.setContentsMargins(margin, 26, margin, 30)
            self.composer_layout.setContentsMargins(margin, 16, margin, 22)

    def _make_welcome(self) -> QWidget:
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark = KeepCore(132)
        hero = QLabel("Nothing you say here leaves this room.")
        hero.setObjectName("hero")
        hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.setWordWrap(True)
        hero.setMaximumWidth(560)
        description = QLabel("Keep runs the model, the image generator, and the microphone on this computer. No account, no cloud, nothing sent anywhere.")
        description.setWordWrap(True)
        description.setMaximumWidth(480)
        description.setObjectName("muted")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        suggestions = QHBoxLayout()
        suggestions.setSpacing(10)
        for label, prompt in (
            ("Explain something", "Explain a complex idea in simple terms."),
            ("Brainstorm together", "Help me brainstorm a few original ideas."),
            ("Ask about an image", "I want to ask a question about an image."),
        ):
            button = QPushButton(label)
            button.setObjectName("suggestion")
            button.clicked.connect(lambda checked=False, value=prompt: self._use_suggestion(value))
            suggestions.addWidget(button)
        layout.addStretch()
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(22)
        layout.addWidget(hero)
        layout.addSpacing(12)
        layout.addWidget(description)
        layout.addSpacing(26)
        layout.addLayout(suggestions)
        layout.addStretch()
        return welcome

    def _use_suggestion(self, prompt: str) -> None:
        self.composer.setPlainText(prompt)
        self.composer.setFocus()

    def keyPressEvent(self, event) -> None:
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and self.composer.hasFocus()
        ):
            self.send_or_stop()
            return
        super().keyPressEvent(event)

    def load_models(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        self.status_label.setStyleSheet("")
        self.status_label.setText("●  Connecting locally…")
        self.model_combo.clear()
        self.model_combo.addItem("Connecting…", None)
        self.retry_button.setEnabled(False)
        self.send_button.setEnabled(False)
        worker = ApiWorker(self.client, "models")
        worker.models_ready.connect(self._models_loaded)
        worker.failed.connect(self._model_load_failed)
        worker.finished.connect(self._worker_finished)
        self.worker = worker
        worker.start()

    def _models_loaded(self, models: list[str]) -> None:
        self.model_combo.clear()
        if not models:
            self.model_combo.addItem("No models available", None)
            self.status_label.setText("●  Load a model in LM Studio, then press Retry.")
            return
        for model in models:
            self.model_combo.addItem(friendly_model_name(model), model)
            self.model_combo.setItemData(
                self.model_combo.count() - 1, model, Qt.ItemDataRole.ToolTipRole
            )
        preferred = choose_preferred_model(models)
        if preferred:
            preferred_index = self.model_combo.findData(preferred)
            if preferred_index >= 0:
                self.model_combo.setCurrentIndex(preferred_index)
        self.status_label.setText(f"●  Connected locally · {len(models)} model(s)")
        self.status_label.setStyleSheet("color: #c89b4c;")
        self.send_button.setEnabled(True)

    def _model_load_failed(self, message: str) -> None:
        self.model_combo.clear()
        self.model_combo.addItem("LM Studio unavailable", None)
        self.status_label.setText(f"●  {message}")
        self.status_label.setStyleSheet("color: #d9735c;")
        if self.runtime and self.runtime.available:
            self.start_fallback_after_worker = True

    def _worker_finished(self) -> None:
        self.retry_button.setEnabled(True)
        worker = self.sender()
        if isinstance(worker, ApiWorker):
            worker.deleteLater()
            if worker is self.worker:
                self.worker = None
        if self.start_fallback_after_worker:
            self.start_fallback_after_worker = False
            QTimer.singleShot(0, self._start_local_runtime)

    def _start_local_runtime(self) -> None:
        if not self.runtime or not self.runtime.available:
            return
        self.status_label.setStyleSheet("color: #c89b4c;")
        self.status_label.setText("●  Starting your local model… this can take a minute.")
        self.model_combo.clear()
        self.model_combo.addItem("Loading local model…", None)
        self.retry_button.setEnabled(False)
        worker = ApiWorker(self.client, "runtime", runtime=self.runtime)
        worker.models_ready.connect(self._models_loaded)
        worker.failed.connect(self._runtime_start_failed)
        worker.finished.connect(self._worker_finished)
        self.worker = worker
        worker.start()

    def _runtime_start_failed(self, message: str) -> None:
        self.model_combo.clear()
        self.model_combo.addItem("Local model unavailable", None)
        self.status_label.setText(f"●  {message}")
        self.status_label.setStyleSheet("color: #d9735c;")

    def attach_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach an image", "", "Images (*.jpg *.jpeg *.png *.webp)"
        )
        if not path:
            return
        if Path(path).stat().st_size > 20 * 1024 * 1024:
            QMessageBox.warning(self, "Image too large", "Choose an image smaller than 20 MB.")
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Unreadable image", "That image could not be opened.")
            return
        self.pending_image = path
        self.image_preview.setPixmap(
            pixmap.scaled(42, 42, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        self.image_name.setText(Path(path).name)
        self.image_chip.show()

    def choose_installed_model(self):
        if self.worker is not None:
            return
        dialog = ModelBrowser(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self.runtime is None or dialog.selected_path is None:
            return
        assets = discover_runtime_assets(model_path=dialog.selected_path)
        if not assets:
            QMessageBox.warning(self, "Runtime unavailable", "Install a local inference runtime in LM Studio first.")
            return
        if not self.runtime.process and self.model_combo.currentData():
            QMessageBox.information(self, "LM Studio manages this server", "Load this model in LM Studio, then use Retry. Models exposed by its server can be selected in the model menu.")
            return
        self.model_combo.clear()
        self.model_combo.addItem("Loading model…", None)
        self.send_button.setEnabled(False)
        self.status_label.setText("Loading " + friendly_model_name(str(assets.model)))
        worker = ApiWorker(self.client, "runtime", runtime=self.runtime, assets=assets)
        worker.models_ready.connect(self._models_loaded)
        worker.failed.connect(self._runtime_start_failed)
        worker.finished.connect(self._worker_finished)
        self.worker = worker
        worker.start()

    def open_image_studio(self):
        ImageStudio(self).exec()

    def clear_pending_image(self) -> None:
        self.pending_image = None
        self.image_preview.clear()
        self.image_name.clear()
        self.image_chip.hide()

    def send_or_stop(self) -> None:
        if self.worker and self.worker.isRunning():
            if self.worker.action != "chat":
                return
            self.worker.cancel()
            self.send_button.setEnabled(False)
            self.send_button.setText("Stopping…")
            return
        self.send_message()

    def _voice_ready(self) -> bool:
        return (
            (self.voice_root / ".voice-venv/Scripts/python.exe").is_file()
            and (self.voice_root / "voice-models/faster-whisper-tiny/model.bin").is_file()
        )

    def toggle_voice_input(self) -> None:
        if self.voice_process is not None:
            self.mic_button.setEnabled(False)
            self.mic_button.setText("Transcribing…")
            self.status_label.setText("●  Transcribing your voice locally…")
            self.voice_process.write(b"stop\n")
            self.voice_process.closeWriteChannel()
            return
        if not self._voice_ready():
            # The setup script may have been run while Keep was open. Refresh
            # the saved location here so Speak works without another restart.
            self.settings.sync()
            configured_root = self.settings.value("voice_runtime_root")
            if configured_root:
                self.voice_root = Path(str(configured_root))
        if not self._voice_ready():
            QMessageBox.information(
                self, "Voice input setup needed",
                "Run setup-voice.ps1 once from the Keep project folder, then try Speak again."
            )
            return
        self.voice_buffer = self.voice_error = ""
        process = QProcess(self)
        self.voice_process = process
        process.readyReadStandardOutput.connect(self._read_voice_output)
        process.readyReadStandardError.connect(self._read_voice_error)
        process.finished.connect(self._voice_finished)
        process.errorOccurred.connect(self._voice_process_error)
        worker = Path(__file__).resolve().parent / "voice_worker.py"
        process.start(str(self.voice_root / ".voice-venv/Scripts/python.exe"), ["-u", str(worker)])
        process.write((__import__("json").dumps({
            "model": str(self.voice_root / "voice-models/faster-whisper-tiny")
        }) + "\n").encode())
        self.mic_button.setText("■  Stop")
        self.send_button.setEnabled(False)
        self.status_label.setText("●  Starting the local microphone…")

    def _read_voice_output(self) -> None:
        if not self.voice_process:
            return
        self.voice_buffer += bytes(self.voice_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        while "\n" in self.voice_buffer:
            line, self.voice_buffer = self.voice_buffer.split("\n", 1)
            try:
                update = __import__("json").loads(line)
            except ValueError:
                continue
            if update.get("status"):
                self.status_label.setText("●  " + update["status"])
            transcript = update.get("transcript")
            if transcript:
                existing = self.composer.toPlainText().rstrip()
                self.composer.setPlainText((existing + " " + transcript).strip())
                self.composer.moveCursor(QTextCursor.MoveOperation.End)
            if update.get("error"):
                self.voice_error = update["error"]

    def _read_voice_error(self) -> None:
        if self.voice_process:
            self.voice_error = (self.voice_error + bytes(
                self.voice_process.readAllStandardError()).decode("utf-8", errors="replace"))[-3000:]

    def _voice_process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.voice_error = self.voice_process.errorString() if self.voice_process else "Voice process did not start."

    def _voice_finished(self, code, *_args) -> None:
        if self.voice_process is None:
            return
        self._read_voice_output()
        self.voice_process.deleteLater()
        self.voice_process = None
        self.mic_button.setEnabled(True)
        self.mic_button.setText("◉  Speak")
        self.send_button.setEnabled(bool(self.model_combo.currentData()))
        if code and self.voice_error:
            detail = self.voice_error.strip().splitlines()[-1]
            self.status_label.setText("●  Voice input failed: " + detail)
        self.composer.setFocus()

    def send_message(self) -> None:
        if self.worker is not None:
            return
        model = self.model_combo.currentData()
        text = self.composer.toPlainText().strip()
        if not model:
            QMessageBox.information(self, "No model", "Start LM Studio's server and select a model first.")
            return
        if not text and not self.pending_image:
            return
        if not text:
            text = "Describe this image."
        if self.pending_image and not any(word in str(model).casefold() for word in ("vl", "vision")):
            QMessageBox.information(
                self, "Choose a vision model",
                "This model is optimized for text. Open Model library and load Qwen 3 VL before sending an image."
            )
            return
        user_message = ChatMessage("user", text, self.pending_image)
        self.messages.append(user_message)
        if len(self.messages) == 1:
            title = text.replace("\n", " ")[:55]
            self.sessions[self.session_index]["title"] = title
            self.chat_title.setText(title)
            self.chat_list.item(self.session_index).setText(title)
            self.chat_list.item(self.session_index).setToolTip(title)
        self._add_bubble("user", text, self.pending_image)
        self.composer.clear()
        self.clear_pending_image()
        self.active_answer = ""
        self.active_bubble = self._add_bubble("assistant", "")
        self._start_generation(model)

    def _start_generation(self, model: str | None = None) -> None:
        model = model or self.model_combo.currentData()
        self._set_generating(True)
        self.generation_started = time.monotonic()
        request_messages = [ChatMessage("system", build_system_prompt(
            self.profile_combo.currentText(), self.custom_instructions
        )), *self.messages[-40:]]
        worker = ApiWorker(
            self.client,
            "chat",
            model=model,
            messages=request_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            thinking=False,
        )
        worker.token_ready.connect(self._append_token)
        worker.response_ready.connect(self._response_finished)
        worker.failed.connect(self._response_failed)
        worker.finished.connect(self._worker_finished)
        self.worker = worker
        worker.start()

    def regenerate_response(self) -> None:
        if self.worker is not None or not self.messages or self.messages[-1].role != "assistant":
            return
        self.messages.pop()
        if self.message_rows:
            row = self.message_rows.pop()
            self.message_layout.removeWidget(row)
            row.deleteLater()
        self.active_answer = ""
        self.active_bubble = self._add_bubble("assistant", "")
        self._start_generation()

    def _add_bubble(self, role: str, text: str, image_path: str | None = None) -> MessageBubble:
        self.welcome.hide()
        bubble = MessageBubble(role, text, image_path)
        if role == "assistant":
            bubble.speak_requested.connect(self.speak_text)
        self.message_layout.insertWidget(self.message_layout.count() - 1, bubble)
        self.message_rows.append(bubble)
        QTimer.singleShot(0, self._scroll_to_bottom)
        return bubble

    def _append_token(self, token: str) -> None:
        self.active_answer += token
        if not self.stream_render_timer.isActive():
            self.stream_render_timer.start()

    def _flush_stream_render(self) -> None:
        if self.active_bubble:
            self.active_bubble.set_text(self.active_answer)
        self._scroll_to_bottom()

    def _response_finished(self, answer: str) -> None:
        self.stream_render_timer.stop()
        was_cancelled = bool(self.worker and self.worker.cancel_event.is_set())
        final_answer = answer.strip()
        if final_answer:
            self.messages.append(ChatMessage("assistant", final_answer))
            if self.active_bubble:
                suffix = "\n\n*Stopped.*" if was_cancelled else ""
                self.active_bubble.set_text(final_answer + suffix)
                self.active_bubble.finish()
            elapsed = time.monotonic() - self.generation_started
            self.status_label.setText(f"●  Done in {elapsed:.1f}s · {self.profile_combo.currentText()}")
        elif self.active_bubble:
            self.active_bubble.set_text("*Response stopped.*" if was_cancelled else "*The model returned no text.*")
        self._set_generating(False)

    def _response_failed(self, message: str) -> None:
        self.stream_render_timer.stop()
        if self.active_bubble:
            self.active_bubble.set_text(f"**Could not respond**\n\n{message}")
        self._set_generating(False)

    def _set_generating(self, active: bool) -> None:
        for widget in (
            self.composer,
            self.attach_button,
            self.mic_button,
            self.model_combo,
            self.new_chat_button,
            self.settings_button,
            self.retry_button,
            self.chat_list,
            self.chat_search,
            self.export_button,
            self.models_button,
            self.profile_combo,
            self.regenerate_button,
            self.image_studio_button,
        ):
            widget.setEnabled(not active)
        self.send_button.setEnabled(True)
        if not active:
            self.regenerate_button.setEnabled(bool(self.messages and self.messages[-1].role == "assistant"))
        self.send_button.setText("Stop" if active else "Send")
        self.send_button.setObjectName("danger" if active else "primary")
        self.send_button.style().unpolish(self.send_button)
        self.send_button.style().polish(self.send_button)

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def new_chat(self) -> None:
        if self.worker is not None and self.worker.action == "chat":
            return
        if self.session_index >= 0:
            self._save_draft()
        self.sessions.append({"title": "New conversation", "messages": [], "draft": "", "image": None})
        self.chat_search.clear()
        self.chat_list.blockSignals(True)
        self.chat_list.addItem("New conversation")
        index = len(self.sessions) - 1
        self.chat_list.setCurrentRow(index)
        self.chat_list.blockSignals(False)
        self._show_session(index)

    def _save_draft(self):
        session = self.sessions[self.session_index]
        session["draft"] = self.composer.toPlainText()
        session["image"] = self.pending_image

    def switch_chat(self, index):
        if index < 0 or index == self.session_index:
            return
        if self.worker is not None and self.worker.action == "chat":
            return
        self._save_draft()
        self._show_session(index)

    def _show_session(self, index):
        self.session_index = index
        session = self.sessions[index]
        self.messages = session["messages"]
        self.clear_pending_image()
        for row in self.message_rows:
            self.message_layout.removeWidget(row)
            row.deleteLater()
        self.message_rows.clear()
        self.welcome.show()
        self.active_bubble = None
        for message in self.messages:
            bubble = self._add_bubble(message.role, message.content, message.image_path)
            bubble.finish()
        self.chat_title.setText(session["title"])
        self.composer.setPlainText(session["draft"])
        if session["image"]:
            self.pending_image = session["image"]
            self.image_name.setText(Path(self.pending_image).name)
            self.image_chip.show()
        self.composer.setFocus()
        self.regenerate_button.setEnabled(bool(self.messages and self.messages[-1].role == "assistant"))

    def _profile_changed(self, profile: str) -> None:
        if profile in PROFILES:
            self.profile = profile
            self.temperature = PROFILE_TEMPERATURES[profile]
            self.settings.setValue("profile", profile)
            self.settings.setValue("temperature", self.temperature)

    def speak_text(self, text: str) -> None:
        if not text.strip():
            return
        if self.speech.state() == QTextToSpeech.State.Speaking:
            self.speech.stop()
            self.status_label.setText("●  Read aloud stopped")
            return
        self.status_label.setText("●  Reading response aloud with a local Windows voice…")
        self.speech.say(text)

    def _filter_sessions(self, query):
        for index, session in enumerate(self.sessions):
            searchable = session["title"] + " " + " ".join(m.content for m in session["messages"])
            self.chat_list.item(index).setHidden(query.casefold() not in searchable.casefold())

    def export_chat(self):
        if not self.messages:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export conversation", "Keep conversation.md", "Markdown (*.md)")
        if not path:
            return
        text = "# " + self.sessions[self.session_index]["title"] + "\n\n"
        for message in self.messages:
            text += "## " + ("You" if message.role == "user" else "Keep") + "\n\n" + message.content + "\n\n"
            if message.image_path:
                text += "[Attached image: " + Path(message.image_path).name + "]\n\n"
        try:
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Could not export", str(exc))

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.temperature, self.max_tokens, self.custom_instructions,
                                self.speech_rate, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.temperature = dialog.temperature
            self.max_tokens = dialog.max_tokens
            self.custom_instructions = dialog.custom_instructions
            self.speech_rate = dialog.speech_rate
            self.speech.setRate(self.speech_rate)
            self.settings.setValue("temperature", self.temperature)
            self.settings.setValue("max_tokens", self.max_tokens)
            self.settings.setValue("custom_instructions", self.custom_instructions)
            self.settings.setValue("speech_rate", self.speech_rate)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.voice_process is not None:
            process = self.voice_process
            self.voice_process = None
            if os.name == "nt" and process.processId():
                QProcess.startDetached("taskkill.exe", ["/PID", str(process.processId()), "/T", "/F"])
            else:
                process.kill()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.start_fallback_after_worker = False
            if self.runtime and self.runtime.process:
                self.runtime.stop()
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        if self.runtime:
            self.runtime.stop()
        self.speech.stop()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Keep")
    app.setApplicationDisplayName("Keep")
    app.setWindowIcon(make_keep_icon())
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    available_fonts = set(QFontDatabase.families())
    body_font = "Segoe UI Variable Text" if "Segoe UI Variable Text" in available_fonts else "Segoe UI"
    app.setFont(QFont(body_font, 11))
    try:
        if "--verify-install" in sys.argv:
            class VerificationClient:
                def list_models(self):
                    return ["qwen3-vl-4b"]

                def stream_chat(self, **kwargs):
                    yield "Keep installation verified."

            window = MainWindow(VerificationClient())
            output = Path(sys.argv[sys.argv.index("--verify-install") + 1])
            timer = QTimer(window)
            attempts = [0]

            def verify():
                attempts[0] += 1
                if attempts[0] > 100:
                    app.exit(1)
                elif window.worker is None and window.model_combo.currentData():
                    if not window.messages:
                        window.composer.setPlainText("Verify the installed application")
                        window.send_message()
                    elif len(window.messages) == 2:
                        window.grab().save(str(output))
                        timer.stop()
                        window.close()
            timer.timeout.connect(verify)
            timer.start(100)
        elif "--verify-image" in sys.argv:
            window = ImageStudio()
            output = Path(sys.argv[sys.argv.index("--verify-image") + 1])
            window.prompt.setPlainText("A cozy cabin beside a lake at sunset, watercolor illustration")
            window.steps.setValue(12)
            window.start()
            timer = QTimer(window)
            attempts = [0]

            def verify_image():
                attempts[0] += 1
                if attempts[0] > 900:
                    window.cancel()
                if window.process is None:
                    timer.stop()
                    success = bool(window.output and window.output.is_file())
                    window.grab().save(str(output))
                    window.close()
                    app.exit(0 if success else 1)
            timer.timeout.connect(verify_image)
            timer.start(1000)
        else:
            window = MainWindow()
    except ValueError as exc:
        QMessageBox.critical(None, "Invalid local server address", str(exc))
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
