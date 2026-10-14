from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from lm_studio_client import ChatMessage, LMStudioClient


class FakeLMStudioHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    last_chat_request = None

    def log_message(self, format, *args):
        pass

    def _send_json(self, body: dict) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == "/v1/models":
            self._send_json({"object": "list", "data": [{"id": "qwen3-vl-4b-instruct"}]})
            return
        self.send_error(404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        type(self).last_chat_request = json.loads(self.rfile.read(length))
        body = (
            'data: {"choices":[{"delta":{"content":"Real "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"HTTP works"}}]}\n\n'
            "data: [DONE]\n\n"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()


class LocalHTTPIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeLMStudioHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_real_local_socket_model_and_streaming_round_trip(self):
        client = LMStudioClient(self.base_url)
        self.assertEqual(client.list_models(), ["qwen3-vl-4b-instruct"])
        answer = "".join(
            client.stream_chat(
                model="qwen3-vl-4b-instruct",
                messages=[ChatMessage("user", "Integration test")],
                temperature=0.3,
                max_tokens=256,
            )
        )
        self.assertEqual(answer, "Real HTTP works")
        self.assertEqual(FakeLMStudioHandler.last_chat_request["model"], "qwen3-vl-4b-instruct")
        self.assertEqual(
            FakeLMStudioHandler.last_chat_request["messages"],
            [{"role": "user", "content": "Integration test\n/no_think"}],
        )


if __name__ == "__main__":
    unittest.main()
