from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    from autoclip.app import create_app

    monkeypatch.setenv("AUTOCLIP_NO_WORKER", "1")
    with TestClient(create_app()) as c:
        yield c


def test_cross_origin_writes_and_untrusted_hosts_are_rejected(client):
    assert (
        client.post("/api/jobs", headers={"Origin": "https://evil.example"}, json={}).status_code
        == 403
    )
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/health").status_code == 200


def test_upload_size_limit_is_enforced(client, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_MAX_UPLOAD_BYTES", "8")
    response = client.post(
        "/api/sources/upload", files={"file": ("large.mp4", b"x" * 20, "video/mp4")}
    )
    assert response.status_code == 413


def test_static_traversal_cannot_read_outside_ui(client):
    assert client.get("/%2e%2e/%2e%2e/pyproject.toml").status_code in {400,404,503}


def test_youtube_rejects_credentials_and_non_http_schemes():
    from autoclip.pipeline.ingest import is_youtube_url

    assert not is_youtube_url("file://youtube.com/private")
    assert not is_youtube_url("https://user:password@youtube.com/watch?v=x")
    assert is_youtube_url("https://www.youtube.com/watch?v=x")


def test_playlist_disguised_as_video_is_rejected(tmp_path: Path):
    from autoclip.pipeline.ffmpeg import FFmpegError, probe

    source = tmp_path / "bad.mp4"
    source.write_text("#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:10,\nhttp://127.0.0.1:1/private\n")
    with pytest.raises(FFmpegError):
        probe(source)


def test_cpu_mode_does_not_probe_or_select_gpu(monkeypatch):
    from autoclip.config import ExportSettings, WhisperSettings
    from autoclip.pipeline import export, transcribe

    monkeypatch.setenv("CLIPFORGE_CPU", "1")

    def no_gpu():
        raise AssertionError("CPU mode must not probe GPU")

    monkeypatch.setattr(transcribe, "report", no_gpu)
    monkeypatch.setattr(export, "report", no_gpu)
    assert transcribe.resolve_compute(WhisperSettings(compute_type="float16")) == ("cpu", "int8")
    assert "libx264" in export.encoder_args(ExportSettings())


def test_windows_path_traversal_is_rejected(client):
    from autoclip import paths

    with pytest.raises(ValueError):
        paths.job_work_dir("..\\private")
    assert client.get("/api/jobs/..%5cprivate/quality-status").status_code == 400


def test_caption_text_cannot_inject_ass_commands():
    from autoclip.pipeline.captions import _text_of, get_style
    from autoclip.pipeline.transcript import Word

    text = _text_of(Word(r"{\pos(0,0)}hello", 0, 1), get_style("boxed"))
    assert "{" not in text and "\\" not in text
