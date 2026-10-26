"""Job lifecycle and the SSE progress stream."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from ..config import load as load_settings
from ..db import store
from ..db.models import Job, new_id
from ..jobs.events import broker
from ..jobs.queue import queue
from .schemas import CaptionPatchIn, JobCreateIn, JobOut, JobSettingsIn

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _apply_overrides(settings, overrides: JobSettingsIn):
    """Layer per-job overrides on top of saved settings."""
    merged = settings.model_copy(deep=True)

    if overrides.provider:
        merged.active_provider = overrides.provider
    if overrides.whisper_model:
        merged.whisper.model = overrides.whisper_model
    if overrides.language is not None:
        merged.whisper.language = overrides.language
    if overrides.diarization is not None:
        merged.whisper.diarization = overrides.diarization
    if overrides.min_duration_s is not None:
        merged.clips.min_duration_s = overrides.min_duration_s
    if overrides.max_duration_s is not None:
        merged.clips.max_duration_s = overrides.max_duration_s
    if overrides.max_clips is not None:
        merged.clips.max_clips = overrides.max_clips
    if overrides.caption_style:
        merged.export.caption_style = overrides.caption_style
    if overrides.ratio:
        merged.export.ratio = overrides.ratio

    return merged


@router.post("", response_model=JobOut, status_code=201)
async def create_job(payload: JobCreateIn) -> JobOut:
    source = await asyncio.to_thread(store.get_source, payload.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")

    settings = _apply_overrides(load_settings(), payload.settings)
    if settings.clips.min_duration_s >= settings.clips.max_duration_s:
        raise HTTPException(
            status_code=400, detail="Minimum clip length must be below the maximum."
        )

    job = Job(
        id=new_id(),
        source_id=source.id,
        provider=settings.active_provider,
        settings=settings.model_dump(mode="json"),
    )
    await asyncio.to_thread(store.create_job, job)
    queue.notify()

    return JobOut.of(job, source)


@router.get("", response_model=list[JobOut])
async def list_jobs(limit: int = 25) -> list[JobOut]:
    jobs = await asyncio.to_thread(store.list_jobs, limit)
    out: list[JobOut] = []
    for job in jobs:
        source = await asyncio.to_thread(store.get_source, job.source_id)
        out.append(JobOut.of(job, source))
    return out


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str) -> JobOut:
    job = await asyncio.to_thread(store.get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    source = await asyncio.to_thread(store.get_source, job.source_id)
    return JobOut.of(job, source)


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request) -> EventSourceResponse:
    """Stream progress for a job as Server-Sent Events."""
    job = await asyncio.to_thread(store.get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    async def stream():
        # Send the current state immediately: a client connecting mid-job (or
        # reconnecting) must not wait for the next progress tick to render.
        current = await asyncio.to_thread(store.get_job, job_id)
        if current is not None:
            yield {
                "event": "snapshot",
                "data": JobOut.of(current).model_dump_json(),
            }
            if current.status in ("done", "failed", "cancelled"):
                return

        async for event in broker.subscribe(job_id):
            if await request.is_disconnected():
                break
            yield {"event": event.type, "data": event.to_sse().split("data: ", 1)[-1].strip()}

    return EventSourceResponse(stream())


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str) -> JobOut:
    job = await asyncio.to_thread(store.get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    if not queue.cancel(job_id):
        raise HTTPException(
            status_code=409, detail=f"Job is already {job.status}; nothing to cancel."
        )

    updated = await asyncio.to_thread(store.get_job, job_id)
    return JobOut.of(updated or job)


@router.post("/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: str) -> JobOut:
    """Requeue a failed or cancelled job.

    Completed stages left their artifacts in ``work/{job_id}/``, so the retry
    resumes at the stage that failed rather than starting over.
    """
    job = await asyncio.to_thread(store.get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Only failed or cancelled jobs can be retried (this one is {job.status}).",
        )

    queue.clear_cancel(job_id)
    await asyncio.to_thread(store.update_job, job_id, status="queued", error=None, progress=0.0)
    queue.notify()

    updated = await asyncio.to_thread(store.get_job, job_id)
    return JobOut.of(updated or job)


@router.get("/{job_id}/clips")
async def job_clips(job_id: str):
    from .clips import list_clips_for_job

    return await list_clips_for_job(job_id)


@router.get("/{job_id}/transcript")
async def get_transcript(job_id: str):
    from dataclasses import asdict

    from ..pipeline.corrections import load_transcript

    try:
        transcript = await asyncio.to_thread(load_transcript, job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Transcript not found") from exc
    return {
        "words": [asdict(w) for w in transcript.words],
        "language": transcript.language,
        "metadata": transcript.metadata,
    }


@router.get("/{job_id}/quality-status")
async def quality_status(job_id: str):
    import json

    from .. import paths

    path = paths.job_work_dir(job_id) / "highlight-status.json"
    if not path.exists():
        return {
            "status": "legacy-unverified",
            "failures": [],
            "note": "Legacy scores have not been validated with the required rubric.",
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("responses", None)
    from ..pipeline.corrections import load_transcript

    transcript = await asyncio.to_thread(load_transcript, job_id)
    from ..pipeline.readability import transcript_revision

    if data.get("transcript_revision") and data["transcript_revision"] != transcript_revision(
        transcript.words
    ):
        data["status"] = "stale — transcript changed; re-score before trusting titles and ranking"
    data["language"] = transcript.language
    data["alignment"] = transcript.metadata.get("alignment", "legacy-whisper")
    data["alignment_warning"] = transcript.metadata.get("alignment_warning")
    return data


@router.get("/{job_id}/selection")
async def selection_comparison(job_id: str):
    import json

    from .. import paths

    if await asyncio.to_thread(store.get_job, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    path = paths.job_work_dir(job_id) / "selection.json"
    return (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {
            "note": "Legacy job: candidate comparison was not recorded. Re-score to compare.",
            "selected": [],
            "alternatives": [],
        }
    )


@router.patch("/{job_id}/transcript")
async def patch_transcript(job_id: str, payload: CaptionPatchIn):
    from ..pipeline.corrections import save_corrections

    if payload.words is None:
        raise HTTPException(status_code=422, detail="Words are required")
    try:
        await asyncio.to_thread(save_corrections, job_id, [w.model_dump() for w in payload.words])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await get_transcript(job_id)


@router.post("/{job_id}/reanalyze", response_model=JobOut, status_code=201)
async def reanalyze(job_id: str):
    from ..db.models import Transcript as TranscriptRow
    from ..pipeline.corrections import load_transcript
    from ..pipeline.runner import JobWorkspace

    original = await asyncio.to_thread(store.get_job, job_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Job not found")
    transcript = await asyncio.to_thread(load_transcript, job_id)
    settings = load_settings()
    job = Job(
        id=new_id(), source_id=original.source_id, provider="ollama", settings=settings.model_dump()
    )
    await asyncio.to_thread(store.create_job, job)
    destination = JobWorkspace(job.id).transcript
    transcript.save(destination)
    store.upsert_transcript(
        TranscriptRow(
            job_id=job.id,
            json_path=str(destination),
            language=transcript.language,
            model=transcript.model,
            word_count=len(transcript.words),
        )
    )
    queue.notify()
    return JobOut.of(job)
