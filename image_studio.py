"""Responsive image workspace using a separate, cancellable inference process."""
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
from datetime import datetime
from PySide6.QtCore import QProcess, QSettings, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QLabel, QTextEdit,
    QPushButton, QSpinBox, QProgressBar, QFileDialog, QWidget)


class ImageStudio(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings('Keep', 'KeepDesktop')
        self.root = Path(self.settings.value('image_runtime_root', str(Path(__file__).resolve().parent)))
        self.process = None
        self.output = None
        self.buffer = ''
        self.error_text = ''
        self.cancelled = False
        self.setWindowTitle('Keep · Image studio')
        self.resize(980, 730)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        title = QLabel('Create an image')
        title.setObjectName('chatTitle')
        layout.addWidget(title)
        subtitle = QLabel('Stable Diffusion 1.5 · 512 × 512 · Local GPU/CPU generation · No cloud or API key')
        subtitle.setObjectName('muted')
        layout.addWidget(subtitle)
        columns = QHBoxLayout()
        controls = QVBoxLayout()
        controls.addWidget(QLabel('Describe your image'))
        self.prompt = QTextEdit()
        self.prompt.setObjectName('composer')
        self.prompt.setPlaceholderText('A cozy wooden cabin beside a lake, warm sunset, watercolor illustration…')
        self.prompt.setAcceptRichText(False)
        self.prompt.setMinimumHeight(180)
        controls.addWidget(self.prompt)
        controls.addWidget(QLabel('Detail steps'))
        self.steps = QSpinBox()
        self.steps.setRange(4, 30)
        self.steps.setValue(16)
        controls.addWidget(self.steps)
        note = QLabel('More steps take longer. Generation uses this device’s GPU when available, falling back to CPU. Complex details and lettering can still be imperfect.')
        note.setObjectName('muted')
        note.setWordWrap(True)
        controls.addWidget(note)
        self.generate = QPushButton('Generate image')
        self.generate.setObjectName('primary')
        self.generate.clicked.connect(self.start)
        controls.addWidget(self.generate)
        self.cancel_button = QPushButton('Cancel generation')
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.hide()
        controls.addWidget(self.cancel_button)
        self.save = QPushButton('Save image as…')
        self.save.setEnabled(False)
        self.save.clicked.connect(self.save_image)
        controls.addWidget(self.save)
        self.configure = QPushButton('Choose image runtime folder…')
        self.configure.clicked.connect(self.choose_root)
        controls.addWidget(self.configure)
        controls.addStretch()
        control_widget = QWidget()
        control_widget.setLayout(controls)
        control_widget.setFixedWidth(310)
        columns.addWidget(control_widget)
        self.preview = QLabel('Your next creation\nstarts with a few words.')
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(400, 400)
        self.preview.setStyleSheet('background: #1b1f24; border: 1px solid #2b3137; border-radius: 14px; color: #6b7177; font-size: 16pt;')
        columns.addWidget(self.preview, 1)
        layout.addLayout(columns, 1)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel('Ready. Model files are loaded only when you generate.')
        self.status.setWordWrap(True)
        self.status.setObjectName('muted')
        layout.addWidget(self.status)
        self.check_runtime()

    def check_runtime(self):
        ready = (self.root / '.image-venv/Scripts/python.exe').is_file() and (self.root / 'image-models/stable-diffusion-v1-5/model_index.json').is_file()
        self.generate.setEnabled(ready)
        if not ready:
            self.status.setText('Image setup is not installed here. Choose the Keep project folder containing .image-venv and image-models.')

    def choose_root(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choose the Keep image runtime folder', str(self.root))
        if folder:
            self.root = Path(folder)
            self.settings.setValue('image_runtime_root', folder)
            self.status.setText('Runtime folder selected. Ready to generate locally.')
            self.check_runtime()

    def start(self):
        if self.process:
            return
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            self.status.setText('Describe the image you want to create first.')
            self.prompt.setFocus()
            return
        self.output = self.root / 'generated-images' / (datetime.now().strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(3) + '.png')
        self.cancelled = False
        self.error_text = self.buffer = ''
        self.generate.setEnabled(False)
        self.configure.setEnabled(False)
        self.save.setEnabled(False)
        self.cancel_button.show()
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText('Starting the local image engine…')
        process = QProcess(self)
        self.process = process
        process.readyReadStandardOutput.connect(self.read_progress)
        process.readyReadStandardError.connect(self.read_errors)
        process.finished.connect(self._generation_finished)
        process.errorOccurred.connect(self.process_error)
        process.start(str(self.root / '.image-venv/Scripts/python.exe'), ['-u', str(Path(__file__).resolve().parent / 'image_worker.py')])
        request = dict(model=str(self.root / 'image-models/stable-diffusion-v1-5'), output=str(self.output), prompt=prompt, steps=self.steps.value(), seed=secrets.randbelow(2**31))
        process.write((json.dumps(request) + '\n').encode())
        process.closeWriteChannel()

    def read_progress(self):
        self.buffer += bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            try:
                update = json.loads(line)
            except ValueError:
                continue
            self.status.setText(update.get('status', 'Working…'))
            if 'progress' in update:
                self.progress.setRange(0, 100)
                self.progress.setValue(update['progress'])

    def read_errors(self):
        self.error_text = (self.error_text + bytes(self.process.readAllStandardError()).decode('utf-8', errors='replace'))[-5000:]

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.error_text = self.process.errorString()
            self._generation_finished(1)

    def _generation_finished(self, code, *_):
        if self.process is None:
            return
        self.process.deleteLater()
        self.process = None
        self.generate.setEnabled(True)
        self.configure.setEnabled(True)
        self.cancel_button.hide()
        self.progress.setRange(0, 100)
        if self.cancelled:
            self.status.setText('Generation cancelled. You can try another prompt.')
        elif code != 0 or not self.output or not self.output.is_file():
            self.status.setText('Generation failed: ' + (self.error_text.strip().splitlines()[-1] if self.error_text.strip() else 'No image was produced. Check the image runtime folder.'))
        else:
            self.preview.setPixmap(QPixmap(str(self.output)).scaled(512, 512, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.progress.setValue(100)
            self.status.setText('Ready · Generated offline. A copy is kept in generated-images.')
            self.save.setEnabled(True)

    def cancel(self):
        if self.process:
            self.cancelled = True
            if os.name == 'nt' and self.process.processId():
                # Windows virtualenv Python may launch a child interpreter.
                # Stop only our owned process tree, not unrelated Python jobs.
                killer = QProcess(self)
                killer.finished.connect(killer.deleteLater)
                killer.start('taskkill.exe', ['/PID', str(self.process.processId()), '/T', '/F'])
            else:
                self.process.kill()

    def save_image(self):
        if not self.output or not self.output.exists():
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save generated image', 'keep-image.png', 'PNG image (*.png)')
        if path:
            try:
                if Path(path).resolve() != self.output.resolve():
                    shutil.copy2(self.output, path)
                self.status.setText('Saved to ' + path)
            except OSError as exc:
                self.status.setText('Could not save: ' + str(exc))

    def reject(self):
        if self.process:
            self.cancel()
            self.status.setText('Stopping the image engine. Close again when it stops.')
            return
        super().reject()

    def closeEvent(self, event):
        if self.process:
            self.cancel()
            event.ignore()
        else:
            event.accept()
