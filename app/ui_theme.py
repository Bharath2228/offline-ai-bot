"""Keep's visual system: a private study, not a wellness app.

Ink backgrounds, one warm brass accent, a serif brand/display face over
plain Segoe UI for everything functional. Radius is used with intent —
flat structural panels, small radius on real controls, slightly larger
only on chat bubbles where rounding is a legible convention.
"""

INK = "#15181c"
INK_RAISED = "#1b1f24"
INK_CARD = "#20252a"
HAIRLINE = "#2b3137"
HAIRLINE_SOFT = "#262b31"
PARCHMENT = "#e9e4d8"
PARCHMENT_DIM = "#9aa1a8"
PARCHMENT_FAINT = "#6b7177"
BRASS = "#c89b4c"
BRASS_HOVER = "#d9ad5e"
BRASS_PRESSED = "#a67f3c"
BRASS_DIM = "#5b4e34"
EMBER = "#c1593f"
EMBER_SOFT = "#2b1d1a"

DISPLAY_FONT = "Cambria"

APP_STYLE = f"""
QWidget {{ background: {INK}; color: {PARCHMENT}; font-family: "Segoe UI"; font-size: 10.5pt; }}
QMainWindow, QDialog {{ background: {INK}; }}
QLabel {{ background: transparent; }}

QFrame#sidebar {{ background: {INK_RAISED}; border-right: 1px solid {HAIRLINE}; }}
QFrame#topbar {{ background: {INK}; border-bottom: 1px solid {HAIRLINE_SOFT}; }}
QFrame#composerPanel {{ background: {INK}; border-top: 1px solid {HAIRLINE_SOFT}; }}
QFrame#privacyNote {{ background: transparent; border-top: 1px solid {HAIRLINE}; }}
QFrame#imageChip {{ background: {INK_CARD}; border: 1px solid {HAIRLINE}; border-radius: 8px; }}
QFrame#turnUser {{ background: {INK_RAISED}; border: none; border-left: 2px solid {HAIRLINE}; border-radius: 0; }}
QFrame#turnAssistant {{ background: transparent; border: none; border-left: 2px solid {BRASS_DIM}; border-radius: 0; }}

QLabel#logoMark, QLabel#miniLogo {{ background: transparent; border: none; }}
QLabel#brand {{ color: {PARCHMENT}; font-family: "{DISPLAY_FONT}"; font-size: 23px; font-weight: 700; }}
QLabel#brandCaption {{ color: {PARCHMENT_FAINT}; font-size: 8.5pt; }}
QLabel#eyebrow {{ color: {PARCHMENT_FAINT}; font-size: 8.5pt; font-weight: 600; }}
QLabel#fieldLabel {{ color: {PARCHMENT_DIM}; font-size: 8.5pt; font-weight: 600; }}
QLabel#bubbleRoleAssistant {{ color: {BRASS}; font-size: 9pt; font-weight: 650; }}
QLabel#bubbleRoleUser {{ color: {PARCHMENT_FAINT}; font-size: 9pt; font-weight: 650; }}
QLabel#privacyTitle {{ color: {PARCHMENT}; font-size: 9pt; font-weight: 650; }}
QLabel#hero {{ color: {PARCHMENT}; font-family: "{DISPLAY_FONT}"; font-size: 24pt; font-weight: 600; }}
QLabel#muted, QLabel#topCaption {{ color: {PARCHMENT_DIM}; font-size: 10pt; }}
QLabel#status {{ color: {PARCHMENT_DIM}; font-size: 9.5pt; }}
QLabel#privacyText {{ color: {PARCHMENT_FAINT}; font-size: 9.5pt; }}
QLabel#chatTitle {{ color: {PARCHMENT}; font-family: "{DISPLAY_FONT}"; font-size: 16pt; font-weight: 650; }}

QPushButton {{ background: {INK_CARD}; color: {PARCHMENT_DIM}; border: 1px solid {HAIRLINE}; border-radius: 8px; padding: 9px 15px; font-weight: 550; }}
QPushButton:hover {{ color: {PARCHMENT}; border-color: #454d55; background: #262b31; }}
QPushButton:pressed {{ background: {INK}; }}
QPushButton:disabled {{ color: #565c62; background: {INK_RAISED}; border-color: {HAIRLINE_SOFT}; }}
QPushButton#newChat {{ background: transparent; color: {PARCHMENT}; border: 1px solid {BRASS_DIM}; text-align: left; padding: 11px 14px; font-weight: 600; }}
QPushButton#newChat:hover {{ background: #241f16; border-color: {BRASS}; color: {BRASS_HOVER}; }}
QPushButton#primary {{ background: {BRASS}; color: #1a140a; border: none; font-weight: 650; }}
QPushButton#primary:hover {{ background: {BRASS_HOVER}; }}
QPushButton#primary:pressed {{ background: {BRASS_PRESSED}; }}
QPushButton#primary:disabled {{ background: #3a362a; color: #726c5a; }}
QPushButton#danger {{ background: {EMBER_SOFT}; color: #e2a393; border-color: #4a2c24; }}
QPushButton#danger:hover {{ background: #3a241e; }}
QPushButton#suggestion {{ background: {INK_CARD}; color: {PARCHMENT_DIM}; padding: 14px 15px; text-align: left; border: 1px solid {HAIRLINE}; border-radius: 10px; }}
QPushButton#suggestion:hover {{ color: {PARCHMENT}; border-color: {BRASS_DIM}; background: #262220; }}
QPushButton#copy {{ background: transparent; border: none; color: {PARCHMENT_FAINT}; padding: 3px 7px; font-size: 9.5pt; }}
QPushButton#copy:hover {{ color: {BRASS_HOVER}; background: {INK_CARD}; }}

QComboBox, QSpinBox, QLineEdit {{ background: {INK_CARD}; color: {PARCHMENT}; border: 1px solid {HAIRLINE}; border-radius: 7px; padding: 9px 11px; selection-background-color: {BRASS_DIM}; }}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: #454d55; }}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{ border-color: {BRASS}; }}
QComboBox::drop-down {{ border: none; width: 25px; }}
QComboBox QAbstractItemView {{ background: {INK_CARD}; color: {PARCHMENT}; border: 1px solid {HAIRLINE}; selection-background-color: #332c1d; selection-color: {BRASS_HOVER}; padding: 5px; }}
QSpinBox::up-button, QSpinBox::down-button {{ background: {INK_RAISED}; border: none; width: 18px; }}
QTextEdit#composer {{ background: {INK_CARD}; color: {PARCHMENT}; border: 1px solid {HAIRLINE}; border-radius: 12px; padding: 12px; font-size: 11.5pt; selection-background-color: {BRASS_DIM}; }}
QTextEdit#composer:focus {{ border: 1px solid {BRASS}; }}
QTextBrowser {{ background: transparent; border: none; color: {PARCHMENT}; font-size: 11.5pt; selection-background-color: {BRASS_DIM}; }}
QScrollArea {{ background: {INK}; border: none; }}
QScrollArea > QWidget > QWidget {{ background: {INK}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #33393f; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #454d55; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QSlider::groove:horizontal {{ height: 4px; background: {HAIRLINE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {BRASS_DIM}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {BRASS}; width: 16px; margin: -6px 0; border-radius: 8px; }}
QToolTip {{ background: {INK_CARD}; color: {PARCHMENT}; border: 1px solid {HAIRLINE}; padding: 7px; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ padding: 11px 10px; margin: 2px 0; border-radius: 0; border-left: 2px solid transparent; color: {PARCHMENT_DIM}; }}
QListWidget::item:selected {{ background: #201b14; color: {BRASS_HOVER}; border-left: 2px solid {BRASS}; }}
QListWidget::item:hover {{ background: {INK_CARD}; color: {PARCHMENT}; }}
QTabWidget::pane {{ border: 1px solid {HAIRLINE}; border-radius: 10px; margin-top: 5px; background: {INK_RAISED}; }}
QTabBar::tab {{ background: transparent; padding: 11px 20px; color: {PARCHMENT_FAINT}; }}
QTabBar::tab:selected {{ color: {BRASS_HOVER}; border-bottom: 2px solid {BRASS}; background: {INK_RAISED}; }}
QProgressBar {{ background: {INK_RAISED}; color: {PARCHMENT}; border: 1px solid {HAIRLINE}; border-radius: 6px; text-align: center; min-height: 20px; }}
QProgressBar::chunk {{ background: {BRASS_DIM}; border-radius: 5px; }}
"""
