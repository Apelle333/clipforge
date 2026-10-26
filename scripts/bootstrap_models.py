"""Preserve existing settings; download public models only on request."""

import argparse

from autoclip import config, models, paths

parser = argparse.ArgumentParser()
parser.add_argument("--cpu", action="store_true")
parser.add_argument("--download-models", action="store_true")
args = parser.parse_args()
paths.ensure_layout()
settings = config.load()
if not (paths.root() / "config.json").exists():
    settings.active_provider = "ollama"
    settings.provider("ollama").model = "phi4-mini:latest"
    settings.provider("ollama").base_url = "http://127.0.0.1:11436"
    settings.whisper.model = "small"
    if args.cpu:
        settings.whisper.compute_type = "int8"
        settings.export.prefer_hardware_encoder = False
    config.save(settings)
if args.download_models:
    from huggingface_hub import snapshot_download

    snapshot_download(
        "Systran/faster-whisper-small",
        revision="536b0662742c02347bc0e980a01041f333bce120",
        allow_patterns=["*.json", "*.bin", "*.txt"],
        cache_dir=str(paths.root() / "huggingface"),
    )
    models.ensure("face_landmarker")
print("Local setup ready. Existing configuration preserved; no media uploaded.")
