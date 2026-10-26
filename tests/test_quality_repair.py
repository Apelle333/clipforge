import pytest
from autoclip.config import WhisperSettings
from autoclip.pipeline.transcript import Transcript, Word


def test_readability_suggestion_does_not_save_or_change_times(editor_client):
    client = editor_client
    before = client.get("/api/clips/clip/words").json()
    suggestion = client.post("/api/clips/clip/readability")
    assert suggestion.status_code == 200
    assert [(w["start"], w["end"]) for w in suggestion.json()] == [
        (w["start"], w["end"]) for w in before
    ]
    assert client.get("/api/clips/clip/words").json() == before


def test_manual_framing_path_matches_saved_options(editor_client, monkeypatch):
    client = editor_client
    saved = client.get("/api/clips/clip").json()
    options = {**saved["render_options"], "framing": "manual", "manual_x": 1}
    result = client.put("/api/clips/clip/render-options", json=options)
    assert result.status_code == 200
    assert result.json()["render_revision"] != saved["render_revision"]
    # This fixture has no media; static manual geometry needs only source dimensions.
    monkeypatch.setattr("autoclip.api.clips.Path.is_file", lambda self: True)
    response = client.get("/api/clips/clip/crop-path")
    assert response.status_code == 200
    path = response.json()
    assert path["segments"][0]["keyframes"][0]["x"] > 0
    assert not path["segments"][0]["fit"]


def test_legacy_candidate_comparison_is_explicit(editor_client):
    response = editor_client.get("/api/jobs/job/selection")
    assert response.status_code == 200
    assert response.json()["alternatives"] == []
    assert "Legacy" in response.json()["note"]


def test_ranking_becomes_stale_after_lexical_correction(editor_client):
    import json

    from autoclip import paths
    from autoclip.pipeline.corrections import load_transcript
    from autoclip.pipeline.readability import transcript_revision

    words = editor_client.get("/api/clips/clip/words").json()
    audit = {
        "status": "ok",
        "failures": [],
        "transcript_revision": transcript_revision(load_transcript("job").words),
    }
    (paths.job_work_dir("job") / "highlight-status.json").write_text(json.dumps(audit))
    words[0]["text"] = "Louvre"
    editor_client.patch("/api/clips/clip/captions", json={"words": words}).raise_for_status()
    assert editor_client.get("/api/jobs/job/quality-status").json()["status"].startswith("stale")


def test_quality_decoding_is_explicit_and_italian_override_is_preserved():
    from autoclip.pipeline.transcribe import decoding_options

    options = decoding_options(WhisperSettings(language="it"))
    assert options["language"] == "it"
    assert options["task"] == "transcribe"
    assert options["beam_size"] == 5
    assert options["temperature"] == 0.0
    assert options["condition_on_previous_text"] is False


def test_timestamp_normalization_keeps_repetitions_and_unknown_names():
    from autoclip.pipeline.transcribe import normalize_timestamps

    words = [Word("PippoXYZ,", -0.1, 0.3), Word("no", 0.25, 0.5), Word("no!", 0.5, 0.5)]
    normalize_timestamps(words, 1)
    assert [w.text for w in words] == ["PippoXYZ,", "no", "no!"]
    assert all(0 <= w.start < w.end <= 1 for w in words)
    assert all(a.end <= b.start for a, b in zip(words, words[1:], strict=False))


def test_local_scoring_cannot_default_to_fifty():
    from autoclip.providers.base import TranscriptWindow
    from autoclip.providers.ollama_provider import OllamaProvider

    provider = OllamaProvider("phi4-mini:latest")
    with pytest.raises(ValueError):
        provider._parse(
            '{"clips":[{"start_word_index":0,"end_word_index":3,"title":"test"}]}',
            TranscriptWindow("[0]una [1]prova [2]vera [3]oggi", 0, 3),
        )


def test_caption_groups_have_character_budget():
    from autoclip.pipeline.captions import group_words

    words = [Word("incomprensibilmente", i, i + 0.3) for i in range(8)]
    assert all(len(g.text) <= 32 for g in group_words(words, max_chars=32))


def test_alignment_never_changes_words():
    from autoclip.pipeline.alignment import apply_alignment

    t = Transcript(words=[Word("Louvre", 0, 1), Word("no", 1, 2), Word("no.", 2, 3)])
    assert not apply_alignment(t, [{"word": "Londra", "start": 0, "end": 1}])
    assert t.text == "Louvre no no."


def test_zero_length_tail_cannot_create_overlaps():
    from autoclip.pipeline.transcribe import normalize_timestamps

    words = [Word("a", 0, 0.9), Word("b", 1, 1), Word("c", 1, 1)]
    normalize_timestamps(words, 1)
    assert all(a.end <= b.start for a, b in zip(words, words[1:], strict=False))
    assert all(w.end > w.start for w in words)


def test_long_silence_is_not_filled_with_words():
    from autoclip.pipeline.transcribe import normalize_timestamps

    words = [Word("prima", 0, 0.5), Word("dopo", 30, 31)]
    normalize_timestamps(words, 31)
    assert words[1].start == 30
    assert len(words) == 2


@pytest.fixture
def editor_client(monkeypatch):
    from autoclip import db, paths
    from autoclip.app import create_app
    from autoclip.db import store
    from autoclip.db.models import Clip, Job, Source
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AUTOCLIP_NO_WORKER", "1")
    db.init()
    store.create_source(
        Source(
            id="source", type="upload", path="missing.mp4", duration_s=10, width=1920, height=1080
        )
    )
    store.create_job(
        Job(
            id="job",
            source_id="source",
            settings={"export": {"caption_style": "boxed", "ratio": "9:16"}},
        )
    )
    transcript = Transcript(words=[Word("Louis", 0, 1), Word("no", 1, 2), Word("no.", 2, 3)])
    transcript.save(paths.job_work_dir("job") / "transcript.json")
    store.replace_clips(
        "job", [Clip(id="clip", job_id="job", start_s=0, end_s=3, start_word=0, end_word=2)]
    )
    with TestClient(create_app()) as client:
        yield client


def test_manual_correction_survives_trim_and_job_transcript(editor_client):
    client = editor_client
    words = client.get("/api/clips/clip/words").json()
    words[0]["text"] = "Louis Vuitton"
    assert client.patch("/api/clips/clip/captions", json={"words": words}).status_code == 200
    assert client.get("/api/jobs/job/transcript").json()["words"][0]["text"] == "Louis Vuitton"
    assert client.patch("/api/clips/clip", json={"start_s": 0.2, "end_s": 2.8}).status_code == 200
    actual = client.get("/api/clips/clip/words").json()
    assert actual[0]["text"] == "Louis Vuitton" and actual[0]["start"] == 0
    assert len(actual) == 3


def test_caption_save_does_not_reset_job_preset(editor_client):
    client = editor_client
    assert client.get("/api/clips/clip").json()["caption_style"] == "boxed"
    words = client.get("/api/clips/clip/words").json()
    updated = client.patch("/api/clips/clip/captions", json={"words": words})
    assert updated.json()["caption_style"] == "boxed"


def test_manual_timestamp_changes_are_rejected(editor_client):
    words = editor_client.get("/api/clips/clip/words").json()
    words[0]["start"] = 0.4
    assert editor_client.patch("/api/clips/clip/captions", json={"words": words}).status_code == 422


def test_stale_revision_cannot_export_old_preset_or_text(editor_client):
    before = editor_client.get("/api/clips/clip").json()["render_revision"]
    editor_client.patch("/api/clips/clip/captions", json={"caption_style": "clean_lower"})
    response = editor_client.post("/api/clips/clip/export", json={"expected_revision": before})
    assert response.status_code == 409


def test_closeup_that_cannot_fit_safe_margin_uses_fit():
    from autoclip.pipeline.reframe import ReframeConfig, _track_segment
    from autoclip.pipeline.reframe.faces import FaceObservation
    from autoclip.pipeline.reframe.tracker import FaceTrack

    track = FaceTrack(
        id=1,
        observations=[
            FaceObservation(t=0, cx=900, cy=500, width=700, height=500, eye_y=400, mar=0.1)
        ],
    )
    result = _track_segment(
        track,
        start_s=0,
        end_s=1,
        source_w=1920,
        source_h=1080,
        crop_w=608,
        crop_h=1080,
        config=ReframeConfig(),
    )
    assert result.fit


def test_rubric_is_computed_instead_of_trusting_generic_total():
    from autoclip.providers.scoring import Rubric

    assert Rubric(hook=20, coherence=18, entertainment=14, context=16, ending=18).total() == 88
    assert Rubric(hook=0, coherence=18, entertainment=14, context=16, ending=18).total() == 58


def test_italian_apostrophe_spacing_does_not_rewrite_words():
    from autoclip.pipeline.captions import group_words

    words = [Word("l", 0, 0.1), Word("'hanno", 0.1, 0.3), Word("visto.", 0.3, 0.6)]
    assert group_words(words)[0].text == "l'hanno visto."
    assert words[1].start == 0.1 and words[1].text == "'hanno"


def test_manual_correction_is_used_by_reanalysis_without_overwriting_old_job(editor_client):
    words = editor_client.get("/api/clips/clip/words").json()
    words[0]["text"] = "Louis Vuitton"
    editor_client.patch("/api/clips/clip/captions", json={"words": words})
    response = editor_client.post("/api/jobs/job/reanalyze")
    assert response.status_code == 201
    new_id = response.json()["id"]
    assert new_id != "job"
    assert (
        editor_client.get(f"/api/jobs/{new_id}/transcript").json()["words"][0]["text"]
        == "Louis Vuitton"
    )
    assert editor_client.get("/api/clips/clip").status_code == 200


@pytest.mark.asyncio
async def test_same_job_cannot_run_concurrently(editor_client):
    from autoclip.db import store
    from autoclip.pipeline.runner import PipelineError, PipelineRunner
    from filelock import FileLock

    runner = PipelineRunner(store.get_job("job"), store.get_source("source"))
    with (
        FileLock(runner.workspace.root / "pipeline.lock"),
        pytest.raises(PipelineError, match="already being processed"),
    ):
        await runner.run()


@pytest.mark.slow
def test_real_model_does_not_invent_text_for_30_seconds_of_silence(tmp_path):
    import os
    import wave

    from autoclip.pipeline.transcribe import TranscriptionError, _transcribe_once

    model = os.environ.get("AUTOCLIP_QUALITY_ASR_MODEL")
    if not model:
        pytest.skip(
            "Set AUTOCLIP_QUALITY_ASR_MODEL to cached small weights for real silence regression"
        )
    audio = tmp_path / "silence.wav"
    with wave.open(str(audio), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\0\0" * 16000 * 30)
    with pytest.raises(TranscriptionError, match="No speech"):
        _transcribe_once(audio, WhisperSettings(model=model, language="it"), force_cpu=True)
