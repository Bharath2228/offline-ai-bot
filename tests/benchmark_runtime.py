"""Compare local Qwen throughput across conservative GPU offload levels."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lm_studio_client import ChatMessage, LMStudioClient, LMStudioError
from local_runtime import LocalModelRuntime, discover_runtime_assets


def run(layers: int, port: int) -> dict:
    candidates = [
        path for path in (Path.home() / ".lmstudio/models").rglob("*.gguf")
        if "qwen3-8b" in path.name.casefold() and not path.name.casefold().startswith("mmproj")
    ]
    if not candidates:
        raise RuntimeError("Qwen 3 8B was not found")
    root = Path(__file__).resolve().parent.parent
    runtime = LocalModelRuntime(
        discover_runtime_assets(model_path=candidates[0]), port=port, gpu_layers=layers,
        log_path=root / "qa" / f"benchmark-{layers}-layers.log",
    )
    client = LMStudioClient(f"http://127.0.0.1:{port}/v1")
    started = time.monotonic()
    try:
        runtime.start()
        deadline = time.monotonic() + 180
        while True:
            try:
                models = client.list_models()
                if models:
                    break
            except LMStudioError:
                pass
            if runtime.has_exited() or time.monotonic() > deadline:
                raise RuntimeError(f"Runtime failed with {layers} GPU layers")
            time.sleep(0.2)
        ready_seconds = time.monotonic() - started
        samples = []
        for prompt in (
            "Reply with exactly SPEED READY",
            "In one short sentence, explain why leaves look green.",
        ):
            sample_start = time.monotonic()
            answer = "".join(client.stream_chat(
                model=models[0], messages=[ChatMessage("user", prompt)],
                temperature=0, max_tokens=48,
            )).strip()
            samples.append({"seconds": round(time.monotonic() - sample_start, 2), "answer": answer})
        return {"gpu_layers": layers, "ready_seconds": round(ready_seconds, 2), "samples": samples}
    finally:
        runtime.stop()


if __name__ == "__main__":
    for index, layer_count in enumerate((0, 5, 10)):
        print(json.dumps(run(layer_count, 1260 + index), ensure_ascii=True), flush=True)
