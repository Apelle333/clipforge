import httpx
import pytest
from autoclip.config import Settings
from autoclip.providers import build_provider
from autoclip.providers.base import DetectionConfig, ProviderError
from autoclip.providers.ollama_provider import OllamaProvider


def test_default_is_local():
    assert Settings().active_provider == "ollama"


def test_cloud_provider_is_blocked():
    with pytest.raises(ProviderError, match="local-only"):
        build_provider("openai", Settings())


def test_remote_ollama_is_blocked():
    with pytest.raises(ProviderError, match="loopback"):
        OllamaProvider("phi4-mini:latest", base_url="https://example.com")


@pytest.mark.asyncio
async def test_ollama_releases_gpu_and_bounds_generation(monkeypatch):
    seen = {}

    class Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json):
            seen["payload"] = json
            return httpx.Response(
                200, json={"response": '{"clips":[]}'}, request=httpx.Request("POST", url)
            )

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    await OllamaProvider("phi4-mini:latest")._complete(
        "instructions\n## Output\nexample 1042",
        "Transcript section, words 10 to 50.",
        DetectionConfig(),
    )
    assert seen["trust_env"] is False
    assert seen["payload"]["keep_alive"] == 0
    assert seen["payload"]["options"]["num_predict"] <= 2048
    assert seen["payload"]["options"]["num_ctx"] <= 8192
    assert (
        seen["payload"]["format"]["$defs"]["ScoredCandidate"]["properties"]["end_word_index"][
            "maximum"
        ]
        == 50
    )
    assert "1042" not in seen["payload"]["system"]


def test_cuda_failure_retries_on_cpu(monkeypatch, tmp_path):
    from autoclip.pipeline import transcribe
    from autoclip.pipeline.transcript import Transcript, Word

    calls = []
    expected = Transcript(words=[Word("hello", 0, 1)])

    def attempt(*args, force_cpu=False, **kwargs):
        calls.append(force_cpu)
        if not force_cpu:
            raise RuntimeError("CUDA out of memory")
        return expected

    monkeypatch.setattr(transcribe, "_transcribe_once", attempt, raising=False)
    assert transcribe.transcribe(tmp_path / "audio.wav") is expected
    assert calls == [False, True]


def test_runner_uses_saved_job_settings(tmp_path):
    from autoclip.db.models import Job, Source
    from autoclip.pipeline.runner import PipelineRunner

    saved = Settings()
    saved.clips.max_clips = 3
    job = Job(id="test", source_id="source", settings=saved.model_dump())
    source = Source(id="source", type="file", path=str(tmp_path / "a.mp4"))
    assert PipelineRunner(job, source).settings.clips.max_clips == 3


def test_audio_decoder_accepts_local_wav(tmp_path):
    import wave

    from faster_whisper.audio import decode_audio

    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 16000)
    assert len(decode_audio(str(audio))) == 16000


def test_cancelled_transcription_unloads_model(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import faster_whisper
    from autoclip.pipeline import transcribe

    released = []

    class Model:
        def __init__(self, *args, **kwargs):
            self.model = SimpleNamespace(unload_model=lambda: released.append(True))

        def transcribe(self, *args, **kwargs):
            return iter([object()]), SimpleNamespace(duration=1, language="en")

    monkeypatch.setattr(faster_whisper, "WhisperModel", Model)
    with pytest.raises(transcribe.TranscriptionError, match="cancelled"):
        transcribe._transcribe_once(tmp_path / "audio.wav", force_cpu=True, cancelled=lambda: True)
    assert released == [True]


def test_queued_cancel_flag_can_be_cleared_for_retry():
    from autoclip import db
    from autoclip.db import store
    from autoclip.db.models import Job, Source
    from autoclip.jobs.queue import JobQueue

    db.init()
    store.create_source(Source(id="source", type="upload", path="test.mp4"))
    store.create_job(Job(id="cancel-job", source_id="source"))
    queue = JobQueue()
    assert queue.cancel("cancel-job")
    queue.clear_cancel("cancel-job")
    assert not queue.is_cancelled("cancel-job")


@pytest.mark.asyncio
async def test_inference_failure_during_cancel_marks_job_cancelled(monkeypatch):
    from autoclip import db
    from autoclip.db import store
    from autoclip.db.models import Job, Source
    from autoclip.pipeline.runner import JobCancelled, PipelineRunner

    db.init()
    source = store.create_source(Source(id="source", type="upload", path="test.mp4"))
    job = store.create_job(Job(id="cancel-job", source_id="source"))
    runner = PipelineRunner(job, source, is_cancelled=lambda: True)

    def interrupted():
        raise RuntimeError("Transcription cancelled")

    monkeypatch.setattr(runner, "_stage_prepare", interrupted)
    with pytest.raises(JobCancelled):
        await runner.run()
    assert store.get_job(job.id).status == "cancelled"
