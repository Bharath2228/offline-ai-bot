from __future__ import annotations

import base64
import json
import mimetypes
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Iterator
from urllib.parse import urlparse

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
SUPPORTED_IMAGES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024


class LMStudioError(RuntimeError):
    """An error that can be shown directly in the desktop interface."""


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    image_path: str | None = None


def normalize_local_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("LM Studio URL contains an invalid port.") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("LM Studio URL contains an invalid port.")
    if (
        parsed.scheme != "http"
        or parsed.hostname not in LOCAL_HOSTS
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("LM Studio URL must be a local HTTP address.")
    if parsed.path in ("", "/"):
        url += "/v1"
    elif parsed.path.rstrip("/") != "/v1":
        raise ValueError("LM Studio URL path must be /v1.")
    return url


@lru_cache(maxsize=2)
def _encode_image_bytes(path_value: str, size: int, modified_ns: int, mime_type: str) -> str:
    del size, modified_ns  # They form the cache key and invalidate changed files.
    encoded = base64.b64encode(Path(path_value).read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def encode_image(path_value: str) -> str:
    path = Path(path_value)
    if not path.is_file():
        raise LMStudioError("The attached image no longer exists.")
    metadata = path.stat()
    if metadata.st_size > MAX_IMAGE_BYTES:
        raise LMStudioError("The attached image is larger than 20 MB.")
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type not in SUPPORTED_IMAGES:
        raise LMStudioError("Please attach a JPEG, PNG, or WebP image.")
    return _encode_image_bytes(str(path.resolve()), metadata.st_size, metadata.st_mtime_ns, mime_type)


def serialize_messages(messages: list[ChatMessage]) -> list[dict]:
    serialized: list[dict] = []
    for message in messages:
        if message.role not in {"system", "user", "assistant"}:
            raise LMStudioError(f"Unsupported message role: {message.role}")
        if message.image_path:
            if message.role != "user":
                raise LMStudioError("Images can only be attached to user messages.")
            content: str | list[dict] = [
                {"type": "text", "text": message.content},
                {
                    "type": "image_url",
                    "image_url": {"url": encode_image(message.image_path)},
                },
            ]
        else:
            content = message.content
        serialized.append({"role": message.role, "content": content})
    return serialized


class LMStudioClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = normalize_local_url(base_url)
        self.transport = transport

    def _client(self, *, timeout: httpx.Timeout | float) -> httpx.Client:
        # Ignoring proxy environment variables guarantees localhost traffic never
        # gets routed through a configured corporate or system proxy.
        return httpx.Client(transport=self.transport, timeout=timeout, trust_env=False)

    def list_models(self) -> list[str]:
        try:
            with self._client(timeout=2) as client:
                response = client.get(f"{self.base_url}/models")
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LMStudioError(
                "LM Studio is not reachable. In LM Studio, open Developer and start the server."
            ) from exc

        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise LMStudioError("LM Studio returned an unexpected model list.")
        models = [
            item["id"]
            for item in body["data"]
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
        ]
        return list(dict.fromkeys(models))

    def stream_chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int,
        cancel_event: Event | None = None,
        thinking: bool = False,
    ) -> Iterator[str]:
        if not model.strip():
            raise LMStudioError("Select a model before sending a message.")

        serialized = serialize_messages(messages)
        # Qwen 3 reliably recognizes /no_think across llama.cpp versions. Keep
        # this transport-only so it never appears in the visible conversation.
        if not thinking and "qwen3" in model.casefold():
            for message in reversed(serialized):
                if message["role"] != "user":
                    continue
                if isinstance(message["content"], str):
                    if "/no_think" not in message["content"]:
                        message["content"] += "\n/no_think"
                elif isinstance(message["content"], list) and message["content"]:
                    text_part = message["content"][0]
                    if isinstance(text_part, dict) and "/no_think" not in text_part.get("text", ""):
                        text_part["text"] = text_part.get("text", "") + "\n/no_think"
                break
        payload = {
            "model": model,
            "messages": serialized,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": thinking},
        }
        timeout = httpx.Timeout(connect=8, read=None, write=30, pool=8)
        try:
            with self._client(timeout=timeout) as client:
                with client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload
                ) as response:
                    if response.status_code >= 400:
                        raw = response.read().decode("utf-8", errors="replace")
                        try:
                            body = json.loads(raw)
                            error = body.get("error")
                            detail = error.get("message") if isinstance(error, dict) else error
                        except (json.JSONDecodeError, AttributeError):
                            detail = raw
                        raise LMStudioError(
                            str(detail or f"LM Studio rejected the request ({response.status_code}).")
                        )

                    for line in response.iter_lines():
                        if cancel_event and cancel_event.is_set():
                            return
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line == "[DONE]":
                            return
                        try:
                            event = json.loads(line)
                            choices = event.get("choices", [])
                            delta = choices[0].get("delta", {}) if choices else {}
                            content = delta.get("content")
                        except (json.JSONDecodeError, AttributeError, IndexError, TypeError):
                            continue
                        if isinstance(content, str) and content:
                            yield content
        except LMStudioError:
            raise
        except httpx.ConnectError as exc:
            raise LMStudioError(
                "LM Studio is not reachable. In LM Studio, open Developer and start the server."
            ) from exc
        except httpx.TimeoutException as exc:
            raise LMStudioError("LM Studio took too long to respond.") from exc
        except httpx.HTTPError as exc:
            raise LMStudioError("The connection to LM Studio was interrupted.") from exc


def choose_preferred_model(models: list[str]) -> str | None:
    if not models:
        return None

    def score(model: str) -> tuple[int, float, int, int, int]:
        lowered = model.lower()
        sizes = __import__("re").findall(r"(?:^|[-_ ])(\d+(?:\.\d+)?)b(?:[-_ .]|$)", lowered)
        size = float(sizes[-1]) if sizes else 0.0
        useful = not any(word in lowered for word in ("embedding", "rerank"))
        text_model = not any(word in lowered for word in ("-vl", "vision"))
        return (int(useful), size, int(text_model), int("qwen" in lowered), int("gemma" in lowered))

    return max(models, key=score)
