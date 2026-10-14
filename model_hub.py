"""Explicit online discovery and verified GGUF downloads; no chat data is sent."""
from pathlib import Path, PurePosixPath
from threading import Event
from urllib.parse import quote
import hashlib
import re
import shutil
import httpx


class HubError(RuntimeError):
    pass


class ModelHub:
    def __init__(self, root=None, transport=None):
        self.root = Path(root) if root else Path.home() / '.lmstudio' / 'models'
        self.transport = transport

    def client(self):
        return httpx.Client(timeout=30, follow_redirects=True, transport=self.transport)

    def search(self, query):
        with self.client() as client:
            response = client.get('https://huggingface.co/api/models', params={
                'search': query.strip(), 'filter': 'gguf', 'sort': 'downloads', 'direction': -1, 'limit': 30})
            response.raise_for_status()
            return [m for m in response.json() if isinstance(m, dict) and m.get('id')]

    def files(self, repo):
        self.safe_parts(repo)
        with self.client() as client:
            response = client.get('https://huggingface.co/api/models/' + quote(repo, safe='/'), params={'blobs': 'true'})
            response.raise_for_status()
            info = response.json()
        revision = info['sha']
        files = []
        for item in info.get('siblings', []):
            name = item.get('rfilename', '')
            # Split GGUF shards need an explicit multi-file workflow; do not offer an incomplete shard.
            if name.lower().endswith('.gguf') and not re.search(r'-\d{5}-of-\d{5}', name):
                self.safe_parts(name)
                lfs = item.get('lfs') or {}
                files.append({'name': name, 'size': item.get('size', lfs.get('size', 0)),
                              'sha256': lfs.get('sha256'), 'revision': revision})
        return files

    @staticmethod
    def safe_parts(value):
        path = PurePosixPath(value)
        if not value or path.is_absolute() or any(p in ('', '.', '..') for p in value.split('/')) or '\\' in value or ':' in value:
            raise HubError('Invalid model path')
        if any(p.endswith((' ', '.')) or p.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))} for p in path.parts):
            raise HubError('Invalid Windows model path')
        return path.parts

    def download(self, repo, entry, cancel: Event, progress):
        destination = self.root.joinpath(*self.safe_parts(repo), *self.safe_parts(entry['name']))
        if not destination.resolve().is_relative_to(self.root.resolve()):
            raise HubError('Model destination is outside the model library.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected = int(entry.get('size') or 0)
        if expected and shutil.disk_usage(destination.parent).free < expected + 100 * 1024**2:
            raise HubError('Not enough free disk space for this model.')
        partial = destination.with_suffix(destination.suffix + '.partial')
        digest = hashlib.sha256()
        received = 0
        url = 'https://huggingface.co/' + quote(repo, safe='/') + '/resolve/' + quote(entry['revision'], safe='') + '/' + quote(entry['name'], safe='/')
        try:
            with self.client() as client, client.stream('GET', url) as response:
                response.raise_for_status()
                with partial.open('wb') as output:
                    for chunk in response.iter_bytes(256 * 1024):
                        if cancel.is_set():
                            raise HubError('Download cancelled.')
                        output.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        progress(received, expected)
            if cancel.is_set():
                raise HubError('Download cancelled.')
            if expected and received != expected:
                raise HubError('The download was incomplete. Please try again.')
            if entry.get('sha256') and digest.hexdigest() != entry['sha256']:
                raise HubError('The download failed its integrity check. Please try again.')
            with partial.open('rb') as model:
                if model.read(4) != b'GGUF':
                    raise HubError('The downloaded file is not a GGUF model.')
            partial.replace(destination)
            return destination
        finally:
            partial.unlink(missing_ok=True)
