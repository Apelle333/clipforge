import pytest
from autoclip.pipeline.transcript import Word


def test_readability_is_text_only_and_preserves_repeated_words_and_names():
    from autoclip.pipeline.readability import lexical_identity, readable_words

    words = [Word("no", 0, 0.3), Word("no", 0.3, 0.6), Word("Xyz’Luca?", 2, 3)]
    result = readable_words(words)
    assert [lexical_identity(w.text) for w in result] == [lexical_identity(w.text) for w in words]
    assert [(w.start, w.end) for w in result] == [(w.start, w.end) for w in words]
    assert words[0].text == "no"
    assert result[1].text == "no."


def test_title_rejects_partial_overlap_with_invented_reference():
    from autoclip.providers.editorial import grounded_title

    text = "La protesta continua. Non siamo d'accordo."
    assert grounded_title("Fiorello's TV Applause: la protesta", text) == "La protesta continua."
    assert grounded_title("La protesta continua", text) == "La protesta continua"
    assert grounded_title("The protest continues", text) == "La protesta continua."


def test_repeated_intro_guard_does_not_exclude_later_discussion():
    from autoclip.providers.editorial import editorial_exclusion

    assert editorial_exclusion("Welcome, welcome, welcome!", 1)
    assert editorial_exclusion("Welcome, welcome, welcome!", 200) is None
    assert editorial_exclusion("La protesta riguarda gli agricoltori.", 1) is None
    assert editorial_exclusion("Un fatto. Sai cos'era?", 200)
    assert editorial_exclusion("Sai cos'era? Era una protesta.", 200) is None


def test_ranking_revision_distinguishes_corrections_from_punctuation():
    from autoclip.pipeline.readability import transcript_revision

    assert transcript_revision([Word("Ciao", 0, 1)]) == transcript_revision([Word("ciao.", 0, 1)])
    assert transcript_revision([Word("Louvre", 0, 1)]) != transcript_revision(
        [Word("Londra", 0, 1)]
    )


def test_sentence_pools_skip_window_fragments_and_respect_duration():
    from autoclip.providers.editorial import sentence_pools

    words = [
        (str(i), t)
        for i, t in enumerate(
            ["frammento", "finisce.", "Una", "frase", "intera.", "Altra", "frase."]
        )
    ]
    times = [(i * 2, i * 2 + 1) for i in range(len(words))]
    pools = sentence_pools(words, times, 100, 3, 9)
    assert pools and all(first >= 2 for first, _, _ in pools)
    assert all(words[last][1].endswith(".") for _, last, _ in pools)
    assert all(times[last][1] - times[first][0] <= 9 for first, last, _ in pools)


@pytest.mark.parametrize("mode", ["manual", "fit"])
def test_manual_framing_is_static_bounded_and_shared(mode):
    from autoclip.pipeline.editor_options import EditorOptions
    from autoclip.pipeline.reframe.croppath import manual_crop

    path = manual_crop(1920, 1080, 30, "9:16", EditorOptions(framing=mode, manual_x=1))
    s = path.segments[0]
    assert s.is_static and s.fit == (mode == "fit")
    assert 0 <= s.keyframes[0].x <= 1920 - s.width
    assert s.end_s == 30


def test_manual_options_invalidate_crop_and_export_revision():
    from types import SimpleNamespace

    from autoclip.pipeline.editor_options import EditorOptions, crop_cache_key, render_fingerprint

    clip = SimpleNamespace(start_s=0, end_s=30)
    a, b = EditorOptions(), EditorOptions(framing="manual", manual_x=0.2)
    assert crop_cache_key(clip, "9:16", a) != crop_cache_key(clip, "9:16", b)
    assert render_fingerprint(clip, [], "boxed", "9:16", a) != render_fingerprint(
        clip, [], "boxed", "9:16", b
    )


@pytest.mark.asyncio
async def test_partial_candidate_rating_cannot_pass_silently(monkeypatch):
    from autoclip.providers.base import DetectionConfig, ProviderError, TranscriptWindow
    from autoclip.providers.ollama_provider import OllamaProvider

    provider = OllamaProvider("phi4-mini:latest")

    async def incomplete(*args):
        return (
            '{"clips":[{"candidate_id":0,"title":"Una frase","rubric":'
            '{"hook":10,"coherence":11,"entertainment":12,"context":13,"ending":14}}]}'
        )

    monkeypatch.setattr(provider, "_complete", incomplete)
    window = TranscriptWindow(
        "[0]Una [1]frase. [2]Altra [3]frase.", 0, 3, word_times=[(0, 1), (5, 6), (8, 9), (14, 15)]
    )
    with pytest.raises(ProviderError, match="two attempts"):
        await provider.detect_highlights(
            window, DetectionConfig(min_duration_s=2, max_duration_s=7)
        )


def test_production_selection_avoids_substantially_repeated_material():
    from autoclip.pipeline.highlights import build_clips
    from autoclip.pipeline.transcript import Transcript
    from autoclip.providers.base import ClipCandidate, DetectionConfig

    transcript = Transcript(words=[Word(f"parola{i}.", i, i + 0.8) for i in range(20)])
    candidates = [
        ClipCandidate(start_word_index=a, end_word_index=b, score=score)
        for a, b, score in [(0, 5, 80), (3, 8, 79), (10, 15, 78)]
    ]
    clips = build_clips(
        transcript,
        candidates,
        DetectionConfig(min_duration_s=3, max_duration_s=10, require_complete_sentences=True),
        job_id="overlap-test",
    )
    assert len(clips) == 2
    assert [c.score for c in clips] == [80, 78]
