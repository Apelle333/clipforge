"""Persist bounded per-clip rendering options beside existing job artifacts."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

from .. import paths


class EditorOptions(BaseModel):
    framing: Literal["auto", "fit", "manual"] = "auto"
    manual_x: float = Field(default=0.5, ge=0, le=1)
    manual_y: float = Field(default=0.5, ge=0, le=1)
    size: float = Field(default=1.0, ge=0.6, le=1.4)
    max_width: float = Field(default=0.82, ge=0.55, le=0.9)
    bottom: float = Field(default=0.16, ge=0.12, le=0.3)
    subject_position: float = Field(default=0.5, ge=0.35, le=0.65)
    face_margin: float = Field(default=0.12, ge=0.05, le=0.25)


def load_options(job_id: str, clip_id: str) -> EditorOptions:
    path = paths.job_work_dir(job_id) / "edits" / f"{clip_id}.json"
    return EditorOptions.model_validate_json(path.read_text()) if path.exists() else EditorOptions()


def save_options(job_id: str, clip_id: str, options: EditorOptions) -> None:
    path = paths.job_work_dir(job_id) / "edits" / f"{clip_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(options.model_dump()), encoding="utf-8")
    temp.replace(path)


def render_fingerprint(clip, words, style: str, ratio: str, options: EditorOptions) -> str:
    data = {
        "start": clip.start_s,
        "end": clip.end_s,
        "style": style,
        "ratio": ratio,
        "words": [
            {
                "text": w.text,
                "start": round(float(w.start), 4),
                "end": round(float(w.end), 4),
                "speaker": w.speaker,
            }
            for w in words
        ],
        "options": options.model_dump(),
        "version": "phase02b-captions-v3",
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def crop_cache_key(clip, ratio: str, options: EditorOptions) -> str:
    base = f"{clip.start_s}:{clip.end_s}:{ratio}:{options.subject_position}:{options.face_margin}"
    # Existing automatic geometry remains valid; manual modes need distinct keys.
    value = (
        f"{base}:v3"
        if options.framing == "auto"
        else f"{base}:{options.framing}:{options.manual_x}:{options.manual_y}:v4"
    )
    return hashlib.sha256(value.encode()).hexdigest()[:12]
