"""Clip review, editing, preview media, and export."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import paths
from ..config import load as load_settings
from ..db import store
from ..db.models import Export, new_id
from ..pipeline import captions as captions_module
from ..pipeline import export as export_module
from ..pipeline.corrections import load_transcript, save_corrections
from ..pipeline.editor_options import (
    EditorOptions,
    crop_cache_key,
    load_options,
    render_fingerprint,
    save_options,
)
from ..pipeline.reframe.croppath import CropPath, centre_crop
from ..pipeline.runner import JobWorkspace
from ..pipeline.transcript import Transcript, Word
from .schemas import (
    CaptionPatchIn,
    CaptionStyleOut,
    ClipOut,
    ClipPatchIn,
    ExportOut,
    ExportRequestIn,
    WordOut,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["clips"])


def _clip_out(clip) -> ClipOut:
    edit = store.get_clip_edit(clip.id)
    exports = store.list_exports(clip.id)
    out = ClipOut.of(clip, edit=edit, exports=exports)
    out.render_options = load_options(clip.job_id, clip.id).model_dump()
    if edit is None:
        job = store.get_job(clip.job_id)
        settings = job.settings.get("export", {}) if job else {}
        out.caption_style = settings.get("caption_style", "bold_pop")
        out.ratio = settings.get("ratio", "9:16")
    try:
        words = load_transcript(clip.job_id).slice(clip.start_word, clip.end_word)
    except FileNotFoundError:
        words = []
    out.render_revision = render_fingerprint(
        clip, words, out.caption_style, out.ratio, load_options(clip.job_id, clip.id)
    )
    import json

    for record in out.exports:
        manifest = paths.job_work_dir(clip.job_id) / "render-records" / f"{record.id}.json"
        record.stale = (
            not manifest.exists()
            or json.loads(manifest.read_text())["revision"] != out.render_revision
        )
    return out


async def list_clips_for_job(job_id: str) -> list[ClipOut]:
    job = await asyncio.to_thread(store.get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    clips = await asyncio.to_thread(store.list_clips, job_id)
    return [await asyncio.to_thread(_clip_out, clip) for clip in clips]


@router.get("/clips/{clip_id}", response_model=ClipOut)
async def get_clip(clip_id: str) -> ClipOut:
    clip = await asyncio.to_thread(store.get_clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found.")
    return await asyncio.to_thread(_clip_out, clip)


@router.get("/clips/{clip_id}/words", response_model=list[WordOut])
async def clip_words(clip_id: str) -> list[WordOut]:
    """Words for a clip — the caption editor's source of truth.

    Returns the user's edited words when they exist, falling back to the
    transcript's originals.
    """
    clip = await asyncio.to_thread(store.get_clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found.")

    transcript = await asyncio.to_thread(_load_transcript, clip.job_id)
    words = transcript.slice(clip.start_word, clip.end_word)
    return [WordOut(text=w.text, start=w.start, end=w.end, speaker=w.speaker) for w in words]


@router.get("/clips/{clip_id}/crop-path")
async def clip_crop_path(clip_id: str) -> dict:
    """The computed crop path for a clip, so the preview can match the export.

    Without this the review player can only centre-crop, which on a tracked shot
    shows different framing from the file that gets rendered — sometimes with
    the speaker half out of frame. Reviewing framing against the wrong framing
    is worse than not previewing it at all.
    """
    clip = await asyncio.to_thread(store.get_clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found.")

    cached = JobWorkspace(clip.job_id).crop_path(clip.id)
    job = await asyncio.to_thread(store.get_job, clip.job_id)
    source = await asyncio.to_thread(store.get_source, job.source_id) if job else None
    if source and Path(source.path).is_file():
        saved = await asyncio.to_thread(_clip_out, clip)
        path = await asyncio.to_thread(
            _crop_path_for, JobWorkspace(clip.job_id), clip, source, saved.ratio
        )
        return path.to_dict()
    if not cached.exists():
        # Audio-only sources and pre-reframe jobs legitimately have none; the
        # client falls back to a centre crop.
        raise HTTPException(status_code=404, detail="No crop path for this clip yet.")

    return (await asyncio.to_thread(CropPath.load, cached)).to_dict()


@router.patch("/clips/{clip_id}", response_model=ClipOut)
async def patch_clip(clip_id: str, payload: ClipPatchIn) -> ClipOut:
    """Trim, retitle, or keep/discard a clip.

    A trim re-derives the word range from the new times, so captions stay in
    step with the boundaries without the client having to compute indices.
    """
    clip = await asyncio.to_thread(store.get_clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found.")

    start_s = payload.start_s if payload.start_s is not None else clip.start_s
    end_s = payload.end_s if payload.end_s is not None else clip.end_s
    if end_s <= start_s:
        raise HTTPException(status_code=400, detail="End must come after start.")

    trimmed = payload.start_s is not None or payload.end_s is not None
    start_word = end_word = None

    if trimmed:
        transcript = await asyncio.to_thread(_load_transcript, clip.job_id)
        first, last = transcript.indices_in_range(start_s, end_s)
        start_word, end_word = first, max(first, last - 1)
        # Crop cache keys include trim times; old paths remain available for comparison.

    await asyncio.to_thread(
        store.update_clip,
        clip_id,
        start_s=start_s if trimmed else None,
        end_s=end_s if trimmed else None,
        start_word=start_word,
        end_word=end_word,
        title=payload.title,
        status=payload.status,
        user_trimmed=True if trimmed else None,
    )

    updated = await asyncio.to_thread(store.get_clip, clip_id)
    return await asyncio.to_thread(_clip_out, updated)


@router.patch("/clips/{clip_id}/captions", response_model=ClipOut)
async def patch_captions(clip_id: str, payload: CaptionPatchIn) -> ClipOut:
    """Store word-level caption edits and style choices for a clip."""
    clip = await asyncio.to_thread(store.get_clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found.")

    if payload.caption_style is not None:
        try:
            captions_module.get_style(payload.caption_style)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = await asyncio.to_thread(store.get_clip_edit, clip_id)
    previous = await asyncio.to_thread(_clip_out, clip)
    from ..db.models import ClipEdit

    if payload.words is not None:
        try:
            await asyncio.to_thread(
                save_corrections, clip.job_id, [w.model_dump() for w in payload.words]
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    edit = ClipEdit(
        clip_id=clip_id,
        edited_words=(
            [w.model_dump() for w in payload.words]
            if payload.words is not None
            else (existing.edited_words if existing else None)
        ),
        caption_style=payload.caption_style or previous.caption_style,
        ratio=payload.ratio or previous.ratio,
    )
    await asyncio.to_thread(store.upsert_clip_edit, edit)

    return await asyncio.to_thread(_clip_out, clip)


@router.post("/clips/{clip_id}/export", response_model=ExportOut, status_code=201)
async def export_clip(clip_id: str, payload: ExportRequestIn) -> ExportOut:
    """Render one clip and return its download link."""
    clip = await asyncio.to_thread(store.get_clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found.")

    job = await asyncio.to_thread(store.get_job, clip.job_id)
    source = await asyncio.to_thread(store.get_source, job.source_id) if job else None
    if job is None or source is None:
        raise HTTPException(status_code=404, detail="The clip's source is missing.")

    saved = await asyncio.to_thread(_clip_out, clip)
    if payload.expected_revision and payload.expected_revision != saved.render_revision:
        raise HTTPException(
            status_code=409, detail="Clip changed since preview. Reload and retry export."
        )
    payload.style = payload.style or saved.caption_style
    payload.ratio = payload.ratio or saved.ratio

    try:
        style = captions_module.configured_style(
            captions_module.get_style(payload.style), load_options(clip.job_id, clip.id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    words = [
        Word(text=w.text, start=w.start, end=w.end, speaker=w.speaker)
        for w in await clip_words(clip_id)
    ]

    settings = load_settings()
    settings.export.write_srt = payload.write_srt

    workspace = JobWorkspace(clip.job_id)
    crop_path = await asyncio.to_thread(_crop_path_for, workspace, clip, source, payload.ratio)

    destination = (
        paths.exports_dir()
        / clip.job_id
        / export_module.output_filename(
            f"{clip.title or 'clip'}-{style.key}-{new_id()[:6]}", payload.ratio
        )
    )

    request = export_module.ExportRequest(
        source=Path(source.path),
        destination=destination,
        start_s=clip.start_s,
        end_s=clip.end_s,
        crop_path=crop_path,
        words=words,
        style=style,
        ratio=payload.ratio,
    )

    try:
        await asyncio.to_thread(
            export_module.export_clip,
            request,
            work_dir=workspace.captions_dir,
            settings=settings.export,
        )
    except export_module.ExportError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    record = Export(
        id=new_id(),
        clip_id=clip_id,
        path=str(destination),
        ratio=payload.ratio,
        style=style.key,
        size_bytes=destination.stat().st_size,
    )
    import json

    manifest = workspace.root / "render-records" / f"{record.id}.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "revision": render_fingerprint(
                    clip, words, style.key, payload.ratio, load_options(clip.job_id, clip.id)
                )
            }
        ),
        encoding="utf-8",
    )
    await asyncio.to_thread(store.create_export, record)
    await asyncio.to_thread(store.update_clip, clip_id, status="exported")

    result = ExportOut.of(record)
    result.stale = False
    return result


@router.get("/exports/{export_id}/download")
async def download_export(export_id: str) -> FileResponse:
    record = await asyncio.to_thread(store.get_export, export_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Export not found.")

    path = Path(record.path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="The exported file has been moved or deleted.")

    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/jobs/{job_id}/media")
async def job_media(job_id: str) -> FileResponse:
    """Serve the source video, so the review player can scrub the original.

    Range requests are handled by FileResponse, which is what makes seeking in
    the preview player usable on a long source.
    """
    job = await asyncio.to_thread(store.get_job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    source = await asyncio.to_thread(store.get_source, job.source_id)
    if source is None or not Path(source.path).exists():
        raise HTTPException(status_code=404, detail="Source media not found.")

    return FileResponse(Path(source.path))


@router.get("/caption-styles", response_model=list[CaptionStyleOut])
async def caption_styles() -> list[CaptionStyleOut]:
    """Style presets, with enough detail for the UI to approximate them in CSS."""
    return [
        CaptionStyleOut(
            key=style.key,
            label=style.label,
            description=style.description,
            preview={
                "font": style.font,
                "primary": style.primary,
                "accent": style.accent,
                "outline": style.outline,
                "outlineWidth": style.outline_width,
                "allCaps": style.all_caps,
                "sizeRatio": style.size_ratio,
                "marginRatio": style.margin_v_ratio,
                "boxed": style.boxed,
                "animation": style.animation,
                "maxWords": style.max_words,
            },
        )
        for style in captions_module.PRESETS.values()
    ]


@router.put("/clips/{clip_id}/render-options", response_model=ClipOut)
async def put_render_options(clip_id: str, payload: EditorOptions):
    clip = await asyncio.to_thread(store.get_clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    await asyncio.to_thread(save_options, clip.job_id, clip.id, payload)
    return await asyncio.to_thread(_clip_out, clip)


@router.post("/clips/{clip_id}/readability", response_model=list[WordOut])
async def readability_suggestion(clip_id: str):
    from ..pipeline.readability import readable_words

    words = await clip_words(clip_id)
    return [WordOut(**w.__dict__) for w in readable_words([Word(**w.model_dump()) for w in words])]


@router.post("/clips/{clip_id}/caption-layout")
async def caption_layout(clip_id: str, payload: CaptionPatchIn):
    clip = await asyncio.to_thread(store.get_clip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    saved = await asyncio.to_thread(_clip_out, clip)
    style = captions_module.configured_style(
        captions_module.get_style(saved.caption_style), load_options(clip.job_id, clip_id)
    )
    words = payload.words if payload.words is not None else await clip_words(clip_id)
    words = [Word(**w.model_dump()) for w in words]
    width, height = export_module.ratio_dimensions(saved.ratio)
    return {
        "width": width,
        "height": height,
        "bottom": style.margin_v_ratio,
        "max_width": style.max_width_ratio,
        "groups": [
            {
                "words": [{"text": w.text, "start": w.start, "end": w.end} for w in g.words],
                "font_size": captions_module.fitted_font_size(g, style, width, height),
            }
            for g in captions_module.group_words(words, max_words=style.max_words)
        ],
    }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _load_transcript(job_id: str) -> Transcript:
    workspace = JobWorkspace(job_id)
    if not workspace.transcript.exists():
        raise HTTPException(status_code=404, detail="This job has no transcript yet.")
    return load_transcript(job_id)


def _crop_path_for(workspace: JobWorkspace, clip, source, ratio: str) -> CropPath:
    """Reuse the job's cached crop path, falling back to a centre crop.

    A re-export at a different ratio can't reuse a path computed for the
    original one, so the geometry is recomputed rather than stretched.
    """
    from ..pipeline.reframe import ReframeConfig, build_crop_path

    options = load_options(clip.job_id, clip.id)
    key = crop_cache_key(clip, ratio, options)
    cached = workspace.crop_path(clip.id).with_name(f"{clip.id}-{key}.json")
    if options.framing != "auto":
        from ..pipeline.reframe.croppath import manual_crop

        return manual_crop(
            source.width or 1920, source.height or 1080, clip.end_s - clip.start_s, ratio, options
        )
    if cached.exists():
        return CropPath.load(cached)

    aspect = {"9:16": (9, 16), "1:1": (1, 1), "16:9": (16, 9)}[ratio]
    if Path(source.path).is_file() and source.has_video:
        path = build_crop_path(
            Path(source.path),
            start_s=clip.start_s,
            end_s=clip.end_s,
            transcript=_load_transcript(clip.job_id),
            config=ReframeConfig(
                aspect_w=aspect[0],
                aspect_h=aspect[1],
                subject_position=options.subject_position,
                face_margin=options.face_margin,
            ),
        )
        path.save(cached)
        return path
    return centre_crop(
        source.width or 1920,
        source.height or 1080,
        clip.end_s - clip.start_s,
        aspect_w=aspect[0],
        aspect_h=aspect[1],
    )
