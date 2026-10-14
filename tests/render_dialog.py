"""Render one Keep secondary surface for native visual QA."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from image_studio import ImageStudio
from main import SettingsDialog
from model_browser import ModelBrowser
from ui_theme import APP_STYLE


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in {"settings", "models", "images"}:
        raise SystemExit("Usage: render_dialog.py settings|models|images OUTPUT.png")
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    if sys.argv[1] == "settings":
        window = SettingsDialog(0.6, 2048, "", 0.0)
    elif sys.argv[1] == "models":
        window = ModelBrowser()
    else:
        window = ImageStudio()
    window.show()
    for _ in range(12):
        app.processEvents()
        time.sleep(0.02)
    if not window.grab().save(sys.argv[2]):
        raise RuntimeError("Could not save dialog preview")
    window.close()


if __name__ == "__main__":
    main()
