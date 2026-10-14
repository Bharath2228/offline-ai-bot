# Keep

A polished native Windows AI application for the models already installed in LM Studio. Keep uses a calm, focus-friendly interface, connects only to the local API at `127.0.0.1:1234`, streams responses, and supports image prompts for vision-language models such as Qwen 3 VL.

## Layout

- `app/` — the application source (`main.py` and everything it imports).
- `scripts/` — one-time setup scripts you run yourself (`start.ps1`, `setup-image.ps1`, `setup-voice.ps1`).
- `packaging/` — builds and installs the desktop executable (`build.ps1`, `install.ps1`, `Keep.spec`).
- `tests/` — the automated test suite plus opt-in live/manual checks.
- `Keep.cmd` / `Install Keep.cmd` — double-click entry points at the project root; they just call into `scripts/` and `packaging/`.

## Start it

For installation, run **Install Keep.cmd**. This installs the bundled executable for your Windows account and creates desktop and Start menu shortcuts. The chat interface includes its own Python runtime. The optional Image studio uses the separate image environment described below. Remove the application through Windows Installed apps; downloaded models are kept.

Use **Model library → Installed** to choose from downloaded GGUF models. When Keep started the inference engine, it can load a different model directly. When connected to an existing LM Studio server, choose a model from the top menu or load it in LM Studio and press Retry.

Conversations are kept in the sidebar for the current session. Search finds titles and message content; switching chats preserves unsent drafts. Copy takes the original response text, and Export chat saves Markdown wherever you choose. Ctrl+N starts a conversation; Ctrl+Enter sends a message.

For stronger answers, Keep prefers the largest installed text model instead of a smaller vision model. The response selector offers **Balanced**, **Precise**, **Creative**, and **Coding** modes. Settings also supports personal instructions. **Regenerate** retries the latest response. Assistant messages can be read aloud using Windows' installed offline voices.

Use **Speak** beside the prompt to dictate. Click it once to begin recording and click **Stop** when finished; the local multilingual Whisper model inserts the transcript into the prompt for review before anything is sent to the LLM. The microphone is never opened automatically. One-time setup: `powershell -ExecutionPolicy Bypass -File scripts\setup-voice.ps1`.

Double-click **Keep.cmd** to run the source version. The app first connects to LM Studio's local server when it is available. If it is stopped, Keep discovers an installed GGUF model and starts LM Studio's bundled local inference engine itself. It prefers the strongest text model—currently Qwen 3 8B—while Qwen 3 VL remains available for image questions. The chosen model must be supported by your installed runtime.

## Qwen and Gemma

Download a GGUF instruction/chat model using **Model library → Discover & download** or LM Studio while online, then choose it under **Installed**. Model downloads and initial dependency setup require internet; chatting with a downloaded model does not. Text models support text conversations; image attachments require a compatible vision model and its matching projector. When changing the source later, rebuild and reinstall to update the desktop executable.

You can also start it from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

The first run installs the desktop UI libraries into this folder's private `.venv`. It does not modify the global Python installation. Once this setup has completed, normal launches do not need internet access.

## Using vision

Select **＋ Image** beside the chat box, choose a JPEG, PNG, or WebP file, type a question about it, and send. The image is converted in memory and sent only to the local model on your computer. This is distinct from **Image studio**, which generates new pictures.

## Offline guarantees

- The application rejects non-local server addresses.
- Chat and image generation use local models, need no API key, and do not send prompts online. Model-library searches and downloads explicitly contact Hugging Face; downloaded models then work offline.
- Conversation content stays in application memory until you close the app. Exported conversations remain in the file you select.
- The app uses LM Studio's OpenAI-compatible local endpoints: `/v1/models` and `/v1/chat/completions`.
- A model process started by the app is bound to `127.0.0.1` and is stopped when the app closes.

## Troubleshooting

- **LM Studio is not reachable:** Wait for the app to start an installed model automatically. The first model load can take up to a minute.
- **No models found:** Load a model in LM Studio, then press **Retry**.
- **Vision prompt fails:** Confirm the selected model is a vision-language model and the image is JPEG, PNG, or WebP.
- **A different local port:** Set `LM_STUDIO_URL` before launching, for example `http://127.0.0.1:1235/v1`. Non-local hosts are intentionally blocked.
- **Local model does not start:** Read `keep-runtime.log` in this folder for the inference engine's diagnostic output.
- **The first answer is slow:** Qwen 3 8B may take up to a minute for the first prompt while its cache warms. Follow-up answers are substantially faster on this machine.
- **Advanced GPU tuning:** Keep defaults to CPU inference because direct tests on this computer's 2 GB Arc GPU were 2–3× faster than partial GPU offload. On a machine with a larger dedicated GPU, set `KEEP_GPU_LAYERS` to a positive layer count before starting Keep.
- **Voice input is unavailable:** Run `scripts\setup-voice.ps1`, keep this project folder in place, and allow microphone access in Windows privacy settings.

## Model library and Image studio

Open **Model library → Discover & download** to search public GGUF models on Hugging Face. Select a repository, choose a file (sizes are displayed), and download it. Completed downloads are verified and appear under **Installed**, where you can load them. Gated models and split GGUF files are not supported by this browser. Vision models need a matching `mmproj` file, downloadable separately from the same repository. Review each model's license and runtime requirements before use.

**Image studio** opens the local Stable Diffusion 1.5 image workspace, pre-converted to OpenVINO IR (int8 weights) for inference on this device's Intel GPU, falling back to CPU automatically if GPU inference fails. It is a separate diffusion model, not a chat LLM. Its model files occupy about 1 GB; OpenVINO adds a GPU kernel cache (~1.8 GB) under `unet/model_cache` the first time it runs on GPU, which speeds up later generations and can be deleted to reclaim space (it's rebuilt automatically). It creates 512×512 images with progress, cancellation, a preview and Save. Generation may take a while on CPU, faster on GPU. Outputs are saved under `generated-images` in the image runtime folder.

The image runtime lives in this project's `.image-venv`, and weights in `image-models/stable-diffusion-v1-5`. The installer records this folder for the desktop app; keep it in place, or use **Choose image runtime folder** after moving it. Offline inference uses `local_files_only=True` and disables Hub access. One-time full setup: `powershell -ExecutionPolicy Bypass -File scripts\setup-image.ps1`. Stable Diffusion 1.5's [model card and license](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5) describe its limitations and usage terms (the [OpenVINO conversion](https://huggingface.co/OpenVINO/stable-diffusion-v1-5-int8-ov) carries the same license).

## Run the tests

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

For the native Windows process-cancellation test, set `$env:QT_QPA_PLATFORM='windows'` before running the suite. The offscreen test mode skips that OS-specific test. Opt-in live checks are available in `tests/live_quality.py` (five response-quality checks), `tests/live_voice.py` (offline speech recognition), `tests/live_library.py` (downloads a 105 MB QA model and runs it), and `tests/live_image_studio.py` (generates a real image with the installed Stable Diffusion weights).
