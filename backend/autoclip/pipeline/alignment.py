"""Optional isolated WhisperX alignment. Text is immutable; bad alignment is rejected."""

from __future__ import annotations

import json
import logging
import math
import subprocess
import tempfile
from pathlib import Path

from .transcript import Transcript

log = logging.getLogger(__name__)


def apply_alignment(transcript: Transcript, aligned: list[dict]) -> bool:
    if len(aligned) != len(transcript.words):
        return False
    previous = 0.0
    proposed = []
    for word, item in zip(transcript.words, aligned, strict=True):
        if item.get("word", "").strip() != word.text.strip():
            return False
        start, end = item.get("start"), item.get("end")
        if start is None or end is None or not all(math.isfinite(t) for t in (start, end)):
            return False
        if not 0 <= start < end or start < previous or abs(start - word.start) > 2.0:
            return False
        proposed.append((start, end))
        previous = end
    for word, (start, end) in zip(transcript.words, proposed, strict=True):
        word.start, word.end = start, end
    return True


def align_transcript(audio: Path, transcript: Transcript) -> None:
    root = Path(__file__).resolve().parents[3]
    python = root / ".align-venv/Scripts/python.exe"
    worker = root / "scripts/align_worker.py"
    try:
        if not python.exists():
            raise RuntimeError("Isolated WhisperX environment is missing")
        with tempfile.TemporaryDirectory(prefix="clipforge-align-") as temp:
            source, output = Path(temp) / "input.json", Path(temp) / "output.json"
            transcript.save(source)
            result = subprocess.run(
                [str(python), str(worker), str(audio.resolve()), str(source), str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=3600,
            )
            if result.returncode:
                raise RuntimeError(result.stderr[-1500:])
            aligned = json.loads(output.read_text(encoding="utf-8"))
            if not apply_alignment(transcript, aligned):
                raise RuntimeError(
                    "Alignment failed text/timing validation; original word times retained"
                )
        transcript.metadata["alignment"] = "whisperx-it-validated"
    except Exception as exc:
        transcript.metadata["alignment"] = "fallback-whisper"
        transcript.metadata["alignment_warning"] = str(exc)
        log.warning("Forced alignment unavailable: %s", exc)
