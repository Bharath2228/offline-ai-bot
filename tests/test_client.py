from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from threading import Event

import httpx

from lm_studio_client import (
    ChatMessage,
    LMStudioClient,
    LMStudioError,
    choose_preferred_model,
    encode_image,
    normalize_local_url,
    serialize_messages,
)


class ClientTests(unittest.TestCase):
    def test_local_urls_are_normalized(self):
        self.assertEqual(normalize_local_url("http://127.0.0.1:1234"), "http://127.0.0.1:1234/v1")
        self.assertEqual(normalize_local_url("http://localhost:1234/v1/"), "http://localhost:1234/v1")
        self.assertEqual(normalize_local_url("http://[::1]:1234/v1"), "http://[::1]:1234/v1")

    def test_non_local_and_malformed_urls_are_rejected(self):
        invalid = [
            "https://127.0.0.1:1234/v1",
            "http://example.com:1234/v1",
            "http://localhost:1234/api",
            "http://user:pass@localhost:1234/v1",
            "http://localhost:1234/v1?key=value",
            "http://localhost:notaport/v1",
            "http://localhost:0/v1",
            "not-a-url",
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_local_url(url)

    def test_list_models_filters_duplicates_and_invalid_entries(self):
        def handler(request):
            self.assertEqual(request.url.path, "/v1/models")
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "qwen3-vl-4b"},
                        {"id": "qwen3-vl-4b"},
                        {"id": ""},
                        "invalid",
                    ]
                },
            )

        client = LMStudioClient(transport=httpx.MockTransport(handler))
        self.assertEqual(client.list_models(), ["qwen3-vl-4b"])

    def test_model_connection_errors_are_friendly(self):
        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        client = LMStudioClient(transport=httpx.MockTransport(handler))
        with self.assertRaisesRegex(LMStudioError, "open Developer and start the server"):
            client.list_models()

    def test_invalid_model_response_is_rejected(self):
        client = LMStudioClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"unexpected": []}))
        )
        with self.assertRaisesRegex(LMStudioError, "unexpected model list"):
            client.list_models()

    def test_stream_chat_parses_sse_and_sends_expected_payload(self):
        captured = {}

        def handler(request):
            self.assertEqual(request.url.path, "/v1/chat/completions")
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                content=(
                    b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
                    b': keepalive\n\n'
                    b'data: malformed\n\n'
                    b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
                    b'data: [DONE]\n\n'
                ),
            )

        client = LMStudioClient(transport=httpx.MockTransport(handler))
        result = "".join(
            client.stream_chat(
                model="qwen3-vl-4b",
                messages=[ChatMessage("user", "Hello")],
                temperature=0.6,
                max_tokens=512,
            )
        )
        self.assertEqual(result, "Hello world")
        self.assertEqual(captured["model"], "qwen3-vl-4b")
        self.assertEqual(captured["temperature"], 0.6)
        self.assertEqual(captured["max_tokens"], 512)
        self.assertTrue(captured["stream"])
        self.assertEqual(captured["messages"], [{"role": "user", "content": "Hello\n/no_think"}])
        self.assertEqual(captured["chat_template_kwargs"], {"enable_thinking": False})

    def test_stream_chat_surfaces_lm_studio_error(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(400, json={"error": {"message": "Model is not loaded"}})
        )
        client = LMStudioClient(transport=transport)
        with self.assertRaisesRegex(LMStudioError, "Model is not loaded"):
            list(
                client.stream_chat(
                    model="qwen",
                    messages=[ChatMessage("user", "Hi")],
                    temperature=0.7,
                    max_tokens=128,
                )
            )

    def test_cancel_event_stops_stream(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=(
                    b'data: {"choices":[{"delta":{"content":"one"}}]}\n'
                    b'data: {"choices":[{"delta":{"content":"two"}}]}\n'
                ),
            )
        )
        client = LMStudioClient(transport=transport)
        cancel = Event()
        stream = client.stream_chat(
            model="qwen",
            messages=[ChatMessage("user", "Hi")],
            temperature=0.7,
            max_tokens=128,
            cancel_event=cancel,
        )
        self.assertEqual(next(stream), "one")
        cancel.set()
        self.assertEqual(list(stream), [])

    def test_image_is_encoded_for_vision_message(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "sample.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nmock")
            data_url = encode_image(str(image))
            self.assertTrue(data_url.startswith("data:image/png;base64,"))
            self.assertEqual(base64.b64decode(data_url.split(",", 1)[1]), image.read_bytes())
            message = serialize_messages([ChatMessage("user", "What is this?", str(image))])[0]
            self.assertEqual(message["content"][0], {"type": "text", "text": "What is this?"})
            self.assertEqual(message["content"][1]["type"], "image_url")

    def test_invalid_image_and_role_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            text_file = Path(directory) / "not-image.txt"
            text_file.write_text("hello", encoding="utf-8")
            with self.assertRaisesRegex(LMStudioError, "JPEG, PNG, or WebP"):
                encode_image(str(text_file))
        with self.assertRaisesRegex(LMStudioError, "Unsupported message role"):
            serialize_messages([ChatMessage("tool", "bad")])

    def test_stronger_text_model_is_preferred(self):
        models = ["gemma-4b", "qwen3-4b", "qwen3-vl-4b", "embedding-model"]
        self.assertEqual(choose_preferred_model(models), "qwen3-4b")
        self.assertEqual(choose_preferred_model(["qwen3-vl-4b", "qwen3-8b"]), "qwen3-8b")
        self.assertIsNone(choose_preferred_model([]))


if __name__ == "__main__":
    unittest.main()
