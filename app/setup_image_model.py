"""One-time verified download of Stable Diffusion 1.5, pre-converted to OpenVINO IR
(int8 weights) for inference on Intel GPUs. Never called during generation.
"""
import hashlib
import json
from pathlib import Path
import shutil
import httpx

REPO = 'OpenVINO/stable-diffusion-v1-5-int8-ov'
REVISION = 'cb4df51ea6b332962d8df636d6a4e0209c2f51e9'
ROOT = Path(__file__).resolve().parent.parent / 'image-models' / 'stable-diffusion-v1-5'
ALLOWED_SUFFIXES = ('.json', '.bin', '.xml', '.txt')
# The safety checker ships as a separate ~1.2 GB PyTorch model that this pipeline
# never loads (it's disabled below), and .ipynb_checkpoints is editor junk.
SKIP_PREFIXES = ('safety_checker/', '.ipynb_checkpoints')


def disable_safety_checker():
    path = ROOT / 'model_index.json'
    config = json.loads(path.read_text())
    config['safety_checker'] = [None, None]
    config['feature_extractor'] = [None, None]
    config['requires_safety_checker'] = False
    path.write_text(json.dumps(config, indent=2))


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=90) as client:
        response = client.get(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}', params={'blobs': 'true'})
        response.raise_for_status()
        files = [f for f in response.json()['siblings']
                 if f['rfilename'].endswith(ALLOWED_SUFFIXES) and not any(p in f['rfilename'] for p in SKIP_PREFIXES)]
        required = sum(f['size'] for f in files if not (ROOT / f['rfilename']).exists())
        if shutil.disk_usage(ROOT).free < required + 500 * 1024**2:
            raise RuntimeError('Not enough disk space for Stable Diffusion 1.5.')
        for item in files:
            path = ROOT / item['rfilename']
            expected_hash = (item.get('lfs') or {}).get('sha256')
            if path.exists() and path.stat().st_size == item['size']:
                with path.open('rb') as existing:
                    valid = not expected_hash or hashlib.file_digest(existing, 'sha256').hexdigest() == expected_hash
                if valid:
                    print('Verified existing ' + item['rfilename'], flush=True)
                    continue
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(path.suffix + '.partial')
            digest = hashlib.sha256()
            received = 0
            print('Downloading ' + item['rfilename'], flush=True)
            try:
                with client.stream('GET', f'https://huggingface.co/{REPO}/resolve/{REVISION}/{item["rfilename"]}') as download:
                    download.raise_for_status()
                    with partial.open('wb') as output:
                        for chunk in download.iter_bytes(1024 * 1024):
                            output.write(chunk)
                            digest.update(chunk)
                            received += len(chunk)
                if received != item['size'] or (expected_hash and digest.hexdigest() != expected_hash):
                    raise RuntimeError('Model verification failed: ' + item['rfilename'])
                partial.replace(path)
            finally:
                partial.unlink(missing_ok=True)
        disable_safety_checker()
        print(f'Stable Diffusion 1.5 (OpenVINO) ready: {ROOT}', flush=True)


if __name__ == '__main__':
    main()
