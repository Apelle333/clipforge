"""Ollama provider — the fully-local path.

Talks to Ollama's HTTP API directly rather than through its SDK, keeping the
dependency surface to httpx (already required elsewhere).

Clip quality tracks model quality closely here. A 3B model will return
syntactically valid JSON full of mediocre clips; the recommendation list below
reflects what actually produces usable selections.
"""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse

import httpx

from .base import DetectionConfig, LLMProvider, ProviderError, ProviderStatus, extract_json_object
from .scoring import PoolRatings, ScoredCandidates, parse_scored

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:11436"

#: Models with enough instruction-following to hold the JSON contract and enough
#: judgement to rank clips sensibly. Below roughly 7B, selection quality falls
#: off sharply even when the JSON stays valid.
RECOMMENDED_MODELS = [
    "llama3.1:8b",
    "qwen2.5:14b",
    "mistral-nemo:12b",
    "gemma2:9b",
]

#: Highlight detection over an 8-minute window is slow on consumer hardware.
_REQUEST_TIMEOUT = httpx.Timeout(600.0, connect=5.0)


class OllamaProvider(LLMProvider):
    name = "ollama"
    requires_key = False

    def __init__(self, model: str = "", *, api_key: str | None = None, base_url: str | None = None):
        super().__init__(model, api_key=api_key, base_url=base_url or DEFAULT_BASE_URL)
        self.responses = []
        self.pool_count = 0
        self.editorial_audit = []
        endpoint = urlparse(self.base_url or DEFAULT_BASE_URL)
        if endpoint.scheme != "http" or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ProviderError("Ollama must use an HTTP loopback endpoint.", provider=self.name)

    @property
    def url(self) -> str:
        return (self.base_url or DEFAULT_BASE_URL).rstrip("/")

    async def _complete(self, system: str, user: str, config: DetectionConfig) -> str:
        if not self.model:
            raise ProviderError(
                "No Ollama model is selected.",
                provider=self.name,
                hint=f"Pull one first, e.g. `ollama pull {RECOMMENDED_MODELS[0]}`.",
            )

        schema = (
            PoolRatings.model_json_schema()
            if self.pool_count
            else ScoredCandidates.model_json_schema()
        )
        match = re.search(r"Transcript section, words (\d+) to (\d+)", user)
        if match and not self.pool_count:
            first, last = map(int, match.groups())
            properties = schema["$defs"]["ScoredCandidate"]["properties"]
            for key in ("start_word_index", "end_word_index"):
                properties[key].update(minimum=first, maximum=last)
        if self.pool_count:
            schema["$defs"]["PoolRating"]["properties"]["candidate_id"]["maximum"] = (
                self.pool_count - 1
            )
        schema["required"] = ["clips"]
        # Small local models copy the illustrative indices in the generic
        # prompt. The grammar already supplies the shape; omit that example.
        system = (
            "You are an evidence-based video editor. Select complete, self-contained moments. "
            "Use ONLY the supplied transcript. Return the specified JSON schema. "
            "For each candidate provide a short title in the transcript language, an exact "
            "evidence quote from INSIDE that candidate, and five independent scores from 0 to 20: "
            "hook (attention in the first sentence), coherence (one clear thought), "
            "entertainment (surprise, humor or useful insight), context (understandable alone), "
            "ending (complete payoff, no truncated thought). "
            "0 is unusable, 10 ordinary, 20 exceptional. "
            "Do not assign generic identical scores. Never invent words or positions. "
            "When candidates are supplied, RATE EVERY candidate_id exactly once, "
            "including weak ones. "
            "Do not create spans or quotes in candidate-ID mode. "
            f"Source language: {config.language or 'detect from transcript'}. "
            "Do not translate. Greetings, filler, introductions and missing context score poorly. "
            "Rate ALL supplied candidate IDs; the application selects final clips afterward."
        )
        payload = {
            "model": self.model,
            "system": system,
            "prompt": user,
            "stream": False,
            # Ollama's JSON mode constrains decoding to valid JSON, which is the
            # single biggest reliability win for small local models.
            "format": schema,
            "keep_alive": 0,
            "options": {
                "temperature": config.temperature,
                "num_ctx": 8192,
                "num_predict": 4096 if self.pool_count else 2048,
            },
        }
        if "qwen3" in self.model.lower():
            payload["think"] = False
        if os.environ.get("CLIPFORGE_CPU") == "1":
            payload["options"]["num_gpu"] = 0

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT, trust_env=False) as client:
                response = await client.post(f"{self.url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                self.responses.append(
                    {
                        key: data.get(key)
                        for key in ("response", "done_reason", "eval_count", "total_duration")
                    }
                )
                import json
                from uuid import uuid4

                from .. import paths

                audit = paths.root() / "diagnostics"
                audit.mkdir(parents=True, exist_ok=True)
                (audit / f"ollama-{uuid4().hex}.json").write_text(
                    json.dumps(
                        {
                            "model": self.model,
                            "response": data.get("response", ""),
                            "done_reason": data.get("done_reason"),
                            "eval_count": data.get("eval_count"),
                            "window": match.group(0) if match else None,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"Could not reach Ollama at {self.url}.",
                provider=self.name,
                hint="Start it with `ollama serve`, or install it from ollama.com.",
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "Ollama timed out.",
                provider=self.name,
                hint=(
                    "Large transcripts on a small GPU can exceed the limit. Try a smaller "
                    "model or retry after checking Ollama's local server log. "
                    "Use Launch-CLIPFORGE.ps1 to start the dedicated local Ollama server."
                ),
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _translate_status(exc, self.name, self.model) from exc

        return data.get("response", "")

    def _parse(self, raw, window):
        return parse_scored(extract_json_object(raw), window)

    async def detect_highlights(self, window, config):
        from .base import ClipCandidate, ClipCandidates

        words = re.findall(r"\[(\d+)\]([^\[]+)", window.text)
        from .editorial import grounded_title, sentence_pools

        pools = sentence_pools(
            words,
            window.word_times,
            window.first_word,
            config.min_duration_s,
            config.max_duration_s,
        )
        if not pools:
            return ClipCandidates(clips=[])
        self.pool_count = len(pools)
        user = (
            f"Transcript section, words {window.first_word} to {window.last_word}.\n"
            f"Language: {config.language}. Rate ALL supplied candidates (maximum 12).\n"
        )
        user += "\n".join(f"CANDIDATE {i}: {text}" for i, (_, _, text) in enumerate(pools))
        try:
            for _attempt in range(2):
                raw = await self._complete("", user, config)
                try:
                    ratings = PoolRatings.model_validate(extract_json_object(raw))
                    if {c.candidate_id for c in ratings.clips} != set(range(len(pools))):
                        raise ValueError("Rate every supplied candidate ID exactly once")
                    vectors = [tuple(c.rubric.model_dump().values()) for c in ratings.clips]
                    if len(vectors) >= 3 and len(set(vectors)) == 1:
                        raise ValueError("Every candidate received the same generic rubric")
                    results = []
                    seen = set()
                    for rating in ratings.clips:
                        if rating.candidate_id >= len(pools) or rating.candidate_id in seen:
                            raise ValueError("Invalid or duplicate candidate ID")
                        seen.add(rating.candidate_id)
                        first, last, text = pools[rating.candidate_id]
                        title = grounded_title(rating.title, text)
                        results.append(
                            ClipCandidate(
                                start_word_index=first,
                                end_word_index=last,
                                title=title,
                                score=rating.rubric.total(),
                                hook=" ".join(text.split()[:10]),
                                reason=(
                                    "Valutazione soggettiva del modello (criteri su 20): "
                                    f"aggancio {rating.rubric.hook}, "
                                    f"coerenza {rating.rubric.coherence}, "
                                    f"interesse {rating.rubric.entertainment}, "
                                    f"contesto {rating.rubric.context}, "
                                    f"conclusione {rating.rubric.ending}. "
                                    "Il punteggio non misura oggettivamente la qualità."
                                ),
                            )
                        )
                    self.editorial_audit.append(
                        {
                            "window": [window.first_word, window.last_word],
                            "candidates": [
                                {"id": i, "start_word": first, "end_word": last, "text": text}
                                for i, (first, last, text) in enumerate(pools)
                            ],
                            "ratings": [c.model_dump() for c in ratings.clips],
                            "note": "Subjective model ratings; omitted candidates were not rated.",
                        }
                    )
                    return ClipCandidates(clips=results)
                except (ValueError, IndexError) as exc:
                    user += (
                        f"\nInvalid scoring: {exc}. "
                        "Return distinct evidence-based rubric scores and valid IDs."
                    )
            raise ProviderError(
                "AI scoring failed after two attempts. See local diagnostics.", provider=self.name
            )
        finally:
            self.pool_count = 0

    async def health_check(self) -> ProviderStatus:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0), trust_env=False) as client:
                response = await client.get(f"{self.url}/api/tags")
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError:
            return ProviderStatus(
                name=self.name,
                available=False,
                detail=f"Not running at {self.url}",
            )
        except Exception as exc:
            return ProviderStatus(name=self.name, available=False, detail=str(exc)[:200])

        models = [m.get("name", "") for m in data.get("models", [])]
        models = [m for m in models if m]

        if not models:
            return ProviderStatus(
                name=self.name,
                available=False,
                detail=f"Running, but no models pulled. Try `ollama pull {RECOMMENDED_MODELS[0]}`.",
                models=[],
            )

        return ProviderStatus(
            name=self.name, available=True, detail=f"{len(models)} model(s)", models=sorted(models)
        )


def _translate_status(exc: httpx.HTTPStatusError, provider: str, model: str) -> ProviderError:
    if exc.response.status_code == 404:
        return ProviderError(
            f"Ollama has no model named '{model}'.",
            provider=provider,
            hint=f"Pull it with `ollama pull {model}`, or pick one you already have.",
        )
    return ProviderError(f"Ollama returned HTTP {exc.response.status_code}.", provider=provider)
