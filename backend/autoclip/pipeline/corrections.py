"""Text-only job corrections, shared by ranking, trim, captions and export."""

import json

from .. import paths
from .transcript import Transcript


def load_transcript(job_id: str) -> Transcript:
    root = paths.job_work_dir(job_id)
    transcript = Transcript.load(root / "transcript.json")
    from ..db import store

    by_time = {(round(w.start, 4), round(w.end, 4)): w for w in transcript.words}
    for clip in store.list_clips(job_id):
        edit = store.get_clip_edit(clip.id)
        for word in edit.edited_words if edit and edit.edited_words else []:
            original = by_time.get((round(word["start"], 4), round(word["end"], 4)))
            if original:
                original.text = word["text"]
    edits = root / "transcript-corrections.json"
    if edits.exists():
        for index, text in json.loads(edits.read_text(encoding="utf-8")).items():
            if 0 <= int(index) < len(transcript.words):
                transcript.words[int(index)].text = text
        for segment in transcript.segments:
            segment.text = transcript.text_between(segment.first_word, segment.last_word)
    return transcript


def save_corrections(job_id: str, words: list[dict]) -> None:
    transcript = load_transcript(job_id)
    by_time = {(round(w.start, 4), round(w.end, 4)): i for i, w in enumerate(transcript.words)}
    path = paths.job_work_dir(job_id) / "transcript-corrections.json"
    edits = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for word in words:
        key = (round(word["start"], 4), round(word["end"], 4))
        if key not in by_time or not word["text"].strip():
            raise ValueError("Corrections may change text only; keep measured word timestamps.")
        edits[str(by_time[key])] = word["text"].strip()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(edits, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
