"""Download the small multilingual speech-recognition model for offline use."""
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent / "voice-models" / "faster-whisper-tiny"


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id="Systran/faster-whisper-tiny",
        revision="main",
        local_dir=ROOT,
        allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"],
    )
    required = ("config.json", "model.bin", "tokenizer.json")
    missing = [name for name in required if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError("Voice model is incomplete: " + ", ".join(missing))
    print("Offline voice model ready: " + str(ROOT))


if __name__ == "__main__":
    main()
