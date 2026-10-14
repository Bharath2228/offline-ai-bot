"""Record a microphone utterance and transcribe it without network access."""
from __future__ import annotations
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def report(**values):
    print(json.dumps(values, ensure_ascii=True), flush=True)


def main():
    config = json.loads(sys.stdin.readline())
    import numpy as np
    # Load Whisper while the user is speaking. This hides most model startup
    # time without keeping a large background process alive between recordings.
    def load_model():
        from faster_whisper import WhisperModel
        return WhisperModel(str(Path(config["model"])), device="cpu", compute_type="int8",
                            cpu_threads=min(8, os.cpu_count() or 4), local_files_only=True)

    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="keep-whisper")
    model_future = executor.submit(load_model)
    audio_path = config.get("audio_file")
    if audio_path:
        audio = str(Path(audio_path))
    else:
        import sounddevice as sd
        chunks = []

        def capture(indata, frames, timing, status):
            if status:
                report(status="Microphone warning: " + str(status))
            chunks.append(indata.copy())

        report(status="Listening… click Stop when you finish speaking.", listening=True)
        with sd.InputStream(samplerate=16000, channels=1, dtype="float32", callback=capture):
            sys.stdin.readline()
        if not chunks:
            raise RuntimeError("No microphone audio was recorded.")
        audio = np.concatenate(chunks, axis=0).reshape(-1)
        if len(audio) < 4000:
            raise RuntimeError("The recording was too short. Hold the microphone button while speaking.")
    report(status="Transcribing locally…")
    model = model_future.result()
    executor.shutdown(wait=False)
    segments, _ = model.transcribe(audio, beam_size=1, best_of=1, temperature=0,
                                   vad_filter=True, condition_on_previous_text=False)
    transcript = " ".join(segment.text.strip() for segment in segments).strip()
    report(transcript=transcript, status="Voice input ready." if transcript else "I couldn't hear clear speech. Try again closer to the microphone.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report(error=str(exc))
        raise SystemExit(1)
