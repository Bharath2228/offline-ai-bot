"""Opt-in offline speech-to-text verification using a supplied WAV file."""
import argparse
import os
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    args = parser.parse_args()
    from faster_whisper import WhisperModel
    root = Path(__file__).resolve().parent.parent
    model = WhisperModel(str(root / "voice-models/faster-whisper-tiny"), device="cpu",
                         compute_type="int8", cpu_threads=8, local_files_only=True)
    segments, info = model.transcribe(str(args.audio), beam_size=1, temperature=0,
                                      vad_filter=True, condition_on_previous_text=False)
    transcript = " ".join(segment.text.strip() for segment in segments).strip()
    print(f"language={info.language} transcript={transcript!r}")
    words = transcript.casefold()
    if "voice" not in words or "offline" not in words:
        raise SystemExit("Voice transcription did not match the test sentence.")


if __name__ == "__main__":
    main()
