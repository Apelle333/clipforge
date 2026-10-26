"""Conservative, reviewable typography; never infer or replace spoken vocabulary."""

import hashlib
import json
import re
from dataclasses import replace

from .transcript import Word


def lexical_identity(text: str) -> str:
    # Keep accents, digits and apostrophes: they can change spoken content.
    return "".join(c.casefold() for c in text if c.isalnum() or c in "'’")


def transcript_revision(words: list[Word]) -> str:
    return hashlib.sha256(
        json.dumps(
            [[lexical_identity(w.text), w.start, w.end] for w in words], ensure_ascii=False
        ).encode()
    ).hexdigest()


def readable_words(words: list[Word]) -> list[Word]:
    """Capitalize existing sentence starts; add stops only across long pauses.

    Pause-based punctuation is a suggestion, not an audio-verified correction.
    Existing punctuation, repetitions, spelling, timing and speaker are retained.
    """
    result = []
    for i, word in enumerate(words):
        text = word.text
        sentence_start = i == 0 or bool(re.search(r'[.!?…]["”’]*$', result[-1].text))
        if sentence_start:
            text = re.sub(r"[^\W\d_]", lambda m: m[0].upper(), text, count=1)
        if (
            i + 1 < len(words)
            and words[i + 1].start - word.end >= 1.2
            and not re.search(r"[.!?…,;:]$", text)
        ):
            text += "."
        if lexical_identity(text) != lexical_identity(word.text):
            raise ValueError("Readability formatting must preserve lexical content")
        result.append(replace(word, text=text))
    return result
