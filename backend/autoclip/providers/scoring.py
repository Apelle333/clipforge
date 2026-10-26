"""Required evidence and criterion scores for the production local provider."""

import re

from pydantic import BaseModel, Field

from .base import ClipCandidate, ClipCandidates, TranscriptWindow


class Rubric(BaseModel):
    hook: int = Field(ge=0, le=20)
    coherence: int = Field(ge=0, le=20)
    entertainment: int = Field(ge=0, le=20)
    context: int = Field(ge=0, le=20)
    ending: int = Field(ge=0, le=20)

    def total(self) -> int:
        return round(
            5
            * (
                self.hook * 0.30
                + self.coherence * 0.25
                + self.entertainment * 0.15
                + self.context * 0.15
                + self.ending * 0.15
            )
        )


class ScoredCandidate(BaseModel):
    start_word_index: int = Field(ge=0)
    end_word_index: int = Field(ge=0)
    title: str = Field(min_length=3, max_length=100)
    evidence: str = Field(min_length=4)
    rubric: Rubric


class ScoredCandidates(BaseModel):
    clips: list[ScoredCandidate]


class PoolRating(BaseModel):
    candidate_id: int = Field(ge=0)
    title: str = Field(min_length=3, max_length=100)
    rubric: Rubric


class PoolRatings(BaseModel):
    clips: list[PoolRating]


def parse_scored(payload: dict, window: TranscriptWindow) -> ClipCandidates:
    result = ScoredCandidates.model_validate(payload)
    tokens = {int(i): word.strip() for i, word in re.findall(r"\[(\d+)\]([^\[]+)", window.text)}

    def clean(value):
        return re.sub(r"[^\wà-ÿ]+", " ", value.lower()).strip()

    cleaned = []
    vectors = []
    for candidate in result.clips:
        first, last = candidate.start_word_index, candidate.end_word_index
        if not window.first_word <= first < last <= window.last_word:
            raise ValueError("AI scoring failed: indices outside the transcript window.")
        span = " ".join(tokens.get(i, "") for i in range(first, last + 1))
        if clean(candidate.evidence) not in clean(span):
            raise ValueError(
                "AI scoring failed: supporting quote is absent from the selected transcript."
            )
        title_tokens = set(clean(candidate.title).split()) - {
            "il",
            "lo",
            "la",
            "le",
            "gli",
            "di",
            "del",
            "dei",
            "della",
            "un",
            "una",
            "e",
            "a",
            "in",
            "per",
            "che",
            "the",
            "of",
            "and",
        }
        title = (
            candidate.title
            if len(title_tokens & set(clean(span).split())) >= min(2, len(title_tokens))
            else " ".join(span.split()[:8])
        )
        cleaned.append(
            ClipCandidate(
                start_word_index=first,
                end_word_index=last,
                title=title,
                hook=" ".join(span.split()[:10]),
                score=candidate.rubric.total(),
                reason=" ".join(span.split()[:35]) + ("…" if len(span.split()) > 35 else ""),
            )
        )
        vectors.append(tuple(candidate.rubric.model_dump().values()))
    if len(vectors) >= 3 and len(set(vectors)) == 1:
        raise ValueError(
            "AI scoring failed: identical undifferentiated rubric for every candidate; "
            "retry required."
        )
    return ClipCandidates(clips=cleaned)
