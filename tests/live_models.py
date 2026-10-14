"""Opt-in test of installed GGUF models on a dedicated loopback port."""
import time
from pathlib import Path
from lm_studio_client import LMStudioClient, LMStudioError, ChatMessage
from local_runtime import LocalModelRuntime, discover_runtime_assets


def main():
    models = sorted(p for p in (Path.home() / '.lmstudio/models').rglob('*.gguf') if not p.name.startswith('mmproj'))
    for model in models:
        assets = discover_runtime_assets(model_path=model)
        runtime = LocalModelRuntime(assets, port=1249, log_path=Path('qa/model-check.log'))
        client = LMStudioClient('http://127.0.0.1:1249/v1')
        try:
            runtime.start()
            deadline = time.monotonic() + 150
            while True:
                try:
                    names = client.list_models()
                    break
                except LMStudioError:
                    if runtime.has_exited() or time.monotonic() > deadline:
                        raise RuntimeError('Model startup failed: ' + str(model))
                    time.sleep(0.5)
            answer = ''.join(client.stream_chat(model=names[0], messages=[ChatMessage('user', 'Say hello in one short sentence. /no_think')], temperature=0, max_tokens=64))
            assert answer.strip(), 'Empty model response'
            print(model.name + ': ' + repr(answer), flush=True)
        finally:
            runtime.stop()

if __name__ == '__main__':
    main()
