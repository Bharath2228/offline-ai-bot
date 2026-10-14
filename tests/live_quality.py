"""Opt-in deterministic quality gate for installed chat models."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lm_studio_client import ChatMessage, LMStudioClient, LMStudioError
from local_runtime import LocalModelRuntime, discover_runtime_assets
from assistant_profiles import build_system_prompt


SYSTEM = build_system_prompt("Balanced")

CASES = [
    ("exact instruction", [ChatMessage("user", "Reply with exactly ORANGE-7 and nothing else.")],
     lambda value: value.strip() == "ORANGE-7"),
    ("arithmetic", [ChatMessage("user", "There are 23 boxes with 18 bolts each. 27 bolts are removed. Give only the final number.")],
     lambda value: "387" in value.replace(",", "")),
    ("factual restraint", [ChatMessage("user", "What is the capital of Australia? Answer in one short sentence.")],
     lambda value: "canberra" in value.casefold() and "sydney is" not in value.casefold()),
    ("conversation memory", [ChatMessage("user", "Remember that my project code is CEDAR-482. Reply OK."),
                             ChatMessage("assistant", "OK."),
                             ChatMessage("user", "What is my project code? Give only the code.")],
     lambda value: value.strip().strip("`.* ") == "CEDAR-482"),
    ("concise explanation", [ChatMessage("user", "Explain why the sky looks blue in at most two sentences.")],
     lambda value: "scatter" in value.casefold() and value.count(".") <= 3 and len(value) < 500),
]


def wait_for_model(runtime, client):
    deadline = time.monotonic() + 180
    while True:
        try:
            models = client.list_models()
            if models:
                return models[0]
        except LMStudioError:
            pass
        if runtime.has_exited() or time.monotonic() > deadline:
            raise RuntimeError("Model did not start. See qa/quality-runtime.log")
        time.sleep(.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3-8b")
    args = parser.parse_args()
    candidates = [p for p in (Path.home() / ".lmstudio/models").rglob("*.gguf")
                  if not p.name.lower().startswith("mmproj") and args.model.casefold() in p.name.casefold()]
    if not candidates:
        raise SystemExit("No matching model: " + args.model)
    model_path = candidates[0]
    root = Path(__file__).resolve().parent.parent
    runtime = LocalModelRuntime(discover_runtime_assets(model_path=model_path), port=1251,
                                log_path=root / "qa/quality-runtime.log")
    client = LMStudioClient("http://127.0.0.1:1251/v1")
    results = []
    try:
        runtime.start()
        model = wait_for_model(runtime, client)
        for name, conversation, check in CASES:
            started = time.monotonic()
            answer = "".join(client.stream_chat(
                model=model, messages=[ChatMessage("system", SYSTEM), *conversation],
                temperature=.2, max_tokens=300,
            )).strip()
            result = {"case": name, "passed": bool(check(answer)),
                      "seconds": round(time.monotonic() - started, 2), "answer": answer}
            results.append(result)
            print(json.dumps(result, ensure_ascii=True), flush=True)
    finally:
        runtime.stop()
    passed = sum(item["passed"] for item in results)
    report = {"model": model_path.name, "passed": passed, "total": len(results), "cases": results}
    (root / "qa" / "quality-results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"QUALITY SCORE {passed}/{len(results)} for {model_path.name}", flush=True)
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
