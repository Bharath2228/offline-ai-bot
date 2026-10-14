from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from local_runtime import LocalModelRuntime, RuntimeAssets, discover_runtime_assets


class RuntimeTests(unittest.TestCase):
    def make_tree(self, root: Path):
        model_dir = root / "models" / "community" / "Qwen3-VL-4B-Instruct-GGUF"
        backend_dir = root / "extensions" / "backends" / "llama.cpp-win-x86_64-vulkan-avx2-2.33.0"
        model_dir.mkdir(parents=True)
        backend_dir.mkdir(parents=True)
        model = model_dir / "Qwen3-VL-4B-Instruct-Q4_K_M.gguf"
        projector = model_dir / "mmproj-Qwen3-VL-4B-Instruct-F16.gguf"
        server = backend_dir / "llama-server.exe"
        for path in (model, projector, server):
            path.write_bytes(b"test")
        return server, model, projector

    def test_discovers_qwen_vision_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = self.make_tree(root)
            assets = discover_runtime_assets(root)
            self.assertIsNotNone(assets)
            self.assertEqual((assets.server, assets.model, assets.vision_projector), expected)

    def test_missing_assets_return_none(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(discover_runtime_assets(Path(directory)))

    def test_automatically_discovers_text_only_installations(self):
        for name in ("gemma-3-4b-it-Q4_K_M.gguf", "Qwen3-8B-Q4_K_M.gguf"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, old_model, projector = self.make_tree(root)
                old_model.unlink()
                projector.unlink()
                model = root / "models" / name
                model.write_bytes(b"test")
                assets = discover_runtime_assets(root)
                self.assertIsNotNone(assets)
                self.assertEqual(assets.model, model)
                self.assertIsNone(assets.vision_projector)

    def test_prefers_larger_text_model_over_smaller_vision_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tree(root)
            text_model = root / "models" / "Qwen3-8B-Q4_K_M.gguf"
            text_model.write_bytes(b"test")
            assets = discover_runtime_assets(root)
            self.assertEqual(assets.model, text_model)
            self.assertIsNone(assets.vision_projector)

    def test_rejects_missing_or_projector_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, projector = self.make_tree(root)
            self.assertIsNone(discover_runtime_assets(root, root / "missing.gguf"))
            self.assertIsNone(discover_runtime_assets(root, projector))

    def test_selects_text_model_without_vision_projector(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tree(root)
            text_model = root / "models" / "Gemma" / "gemma.gguf"
            text_model.parent.mkdir()
            text_model.write_bytes(b"test")
            assets = discover_runtime_assets(root, text_model)
            self.assertEqual(assets.model, text_model)
            self.assertIsNone(assets.vision_projector)

    def test_runtime_builds_local_only_process_and_stops_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server, model, projector = self.make_tree(root)
            assets = RuntimeAssets(server, model, projector)
            process = Mock()
            process.poll.return_value = None
            runtime = LocalModelRuntime(assets, port=4321, log_path=root / "runtime.log")
            with patch("local_runtime.subprocess.Popen", return_value=process) as popen:
                runtime.start()
                command = popen.call_args.args[0]
                self.assertIn("127.0.0.1", command)
                self.assertEqual(command[command.index("--port") + 1], "4321")
                self.assertEqual(command[command.index("--parallel") + 1], "1")
                self.assertEqual(command[command.index("-c") + 1], "8192")
                self.assertEqual(command[command.index("-m") + 1], str(model))
                self.assertEqual(command[command.index("--mmproj") + 1], str(projector))
                runtime.stop()
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=10)

    def test_invalid_runtime_port_is_rejected(self):
        with self.assertRaises(ValueError):
            LocalModelRuntime(port=0)


if __name__ == "__main__":
    unittest.main()
