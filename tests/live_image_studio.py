"""Opt-in end-to-end image generation and visual QA with real local weights."""
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('QT_QPA_PLATFORM', 'windows')
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from PySide6.QtCore import QTimer
from image_studio import ImageStudio
from ui_theme import APP_STYLE


def main():
    app = QApplication([])
    app.setStyle('Fusion')
    app.setFont(QFont('Segoe UI', 11))
    app.setStyleSheet(APP_STYLE)
    window = ImageStudio()
    window.root = Path(__file__).resolve().parent.parent
    window.check_runtime()
    window.show()
    window.prompt.setPlainText('A cozy wooden cabin beside a peaceful lake, pine forest, sunset, watercolor illustration, beautiful warm light')
    window.steps.setValue(16)
    window.start()
    start = time.monotonic()
    previous = ['']
    timer = QTimer(window)

    def check():
        if window.status.text() != previous[0]:
            previous[0] = window.status.text()
            print(previous[0], flush=True)
        if time.monotonic() - start > 900:
            window.cancel()
        if window.process is None:
            timer.stop()
            app.quit()

    timer.timeout.connect(check)
    timer.start(200)
    try:
        app.exec()
        app.processEvents()
        if not window.output or not window.output.exists():
            raise RuntimeError(window.status.text() + '\n' + window.error_text)
        window.grab().save(str(window.root / 'qa/image-studio-verified.png'))
        print(f'Generated {window.output} in {time.monotonic() - start:.1f}s', flush=True)
    finally:
        window.cancel()
        while window.process is not None:
            app.processEvents()
            time.sleep(.02)
        window.close()


if __name__ == '__main__':
    main()
