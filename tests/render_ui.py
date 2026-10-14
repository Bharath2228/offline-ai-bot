from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from PySide6.QtWidgets import QApplication

from main import APP_STYLE, MainWindow


class PreviewClient:
    def list_models(self):
        return ["lmstudio-community/Qwen3-VL-4B-Instruct-Q4_K_M.gguf"]

    def stream_chat(self, **kwargs):
        yield "Everything is running locally. "
        yield "Your Qwen vision model is ready for text and image questions."


def wait_for(app, predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise TimeoutError("Desktop preview did not settle")


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Usage: render_ui.py OUTPUT.png [welcome]")
    mode = sys.argv[2] if len(sys.argv) == 3 else "chat"
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow(PreviewClient())
    window.show()
    wait_for(app, lambda: window.model_combo.currentData() is not None)
    if mode != "welcome":
        window.composer.setPlainText("Confirm that this conversation stays offline.")
        window.send_message()
        wait_for(app, lambda: len(window.messages) == 2)
    # Allow deferred native paint events to finish before capturing visual QA.
    for _ in range(12):
        app.processEvents()
        time.sleep(0.02)
    if not window.grab().save(sys.argv[1]):
        raise RuntimeError("Could not save desktop preview")
    window.close()


if __name__ == "__main__":
    main()
