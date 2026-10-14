import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QProcess, QEventLoop, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from image_studio import ImageStudio


class ImageStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_missing_runtime_and_empty_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            window = ImageStudio()
            window.root = Path(directory)
            window.check_runtime()
            self.assertFalse(window.generate.isEnabled())
            window.start()
            self.assertIsNone(window.process)
            self.assertIn('Describe', window.status.text())
            window.close()

    @unittest.skipIf(os.name == 'nt' and os.environ.get('QT_QPA_PLATFORM') == 'offscreen',
                     'Windows process-handle notifications require QT_QPA_PLATFORM=windows; covered by native test run')
    def test_cancel_stops_real_child_process(self):
        window = ImageStudio()
        process = QProcess(window)
        window.process = process
        process.finished.connect(window._generation_finished)
        process.start(sys.executable, ['-c', 'import time; time.sleep(30)'])
        self.assertTrue(process.waitForStarted(3000))
        loop = QEventLoop()
        process.finished.connect(loop.quit)
        QTimer.singleShot(100, window.cancel)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        self.assertIsNone(window.process)
        self.assertIn('cancelled', window.status.text())
        self.assertTrue(window.generate.isEnabled())
        window.close()

    def test_success_preview_and_save(self):
        with tempfile.TemporaryDirectory() as directory:
            window = ImageStudio()
            window.output = Path(directory) / 'output.png'
            pixmap = QPixmap(32, 32)
            pixmap.fill()
            pixmap.save(str(window.output))
            window.process = QProcess(window)
            window._generation_finished(0)
            self.assertTrue(window.save.isEnabled())
            self.assertFalse(window.preview.pixmap().isNull())
            destination = Path(directory) / 'saved.png'
            with patch('image_studio.QFileDialog.getSaveFileName', return_value=(str(destination), '')):
                window.save_image()
            self.assertEqual(destination.read_bytes(), window.output.read_bytes())
            window.close()
