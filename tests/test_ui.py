from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTextToSpeech import QTextToSpeech

from lm_studio_client import ChatMessage, LMStudioError
from main import APP_STYLE, ApiWorker, MainWindow


class FakeClient:
    def __init__(self, fail_models: bool = False) -> None:
        self.fail_models = fail_models
        self.requests = []

    def list_models(self):
        if self.fail_models:
            raise LMStudioError("LM Studio test failure")
        return ["text-model", "qwen3-vl-4b"]

    def stream_chat(self, **kwargs):
        self.requests.append(kwargs)
        yield "Hello"
        yield " from Qwen"


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(APP_STYLE)

    def wait_until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for the desktop UI")

    def test_models_load_and_qwen_vision_is_selected(self):
        window = MainWindow(FakeClient())
        window.show()
        self.wait_until(lambda: window.model_combo.currentData() == "qwen3-vl-4b")
        self.assertEqual(window.model_combo.currentData(), "qwen3-vl-4b")
        self.assertEqual(window.model_combo.currentText(), "Qwen 3 VL  ·  4B  ·  Local")
        self.assertTrue(window.windowTitle().startswith("Keep"))
        self.assertTrue(window.send_button.isEnabled())
        self.assertIn("Connected locally", window.status_label.text())
        suggestions = [
            button
            for button in window.findChildren(QPushButton)
            if button.objectName() == "suggestion"
        ]
        self.assertEqual(len(suggestions), 3)
        suggestions[0].click()
        self.assertEqual(
            window.composer.toPlainText(), "Explain a complex idea in simple terms."
        )
        window.close()

    def test_stream_worker_batches_tiny_tokens_for_smooth_rendering(self):
        class BurstClient:
            def stream_chat(self, **kwargs):
                yield from ("x" for _ in range(1000))

        chunks = []
        completed = []
        worker = ApiWorker(BurstClient(), "chat")
        worker.token_ready.connect(chunks.append)
        worker.response_ready.connect(completed.append)
        worker.start()
        self.wait_until(lambda: worker.isFinished())
        self.app.processEvents()
        self.assertEqual("".join(chunks), "x" * 1000)
        self.assertEqual(completed, ["x" * 1000])
        self.assertLessEqual(len(chunks), 11)
        worker.deleteLater()

    def test_full_text_chat_and_new_conversation(self):
        client = FakeClient()
        window = MainWindow(client)
        window.show()
        self.wait_until(lambda: window.model_combo.currentData() == "qwen3-vl-4b")
        window.composer.setPlainText("Say hello")
        window.send_message()
        self.wait_until(lambda: window.worker is None)

        self.assertEqual(window.messages, [
            ChatMessage("user", "Say hello", None),
            ChatMessage("assistant", "Hello from Qwen", None),
        ])
        self.assertEqual(client.requests[0]["model"], "qwen3-vl-4b")
        self.assertEqual(client.requests[0]["messages"][-1], ChatMessage("user", "Say hello", None))
        self.assertEqual(client.requests[0]["messages"][0].role, "system")
        self.assertFalse(client.requests[0]["thinking"])
        self.assertEqual(len(window.message_rows), 2)
        self.assertIn("Hello from Qwen", window.active_bubble.text_view.toPlainText())
        self.assertTrue(window.regenerate_button.isEnabled())
        request_count = len(client.requests)
        window.regenerate_button.click()
        self.wait_until(lambda: window.worker is None)
        self.assertEqual(len(client.requests), request_count + 1)
        self.assertEqual(len(window.messages), 2)

        window.new_chat()
        self.app.processEvents()
        self.assertEqual(window.messages, [])
        self.assertEqual(window.message_rows, [])
        self.assertTrue(window.welcome.isVisible())
        window.composer.setPlainText("Draft for another conversation")
        window.chat_list.setCurrentRow(0)
        self.app.processEvents()
        self.assertEqual(len(window.messages), 2)
        self.assertEqual(window.messages[0].content, "Say hello")
        window.chat_list.setCurrentRow(1)
        self.assertEqual(window.composer.toPlainText(), "Draft for another conversation")
        window.chat_search.setText("Say hello")
        self.assertFalse(window.chat_list.item(0).isHidden())
        self.assertTrue(window.chat_list.item(1).isHidden())
        window.close()

    def test_profiles_and_personal_instructions_reach_the_model(self):
        client = FakeClient()
        window = MainWindow(client)
        previous_profile = window.settings.value("profile", "Balanced")
        previous_temperature = window.settings.value("temperature", 0.7)
        window.show()
        try:
            self.wait_until(lambda: window.model_combo.currentData() == "qwen3-vl-4b")
            window.profile_combo.setCurrentText("Coding")
            window.custom_instructions = "Use Python 3."
            window.composer.setPlainText("Write a function")
            window.send_message()
            self.wait_until(lambda: window.worker is None)
            system = client.requests[0]["messages"][0]
            self.assertEqual(system.role, "system")
            self.assertIn("software engineer", system.content)
            self.assertIn("Use Python 3.", system.content)
        finally:
            window.settings.setValue("profile", previous_profile)
            window.settings.setValue("temperature", previous_temperature)
            window.close()

    def test_image_attachment_clear_and_chat_export(self):
        window = MainWindow(FakeClient())
        window.show()
        try:
            self.wait_until(lambda: window.model_combo.currentData() == "qwen3-vl-4b")
            with tempfile.TemporaryDirectory() as directory:
                image_path = Path(directory) / "sample.png"
                pixmap = QPixmap(12, 12)
                pixmap.fill(QColor("#6f998b"))
                self.assertTrue(pixmap.save(str(image_path)))
                with __import__('unittest').mock.patch(
                    'main.QFileDialog.getOpenFileName', return_value=(str(image_path), 'Images')
                ):
                    window.attach_image()
                self.assertEqual(window.pending_image, str(image_path))
                self.assertTrue(window.image_chip.isVisible())
                window.clear_pending_image()
                self.assertIsNone(window.pending_image)
                self.assertFalse(window.image_chip.isVisible())

                window.messages = [ChatMessage("user", "Hello"), ChatMessage("assistant", "Hi there")]
                window.sessions[window.session_index]["messages"] = window.messages
                window.sessions[window.session_index]["title"] = "Export check"
                output = Path(directory) / "conversation.md"
                with __import__('unittest').mock.patch(
                    'main.QFileDialog.getSaveFileName', return_value=(str(output), 'Markdown')
                ):
                    window.export_chat()
                exported = output.read_text(encoding="utf-8")
                self.assertIn("# Export check", exported)
                self.assertIn("## Keep\n\nHi there", exported)
        finally:
            window.close()

    def test_read_aloud_starts_and_stops_local_speech(self):
        class SpeechProbe:
            def __init__(self):
                self.current = QTextToSpeech.State.Ready
                self.spoken = []
                self.stopped = 0

            def state(self):
                return self.current

            def say(self, text):
                self.spoken.append(text)

            def stop(self):
                self.stopped += 1

        window = MainWindow(FakeClient())
        probe = SpeechProbe()
        window.speech = probe
        window.speak_text("Read this locally")
        self.assertEqual(probe.spoken, ["Read this locally"])
        probe.current = QTextToSpeech.State.Speaking
        window.speak_text("Stop")
        self.assertEqual(probe.stopped, 1)
        window.close()

    def test_voice_input_reports_missing_optional_setup(self):
        window = MainWindow(FakeClient())
        window.voice_root = __import__('pathlib').Path('missing-voice-runtime')
        with (
            __import__('unittest').mock.patch.object(window, '_voice_ready', return_value=False),
            __import__('unittest').mock.patch.object(window.settings, 'value', return_value=None),
            __import__('unittest').mock.patch('main.QMessageBox.information') as message,
        ):
            window.toggle_voice_input()
        message.assert_called_once()
        self.assertIsNone(window.voice_process)
        window.close()

    def test_model_failure_is_shown_without_enabling_send(self):
        window = MainWindow(FakeClient(fail_models=True))
        window.show()
        self.wait_until(lambda: "LM Studio test failure" in window.status_label.text())
        self.assertIn("LM Studio test failure", window.status_label.text())
        self.assertFalse(window.send_button.isEnabled())
        window.close()


if __name__ == "__main__":
    unittest.main()
