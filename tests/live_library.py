"""Opt-in real model search, download, selection, and inference check."""
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('QT_QPA_PLATFORM', 'windows')
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from model_browser import ModelBrowser
from model_hub import ModelHub
from ui_theme import APP_STYLE
from local_runtime import LocalModelRuntime, discover_runtime_assets
from lm_studio_client import LMStudioClient, LMStudioError, ChatMessage


def main():
    root = Path(__file__).resolve().parent.parent
    app = QApplication([])
    app.setFont(QFont('Segoe UI', 11))
    app.setStyle('Fusion')
    app.setStyleSheet(APP_STYLE)
    browser = ModelBrowser(hub=ModelHub(root / 'qa/downloaded-models'))
    browser.show()

    def settle():
        deadline = time.monotonic() + 300
        while browser.worker is not None:
            app.processEvents()
            if time.monotonic() > deadline:
                raise TimeoutError(browser.status.text())
            time.sleep(.02)
        print(browser.status.text(), flush=True)

    try:
        browser.tabs.setCurrentIndex(1)
        browser.query.setText('SmolLM2-135M-Instruct')
        browser.search_button.click()
        settle()
        repo = 'bartowski/SmolLM2-135M-Instruct-GGUF'
        row = next(i for i in range(browser.results.count()) if browser.results.item(i).data(Qt.ItemDataRole.UserRole) == repo)
        browser.results.setCurrentRow(row)
        settle()
        index = next(i for i, entry in enumerate(browser.entries) if entry['name'].endswith('Q4_K_M.gguf'))
        browser.files.setCurrentIndex(index)
        app.processEvents()
        browser.grab().save(str(root / 'qa/library-discover.png'))
        browser.download_button.click()
        settle()
        browser.tabs.setCurrentIndex(0)
        app.processEvents()
        browser.grab().save(str(root / 'qa/library-installed.png'))
        browser.load_button.click()
        assert browser.selected_path and browser.selected_path.is_file(), browser.status.text()
        model = browser.selected_path
    finally:
        if browser.worker:
            browser.cancel_download()
            settle()
        browser.close()
    runtime = LocalModelRuntime(discover_runtime_assets(model_path=model), port=1249, log_path=root / 'qa/library-runtime.log')
    client = LMStudioClient('http://127.0.0.1:1249/v1')
    try:
        runtime.start()
        deadline = time.monotonic() + 120
        while True:
            try:
                names = client.list_models()
                break
            except LMStudioError:
                if runtime.has_exited() or time.monotonic() > deadline:
                    raise RuntimeError('Downloaded model did not load')
                time.sleep(.5)
        answer = ''.join(client.stream_chat(model=names[0], messages=[ChatMessage('user', 'Say hello in a short sentence.')], temperature=0, max_tokens=32))
        assert answer.strip()
        print('Verified downloaded model response: ' + repr(answer), flush=True)
    finally:
        runtime.stop()


if __name__ == '__main__':
    main()
