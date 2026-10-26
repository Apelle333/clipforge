"""Run only in .align-venv; no ASR or LLM rewrite is performed."""

import json
import sys
from pathlib import Path

from whisperx.alignment import align, load_align_model
from whisperx.audio import load_audio

audio, source, destination = map(Path, sys.argv[1:])
data = json.loads(source.read_text(encoding="utf-8"))
model, metadata = load_align_model(
    language_code=data["language"],
    device="cpu",
    model_name="jonatasgrosman/wav2vec2-large-xlsr-53-italian"
    if data["language"] == "it"
    else None,
    model_dir=str(Path(__file__).resolve().parents[2] / "data/alignment-models"),
)
segments = [{"text": s["text"], "start": s["start"], "end": s["end"]} for s in data["segments"]]
result = align(
    segments, model, metadata, load_audio(str(audio)), "cpu", return_char_alignments=False
)
destination.write_text(json.dumps(result["word_segments"], ensure_ascii=False), encoding="utf-8")
