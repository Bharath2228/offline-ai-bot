from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class LocalRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeAssets:
    server: Path
    model: Path
    vision_projector: Path | None


def _version_key(path: Path) -> tuple[int, ...]:
    values = re.findall(r"\d+", path.parent.name)
    return tuple(int(value) for value in values[-3:]) if values else (0,)


def discover_runtime_assets(lmstudio_home: Path | None = None, model_path: Path | None = None) -> RuntimeAssets | None:
    root = lmstudio_home or (Path.home() / ".lmstudio")
    model_root = root / "models"
    backend_root = root / "extensions" / "backends"
    if not model_root.is_dir() or not backend_root.is_dir():
        return None

    model_candidates = [
        path
        for path in model_root.rglob("*.gguf")
        if not path.name.lower().startswith("mmproj")
        and path.is_file()
    ]
    if not model_candidates and model_path is None:
        return None
    model_candidates.sort(
        key=lambda path: (
            max([float(value) for value in re.findall(r"(\d+(?:\.\d+)?)b", path.name.lower())] or [0]),
            int("vl" not in path.name.lower() and "vision" not in path.name.lower()),
            int("q4_k_m" in path.name.lower()),
            path.stat().st_mtime,
        ),
        reverse=True,
    )
    model = model_path or model_candidates[0]
    if not model.is_file() or model.suffix.lower() != ".gguf" or model.name.lower().startswith("mmproj"):
        return None
    projectors = sorted(model.parent.glob("mmproj*.gguf"))

    server_patterns = [
        "llama.cpp-win-x86_64-vulkan-avx2-*/llama-server.exe",
        "llama.cpp-win-x86_64-nvidia-cuda-avx2-*/llama-server.exe",
        "llama.cpp-win-x86_64-avx2-*/llama-server.exe",
    ]
    server = None
    for pattern in server_patterns:
        candidates = sorted(backend_root.glob(pattern), key=_version_key, reverse=True)
        if candidates:
            server = candidates[0]
            break
    if server is None:
        return None
    return RuntimeAssets(server=server, model=model, vision_projector=projectors[0] if projectors else None)


class LocalModelRuntime:
    def __init__(
        self,
        assets: RuntimeAssets | None = None,
        *,
        port: int = 1234,
        log_path: Path | None = None,
        gpu_layers: int | None = None,
    ) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("Local runtime port must be between 1 and 65535.")
        self.assets = assets or discover_runtime_assets()
        self.port = port
        self.log_path = log_path or (Path(__file__).resolve().parent.parent / "keep-runtime.log")
        self.gpu_layers = gpu_layers
        self.process: subprocess.Popen | None = None
        self._log_file = None

    @property
    def available(self) -> bool:
        return self.assets is not None

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        if not self.assets:
            raise LocalRuntimeError("No installed GGUF model and compatible LM Studio runtime could be found.")
        self._log_file = self.log_path.open("a", encoding="utf-8")
        command = [
            str(self.assets.server),
            "-m",
            str(self.assets.model),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "-c",
            "8192",
            "--parallel",
            "1",
            "--image-min-tokens",
            "1024",
        ]
        backend_name = self.assets.server.parent.name.lower()
        if self.assets.vision_projector:
            command.extend(["--mmproj", str(self.assets.vision_projector)])
        if "vulkan" in backend_name or "cuda" in backend_name:
            # On this machine's 2 GB Intel Arc GPU, even modest offload triggers
            # Windows paging. Direct benchmarks show CPU-only inference is 2–3x
            # faster and far more consistent. Power users with larger GPUs can
            # opt in without changing code via KEEP_GPU_LAYERS.
            if self.gpu_layers is not None:
                layers = self.gpu_layers
            else:
                try:
                    layers = int(os.getenv("KEEP_GPU_LAYERS", "0"))
                except ValueError:
                    layers = 0
            command.extend(["-ngl", str(max(0, layers))])
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                command,
                cwd=self.assets.server.parent,
                stdin=subprocess.DEVNULL,
                stdout=self._log_file,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags,
            )
        except OSError as exc:
            self._close_log()
            raise LocalRuntimeError(f"The local model runtime could not start: {exc}") from exc

    def has_exited(self) -> bool:
        return bool(self.process and self.process.poll() is not None)

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._close_log()

    def _close_log(self) -> None:
        if self._log_file:
            self._log_file.close()
            self._log_file = None
