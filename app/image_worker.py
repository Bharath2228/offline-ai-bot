"""Isolated inference on OpenVINO (Intel GPU, falling back to CPU). All model loading is strictly local."""
import json
import os
from pathlib import Path
import sys

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'


def report(**values):
    print(json.dumps(values), flush=True)


def generate(request, device, steps):
    import numpy as np
    from optimum.intel import OVStableDiffusionPipeline

    report(status=f'Loading Stable Diffusion 1.5 on {"this device’s GPU" if device == "GPU" else "CPU"}…')
    pipeline = OVStableDiffusionPipeline.from_pretrained(request['model'], local_files_only=True, device=device)
    pipeline.set_progress_bar_config(disable=True)

    def progress(pipe, step, timestep, callback_kwargs):
        shown = min(step + 1, steps)
        report(progress=int(shown * 100 / steps), status=f'Creating your image · step {shown} of {steps}')
        return callback_kwargs

    return pipeline(
        prompt=request['prompt'], negative_prompt='blurry, low quality, distorted',
        num_inference_steps=steps, guidance_scale=7.5, width=512, height=512,
        generator=np.random.RandomState(int(request.get('seed', 42))),
        callback_on_step_end=progress,
    )


def main():
    request = json.loads(sys.stdin.readline())
    steps = max(4, min(30, int(request.get('steps', 16))))

    result = None
    last_error = None
    for device in ('GPU', 'CPU'):
        try:
            result = generate(request, device, steps)
            break
        except Exception as exc:
            last_error = exc
            continue
    if result is None:
        raise RuntimeError('Could not generate on this device.') from last_error

    output = Path(request['output'])
    output.parent.mkdir(parents=True, exist_ok=True)
    result.images[0].save(output)
    report(output=str(output), status='Your image is ready. Generated entirely on this device.')


if __name__ == '__main__':
    main()
