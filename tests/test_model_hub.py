import hashlib
from pathlib import Path
import tempfile
from threading import Event
import unittest
import httpx
from model_hub import ModelHub, HubError


class HubTests(unittest.TestCase):
    def test_search_and_files(self):
        def respond(request):
            if request.url.path == '/api/models':
                self.assertEqual(request.url.params['filter'], 'gguf')
                self.assertEqual(request.url.params['search'], 'Gemma')
                return httpx.Response(200, json=[{'id': 'org/gemma'}, {}])
            return httpx.Response(200, json={'sha': 'pinned', 'siblings': [
                {'rfilename': 'model-Q4_K_M.gguf', 'size': 12, 'lfs': {'sha256': 'abc'}},
                {'rfilename': 'model-00001-of-00002.gguf'}, {'rfilename': 'README.md'}]})
        hub = ModelHub(transport=httpx.MockTransport(respond))
        self.assertEqual(hub.search(' Gemma '), [{'id': 'org/gemma'}])
        self.assertEqual(hub.files('org/gemma'), [{'name': 'model-Q4_K_M.gguf', 'size': 12, 'sha256': 'abc', 'revision': 'pinned'}])

    def test_verified_download_and_progress(self):
        content = b'GGUF' + b'a' * 100
        with tempfile.TemporaryDirectory() as directory:
            hub = ModelHub(directory, httpx.MockTransport(lambda r: httpx.Response(200, content=content)))
            progress = []
            entry = dict(name='model.gguf', size=len(content), sha256=hashlib.sha256(content).hexdigest(), revision='abc')
            path = hub.download('org/model', entry, Event(), lambda *p: progress.append(p))
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(progress[-1], (len(content), len(content)))
            self.assertEqual(list(Path(directory).rglob('*.partial')), [])

    def test_failures_preserve_existing_model_and_remove_partial(self):
        for content, size, digest, cancelled in [(b'GGUFabc', 99, None, False), (b'HTMLabc', 7, None, False), (b'GGUFabc', 7, 'bad', False), (b'GGUFabc', 7, None, True)]:
            with self.subTest(content=content, cancelled=cancelled), tempfile.TemporaryDirectory() as directory:
                hub = ModelHub(directory, httpx.MockTransport(lambda r: httpx.Response(200, content=content)))
                path = Path(directory) / 'org/model/model.gguf'
                path.parent.mkdir(parents=True)
                path.write_bytes(b'existing model')
                event = Event()
                if cancelled:
                    event.set()
                with self.assertRaises(HubError):
                    hub.download('org/model', dict(name='model.gguf', size=size, sha256=digest, revision='abc'), event, lambda *_: None)
                self.assertEqual(path.read_bytes(), b'existing model')
                self.assertEqual(list(Path(directory).rglob('*.partial')), [])

    def test_rejects_unsafe_paths(self):
        for path in ('../escape', '/absolute', 'repo//file', 'a\\b', 'C:drive', 'CON.gguf', 'name./file'):
            with self.subTest(path=path), self.assertRaises(HubError):
                ModelHub.safe_parts(path)
