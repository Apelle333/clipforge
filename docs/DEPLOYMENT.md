# Deployment status

Windows local installation is the tested priority. Compose files are provided
for CPU and optional NVIDIA operation; configuration validation is separate
from a successful image build or inference test. See RELEASE-AUDIT.md for what
was actually run. No container image is published by this release.

## CPU Compose

Requires Docker Desktop with Linux containers/WSL2, or Docker Engine on Linux,
Compose v2, several GB of disk space and internet for dependencies/models.
From the repository root:

```sh
docker compose up --build -d
docker compose exec ollama ollama pull phi4-mini
docker compose exec clipforge python scripts/bootstrap_models.py --cpu --download-models
```

Open http://127.0.0.1:8078. Upload media through the editor. Both service data
and model weights use named volumes. `docker compose down` preserves them;
`down -v` deletes them. Back up both volumes before upgrades. CPU transcription,
ranking and rendering can be substantially slower than GPU operation; no CPU
speed guarantee is made.

Ollama shares the app's network namespace, so its API remains loopback-only
without weakening the provider's loopback restriction. It has no published port.

## Optional NVIDIA

Requires a supported NVIDIA driver, Docker GPU support (NVIDIA Container Toolkit
on Linux or working GPU integration in Docker Desktop/WSL2), Compose supporting
`gpus`, and sufficient VRAM. Verify host GPU container access independently.

```sh
docker compose -f compose.yaml -f compose.gpu.yaml up --build -d
docker compose exec ollama ollama pull phi4-mini
```

Use the same two `-f` arguments with subsequent commands when necessary. GPU
deployment has not been runtime-tested here. Models are loaded sequentially,
but a larger model may still exceed VRAM. CPU fallback is available.

## Public internet deployment is not supported by default

This is an unauthenticated local application. Keep the host port on 127.0.0.1.
Do not expose Ollama. A GPU video processor is a persistent Python/FFmpeg/model
service; it cannot run as a static Vercel website.

Before any public deployment, provide authentication and authorization, HTTPS
at a maintained reverse proxy, explicit trusted hosts/origins, upload/body and
request-rate limits, job concurrency/resource quotas, isolated tenant storage,
retention/deletion policy, backups and monitoring. The alpha has no tenant
isolation or production rate limiter. Upload size checks are defense in depth,
not a replacement for proxy/transport limits. Only process media you trust and
have rights to use. Publishing source code does not authorize public hosting.
