# syntax=docker/dockerfile:1
FROM node:24-slim@sha256:55fb5f5a527ea2c5c4a95f963e48ef90aa38c7b346054fdc8ee9957a2b55d205 AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS cpu
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 AUTOCLIP_HOME=/data HF_HOME=/data/huggingface CUDA_VISIBLE_DEVICES=-1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 fonts-liberation curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE requirements-cpu.lock.txt ./
COPY backend/ ./backend/
COPY scripts/bootstrap_models.py ./scripts/bootstrap_models.py
COPY docs/licenses/ ./docs/licenses/
COPY --from=frontend /build/backend/autoclip/static ./backend/autoclip/static
RUN pip install 'pip>=26.2.2' && pip install -r requirements-cpu.lock.txt && useradd -u 10001 -m clipforge && mkdir /data && chown clipforge:clipforge /data
USER clipforge
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1
CMD ["sh","-c","python scripts/bootstrap_models.py --cpu && exec autoclip serve --host 0.0.0.0 --port 8000 --no-open"]

FROM cpu AS gpu
USER root
RUN pip install nvidia-cublas-cu12==12.9.2.10 nvidia-cuda-nvrtc-cu12==12.9.86 nvidia-cudnn-cu12==9.27.0.42
ENV CUDA_VISIBLE_DEVICES=0
USER clipforge
CMD ["sh","-c","python scripts/bootstrap_models.py && exec autoclip serve --host 0.0.0.0 --port 8000 --no-open"]
