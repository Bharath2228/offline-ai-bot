from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from main import APP_STYLE, MainWindow


def wait_for(app, predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise TimeoutError("The live desktop check did not finish in time")


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    try:
        wait_for(app, lambda: window.model_combo.currentData() is not None, 150)
        window.profile_combo.blockSignals(True)
        window.profile_combo.setCurrentText("Balanced")
        window.profile_combo.blockSignals(False)
        window.max_tokens = 80
        window.temperature = 0.0
        window.composer.setPlainText("Reply with exactly: DESKTOP END TO END OK")
        window.send_message()
        wait_for(app, lambda: len(window.messages) == 2, 120)
        answer = window.messages[-1].content
        if "DESKTOP END TO END OK" not in answer:
            raise AssertionError(f"Unexpected model response: {answer!r}")
        if output and not window.grab().save(output):
            raise RuntimeError("Could not save the live desktop screenshot")
        print(f"LIVE DESKTOP RESPONSE: {answer}")
    finally:
        window.close()


if __name__ == "__main__":
    main()
