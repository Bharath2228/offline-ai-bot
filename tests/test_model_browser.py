import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import time
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from model_browser import ModelBrowser


class FakeHub:
    def __init__(self, root):
        self.root = Path(root)
        self.calls = []

    def search(self, query):
        self.calls.append(('search', query))
        return [{'id': 'org/qwen', 'downloads': 123}]

    def files(self, repo):
        return [dict(name='qwen-Q4_K_M.gguf', size=1024)]

    def download(self, repo, entry, cancel, progress):
        path = self.root / entry['name']
        path.write_bytes(b'GGUFtest')
        progress(1024, 1024)
        return path


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def settle(self, browser):
        deadline = time.monotonic() + 3
        while browser.worker is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertIsNone(browser.worker)

    def test_explicit_search_download_and_select(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = FakeHub(directory)
            browser = ModelBrowser(hub=hub)
            self.assertEqual(hub.calls, [])
            browser.query.setText('qwen')
            browser.search_button.click()
            self.settle(browser)
            self.assertEqual(browser.results.count(), 1)
            browser.results.setCurrentRow(0)
            self.settle(browser)
            self.assertTrue(browser.download_button.isEnabled())
            browser.download_button.click()
            self.settle(browser)
            self.assertEqual(browser.installed.count(), 1)
            browser.load_button.click()
            self.assertEqual(browser.selected_path.name, 'qwen-Q4_K_M.gguf')
            browser.close()
