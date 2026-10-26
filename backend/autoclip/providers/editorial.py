"""Deterministic title grounding and complete-sentence candidate construction."""

import re

STOP = {
    "il",
    "lo",
    "la",
    "le",
    "gli",
    "i",
    "un",
    "una",
    "uno",
    "di",
    "del",
    "della",
    "dei",
    "delle",
    "e",
    "o",
    "a",
    "in",
    "per",
    "che",
    "con",
    "su",
    "da",
    "nel",
    "non",
    "è",
}


def grounded_title(title: str, text: str) -> str:
    source = set(re.findall(r"\w+", text.casefold()))
    content = set(re.findall(r"\w+", title.casefold())) - STOP
    # Every content token must be present. Partial overlap accepted hallucinated
    # names and English framing in the former two-token check.
    if len(content) >= 2 and content <= source:
        return title.strip()
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentence = next(
        (s for s in sentences if len(s.split()) >= 6 and not s.endswith(("?", "…", "..."))),
        sentences[0],
    )
    tokens = sentence.split()
    return " ".join(tokens[:12]).rstrip(",;:") + ("…" if len(tokens) > 12 else "")


def sentence_pools(words, times, first_word, min_duration, max_duration):
    """Overlapping sentence-start candidates, never cut solely at a time limit.

    A partial window edge is excluded unless it is the source beginning.
    Missing punctuation yields fewer candidates rather than fabricated endings.
    """
    ends = [i for i, (_, text) in enumerate(words) if re.search(r'[.!?…]["”’]*$', text.strip())]
    starts = ([0] if first_word == 0 else []) + [i + 1 for i in ends if i + 1 < len(words)]
    pools = []
    for start in starts:
        for end in ends:
            if end <= start:
                continue
            duration = times[end][1] - times[start][0] if times else (end - start + 1) * 0.4
            if duration > max_duration:
                break
            if duration >= min_duration:
                pools.append(
                    (
                        int(words[start][0]),
                        int(words[end][0]),
                        " ".join(w.strip() for _, w in words[start : end + 1]),
                    )
                )
                break
    # Uniform thinning preserves coverage within the local context budget.
    if len(pools) > 12:
        pools = [pools[round(i * (len(pools) - 1) / 11)] for i in range(12)]
    return pools


def editorial_exclusion(text: str, start_s: float) -> str | None:
    """Narrow, disclosed intro guard; never alter model scores to manufacture spread."""
    greetings = re.findall(r"\b(?:welcome|benvenut[ioae])\b", text.casefold())
    if start_s < 30 and len(greetings) >= 2:
        return "Intro con saluti ripetuti nei primi 30 secondi; esclusa dalla selezione automatica."
    last = re.split(r"(?<=[.!])\s+", text.strip())[-1]
    if last.endswith("?") and re.search(
        r"\b(?:sai|sapete|indovina)\b", " ".join(last.split()[-9:]).casefold()
    ):
        return "Domanda introduttiva senza risposta nel segmento; richiede un confine più ampio."
    return None
