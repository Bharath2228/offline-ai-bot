from pathlib import Path
from threading import Event
from PySide6.QtCore import QThread, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from urllib.parse import quote
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QLineEdit, QListWidget, QListWidgetItem, QComboBox, QProgressBar)
from model_hub import ModelHub


class HubWorker(QThread):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, hub, action, *args):
        super().__init__()
        self.hub, self.action, self.args = hub, action, args
        self.cancel = Event()

    def run(self):
        try:
            if self.action == 'download':
                value = self.hub.download(*self.args, self.cancel, self.report)
            else:
                value = getattr(self.hub, self.action)(*self.args)
            self.result.emit(value)
        except Exception as exc:
            self.error.emit(str(exc))

    def report(self, received, total):
        self.progress.emit(int(100 * received / total) if total else 0,
                           f'{received / 1024**3:.2f} / {total / 1024**3:.2f} GB')


class ModelBrowser(QDialog):
    def __init__(self, parent=None, hub=None):
        super().__init__(parent)
        self.hub = hub or ModelHub()
        self.worker = None
        self.selected_path = None
        self.entries = []
        self.repo = None
        self.setWindowTitle('Keep · Model library')
        self.resize(880, 660)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        title = QLabel('Your model library')
        title.setObjectName('chatTitle')
        layout.addWidget(title)
        subtitle = QLabel('Download once. Chat privately, even without an internet connection.')
        subtitle.setObjectName('muted')
        layout.addWidget(subtitle)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        installed_page = QWidget()
        installed_layout = QVBoxLayout(installed_page)
        self.installed = QListWidget()
        installed_layout.addWidget(self.installed)
        self.load_button = QPushButton('Use selected model')
        self.load_button.setObjectName('primary')
        self.load_button.clicked.connect(self.use_selected)
        installed_layout.addWidget(self.load_button)
        self.tabs.addTab(installed_page, 'Installed')
        discover = QWidget()
        online = QVBoxLayout(discover)
        search_row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('Search Qwen, Gemma, Llama, coding models…')
        self.search_button = QPushButton('Search Hugging Face')
        self.search_button.clicked.connect(self.search)
        self.query.returnPressed.connect(self.search)
        search_row.addWidget(self.query, 1)
        search_row.addWidget(self.search_button)
        online.addLayout(search_row)
        self.results = QListWidget()
        self.results.currentRowChanged.connect(self.select_repo)
        online.addWidget(self.results, 1)
        self.files = QComboBox()
        online.addWidget(self.files)
        self.card_button = QPushButton('View model details and license ↗')
        self.card_button.setEnabled(False)
        self.card_button.clicked.connect(self.open_model_card)
        online.addWidget(self.card_button)
        note = QLabel('Q4_K_M is a compact starting point. Vision models also need a matching mmproj file.\nPublic, single-file GGUF downloads are supported. Model licenses and hardware needs vary.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        online.addWidget(note)
        self.download_button = QPushButton('Download selected file')
        self.download_button.setObjectName('primary')
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.download)
        online.addWidget(self.download_button)
        self.tabs.addTab(discover, 'Discover && download')
        self.status = QLabel('Browse installed models, or search online in Discover.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.cancel_button = QPushButton('Cancel download')
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self.cancel_download)
        layout.addWidget(self.cancel_button)
        self.refresh_installed()

    def refresh_installed(self):
        self.installed.clear()
        self.paths = sorted(p for p in self.hub.root.rglob('*.gguf') if not p.name.lower().startswith('mmproj'))
        for path in self.paths:
            lowered = path.name.lower()
            size_matches = __import__('re').findall(r'(\d+(?:\.\d+)?)b', lowered)
            size = float(size_matches[-1]) if size_matches else 0
            vision = 'vl' in lowered or 'vision' in lowered
            recommendation = (' · Recommended for text' if size >= 7 and not vision
                              else ' · Vision model' if vision else '')
            item = QListWidgetItem(path.stem.replace('-', ' ') + f'\n{path.stat().st_size / 1024**3:.1f} GB · Ready on this device' + recommendation)
            item.setToolTip(str(path))
            self.installed.addItem(item)
        if self.paths:
            self.installed.setCurrentRow(0)
        self.load_button.setEnabled(bool(self.paths))

    def run_job(self, action, callback, *args):
        if self.worker:
            return
        self.worker = HubWorker(self.hub, action, *args)
        self.worker.result.connect(callback)
        self.worker.error.connect(lambda text: self.status.setText('Could not complete: ' + text))
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.job_finished)
        self.search_button.setEnabled(False)
        self.results.setEnabled(False)
        self.download_button.setEnabled(False)
        self.load_button.setEnabled(False)
        self.worker.start()

    def job_finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.search_button.setEnabled(True)
        self.results.setEnabled(True)
        self.load_button.setEnabled(bool(self.paths))
        self.download_button.setEnabled(bool(self.entries))
        self.cancel_button.hide()

    def search(self):
        if self.worker:
            return
        self.entries = []
        self.files.clear()
        self.repo = None
        self.card_button.setEnabled(False)
        self.status.setText('Searching public GGUF models on Hugging Face…')
        self.run_job('search', self.show_results, self.query.text())

    def show_results(self, results):
        self.results.clear()
        for model in results:
            item = QListWidgetItem(model['id'] + f"\n{model.get('downloads', 0):,} downloads · GGUF")
            item.setData(Qt.ItemDataRole.UserRole, model['id'])
            self.results.addItem(item)
        self.status.setText(f'{len(results)} models found. Select one to browse its download files.')

    def select_repo(self, row):
        if self.worker or row < 0:
            return
        self.repo = self.results.item(row).data(Qt.ItemDataRole.UserRole)
        self.card_button.setEnabled(True)
        self.entries = []
        self.files.clear()
        self.status.setText('Checking available files and download sizes…')
        self.run_job('files', self.show_files, self.repo)

    def show_files(self, entries):
        self.entries = sorted(entries, key=lambda e: ('q4_k_m' not in e['name'].lower(), e['name']))
        for entry in self.entries:
            self.files.addItem(f"{entry['name']} · {entry['size'] / 1024**3:.2f} GB")
        self.status.setText('Choose a file, then Download. This uses your internet connection.' if entries else 'No supported single-file GGUF downloads in this repository.')

    def open_model_card(self):
        if self.repo:
            QDesktopServices.openUrl(QUrl('https://huggingface.co/' + quote(self.repo, safe='/')))

    def download(self):
        if self.worker or not self.entries:
            return
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_button.show()
        self.status.setText('Downloading… the completed file will appear under Installed.')
        self.run_job('download', self.downloaded, self.repo, self.entries[self.files.currentIndex()])

    def downloaded(self, path):
        self.progress.setValue(100)
        self.status.setText('Downloaded and verified: ' + path.name + '. Open Installed to use it.')
        self.refresh_installed()

    def update_progress(self, value, label):
        self.progress.setValue(value)
        self.status.setText('Downloading · ' + label)

    def cancel_download(self):
        if self.worker:
            self.worker.cancel.set()
            self.status.setText('Cancelling download…')

    def use_selected(self):
        if self.worker or self.installed.currentRow() < 0:
            return
        self.selected_path = self.paths[self.installed.currentRow()]
        self.accept()

    def reject(self):
        if self.worker:
            self.cancel_download()
            self.status.setText('Please wait for the current operation to finish before closing.')
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker:
            self.cancel_download()
            event.ignore()
        else:
            event.accept()
