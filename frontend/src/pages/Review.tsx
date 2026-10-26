import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'

import {
  api,
  formatBytes,
  formatDuration,
  type CaptionStyle,
  type Clip,
  type CropPath,
  type Job,
  type Word,
  type CaptionLayout,
} from '../api'
import { CaptionEditor } from '../components/CaptionEditor'
import { ClipPlayer } from '../components/ClipPlayer'
import { ErrorNote } from '../components/ErrorNote'
import { TrimBar } from '../components/TrimBar'
import { exportSavedEdit } from '../editorActions'

const RATIOS = ['9:16', '1:1', '16:9'] as const

export function Review() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const [job, setJob] = useState<Job | null>(null)
  const [clips, setClips] = useState<Clip[]>([])
  const [styles, setStyles] = useState<CaptionStyle[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [words, setWords] = useState<Word[]>([])
  const [cropPath, setCropPath] = useState<CropPath | null>(null)
  const [wordsDirty, setWordsDirty] = useState(false)
  const [savingWords, setSavingWords] = useState(false)
  const [exporting, setExporting] = useState<Set<string>>(new Set())
  const [error, setError] = useState<Error | null>(null)
  const [layout,setLayout] = useState<CaptionLayout | null>(null)
  const [savingOptions,setSavingOptions] = useState(false)
  const [renderedUrl,setRenderedUrl] = useState<string | null>(null)
  const [formatting,setFormatting] = useState(false)
  const [comparison,setComparison] = useState<{note:string;exclusions?:Record<string,string>;alternatives:{title:string;score:number;reason:string;start_word_index:number;end_word_index:number}[]} | null>(null)
  const [quality,setQuality] = useState<{status:string;failures:string[];language?:string;alignment?:string;alignment_warning?:string} | null>(null)

  useEffect(() => {
    if (!jobId) return
    fetch(`/api/jobs/${jobId}/selection`).then(r=>r.ok?r.json():null).then(setComparison).catch(()=>setComparison(null))
    fetch(`/api/jobs/${jobId}/quality-status`).then((r)=>r.json()).then(setQuality).catch(()=>setQuality(null))
    void Promise.all([api.getJob(jobId), api.listClips(jobId), api.captionStyles()])
      .then(([loadedJob, loadedClips, loadedStyles]) => {
        setJob(loadedJob)
        setClips(loadedClips)
        setStyles(loadedStyles)
        setSelectedId((current) => current ?? loadedClips[0]?.id ?? null)
      })
      .catch((err) => setError(err as Error))
  }, [jobId])

  const selected = useMemo(
    () => clips.find((clip) => clip.id === selectedId) ?? null,
    [clips, selectedId],
  )

  useEffect(() => {
    if (!selected) return
    let active = true
    setWordsDirty(false)
    setWords([])
    setCropPath(null)
    api
      .getClipWords(selected.id)
      .then((value) => { if (active) setWords(value) })
      .catch(() => { if (active) setWords([]) })
    // 404 is expected for audio-only sources and jobs that never reframed; the
    // player falls back to a centre crop, matching what the renderer does.
    api
      .getCropPath(selected.id)
      .then((value) => { if (active) setCropPath(value) })
      .catch(() => { if (active) setCropPath(null) })
    return () => { active = false }
  }, [selected?.id])

  useEffect(() => {
    setRenderedUrl(null)
    setLayout(null)
    if (!selected || !words.length) return
    let active=true
    api.captionLayout(selected.id,words).then((value) => {if(active) setLayout(value)}).catch((err) => {if(active) setError(err)})
    return () => {active=false}
  },[selected?.id,selected?.caption_style,selected?.ratio,JSON.stringify(selected?.render_options),words])

  const patchClip = useCallback((updated: Clip) => {
    setClips((current) => current.map((clip) => (clip.id === updated.id ? updated : clip)))
  }, [])

  const setStatus = async (clip: Clip, status: Clip['status']) => {
    try {
      patchClip(await api.patchClip(clip.id, { status }))
    } catch (err) {
      setError(err as Error)
    }
  }

  const saveOptions = async (options: Clip['render_options']) => {
    if (!selected) return
    setSavingOptions(true)
    setRenderedUrl(null)
    try { patchClip(await api.renderOptions(selected.id,options)); setCropPath(await api.getCropPath(selected.id)) }
    catch(err) { setError(err as Error) } finally { setSavingOptions(false) }
  }

  const commitTrim = async (start: number, end: number) => {
    if (!selected) return
    setSavingOptions(true)
    try {
      if (wordsDirty) await api.patchCaptions(selected.id,{words})
      setRenderedUrl(null)
      patchClip(await api.patchClip(selected.id, { start_s: start, end_s: end }))
      setWords(await api.getClipWords(selected.id))
      setCropPath(await api.getCropPath(selected.id))
      setWordsDirty(false)
    } catch (err) {
      setError(err as Error)
    } finally {setSavingOptions(false)}
  }

  const saveWords = async () => {
    if (!selected) return
    setSavingWords(true)
    try {
      patchClip(await api.patchCaptions(selected.id, { words }))
      setWordsDirty(false)
      fetch(`/api/jobs/${jobId}/quality-status`).then(r=>r.json()).then(setQuality).catch(()=>{})
    } catch (err) {
      setError(err as Error)
    } finally {
      setSavingWords(false)
    }
  }

  const setStyle = async (clip: Clip, styleKey: string) => {
    setSavingOptions(true)
    try {
      patchClip(await api.patchCaptions(clip.id, { caption_style: styleKey }))
    } catch (err) {
      setError(err as Error)
    } finally {setSavingOptions(false)}
  }

  const setRatio = async (clip: Clip, ratio: string) => {
    setSavingOptions(true)
    try {
      patchClip(await api.patchCaptions(clip.id, { ratio }))
      setCropPath(await api.getCropPath(clip.id))
    } catch (err) {
      setError(err as Error)
    } finally {setSavingOptions(false)}
  }

  const exportClip = async (clip: Clip) => {
    setExporting((current) => new Set(current).add(clip.id))
    setError(null)
    try {
      const record = await exportSavedEdit(api,clip.id, wordsDirty && selectedId === clip.id ? words : undefined)
      if (selectedId === clip.id) setWordsDirty(false)
      patchClip(await api.getClip(clip.id))
      if (selectedId === clip.id) setRenderedUrl(record.download_url)
    } catch (err) {
      setError(err as Error)
    } finally {
      setExporting((current) => {
        const next = new Set(current)
        next.delete(clip.id)
        return next
      })
    }
  }

  const exportKept = async () => {
    const targets = clips.filter((clip) => clip.status === 'kept')
    for (const clip of targets) await exportClip(clip)
  }

  const keptCount = clips.filter((clip) => clip.status === 'kept').length
  const activeStyle = styles.find((style) => style.key === selected?.caption_style)

  if (error && clips.length === 0) {
    return (
      <div className="max-w-3xl pt-24">
        <ErrorNote error={error} />
      </div>
    )
  }

  if (!job) return <p className="pt-24 text-sm text-ink-500">Loading…</p>

  return (
    <div className="pt-10">
      <div className="flex flex-wrap items-baseline justify-between gap-4 border-b border-ink-800 pb-5">
        <div className="min-w-0">
          <Link to="/" className="eyebrow transition-colors hover:text-sodium-500">
            ← All jobs
          </Link>
          <h1 className="mt-2 max-w-2xl truncate font-display text-[clamp(1.5rem,3vw,2.25rem)] leading-tight text-ink-100">
            {job.source?.title || 'Untitled'}
          </h1>
        </div>

        <div className="flex items-baseline gap-6">
          <button className="btn btn-quiet" disabled={savingWords || savingOptions || exporting.size>0} onClick={async()=>{
            try {if (wordsDirty && selected) {await api.patchCaptions(selected.id,{words});setWordsDirty(false)}
              const next=await api.reanalyze(jobId!);navigate(`/jobs/${next.id}`)
            } catch(err){setError(err as Error)}
          }}>Re-score corrected transcript</button>
          <span className="numeric text-xs text-ink-500">
            {clips.length} clips · {keptCount} kept
          </span>
          <button onClick={exportKept} disabled={keptCount === 0 || exporting.size>0 || savingOptions || savingWords || formatting} className="btn btn-primary">
            Export kept
          </button>
        </div>
      </div>
      {quality && <p className="mt-3 text-xs text-ink-300" role="status">AI scoring: {quality.status}{quality.failures.length>0 ? ` — ${quality.failures.length} window(s) failed; review partial results.` : ''}{quality.language ? ` · Language: ${quality.language}` : ''}{quality.alignment ? ` · Timing: ${quality.alignment}` : ''}{quality.alignment_warning ? ' · Forced alignment failed; original ASR times retained.' : ''}</p>}

      {error && (
        <div className="mt-6 max-w-3xl">
          <ErrorNote error={error} onDismiss={() => setError(null)} />
        </div>
      )}

      {clips.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="mt-8 grid gap-x-10 gap-y-10 xl:grid-cols-[minmax(14rem,.7fr)_minmax(22rem,1.2fr)_minmax(22rem,1fr)] lg:grid-cols-2">
          {/* Ranked list */}
          <section className="lg:max-h-[76vh] lg:overflow-y-auto lg:pr-1 lg:col-span-2 xl:col-span-1">
            <p className="eyebrow border-b border-ink-800 pb-2">AI suggestions · subjective scores</p>
            <ul>
              {clips.map((clip, index) => (
                <li key={clip.id}>
                  <ClipRow
                    clip={clip}
                    index={index}
                    selected={clip.id === selectedId}
                    onSelect={async() => {
                      if (savingWords || savingOptions || formatting || exporting.size>0) return
                      try {if(wordsDirty && selected){await api.patchCaptions(selected.id,{words});setWordsDirty(false)};setSelectedId(clip.id)}
                      catch(err){setError(err as Error)}
                    }}
                    onKeep={() =>
                      setStatus(clip, clip.status === 'kept' ? 'candidate' : 'kept')
                    }
                    onDiscard={() =>
                      setStatus(clip, clip.status === 'discarded' ? 'candidate' : 'discarded')
                    }
                  />
                </li>
              ))}
            </ul>
          </section>

          {/* Player + trim */}
          <section className="space-y-8">
            {selected && jobId && (
              <>
                <ClipPlayer
                  src={renderedUrl ?? api.mediaUrl(jobId)}
                  startS={renderedUrl ? 0 : selected.start_s}
                  endS={renderedUrl ? selected.duration_s : selected.end_s}
                  words={renderedUrl ? [] : words}
                  style={renderedUrl ? undefined : activeStyle}
                  ratio={selected.ratio}
                  cropPath={renderedUrl ? null : cropPath}
                  layout={layout}
                />
                <p className="text-xs text-ink-400">{renderedUrl ? 'Exact exported preview — this is the rendered MP4.' : 'Draft approximation — CSS captions and framing can differ. Render preview for exact output.'}
                  {renderedUrl && <button className="btn btn-quiet" onClick={() => setRenderedUrl(null)}>Back to editing</button>}
                </p>
                {!renderedUrl && <button className="btn btn-ghost" disabled={exporting.size>0 || savingOptions || savingWords || formatting} onClick={()=>exportClip(selected)}>Render exact preview</button>}
                {selected.exports.filter(e=>!e.stale).slice(-1).map(e=><button key={e.id} className="btn btn-quiet" disabled={wordsDirty} onClick={()=>setRenderedUrl(e.download_url)}>View current rendered preview</button>)}
                <fieldset disabled={savingOptions || savingWords || formatting || exporting.size>0}>
                <TrimBar
                  words={words}
                  startS={selected.start_s}
                  endS={selected.end_s}
                  originalStart={selected.start_s}
                  originalEnd={selected.end_s}
                  onCommit={commitTrim}
                />
                </fieldset>
              </>
            )}
          </section>

          {/* Editor + style */}
          <section className="space-y-10">
            {selected && (
              <>
                <div>
                  <p className="eyebrow">Selection notes · subjective model assessment</p>
                  <p className="mt-2 max-w-prose text-[0.9375rem] leading-relaxed text-ink-300">
                    {selected.reason || 'No rationale returned for this clip.'}
                  </p>
                  {selected.hook && (
                    <p className="mt-3 border-l-2 border-ink-700 pl-3 font-display text-lg italic text-ink-200">
                      “{selected.hook}”
                    </p>
                  )}
                  {comparison && <details className="mt-4 text-sm text-ink-300">
                    <summary className="cursor-pointer text-sodium-500">Compare alternative candidates</summary>
                    <p className="mt-2 text-xs leading-relaxed">{comparison.note}</p>
                    <ol className="mt-3 space-y-3">{comparison.alternatives.slice(0,8).map((c,i)=><li key={i} className="border-l border-ink-700 pl-3">
                      <p>{c.score} · {c.title}</p><p className="mt-1 text-xs text-ink-400">{c.reason}</p>
                      {comparison.exclusions?.[String(c.start_word_index)] && <p className="mt-1 text-xs text-sodium-500">{comparison.exclusions[String(c.start_word_index)]}</p>}
                    </li>)}</ol>
                  </details>}
                </div>

                <fieldset disabled={savingOptions || exporting.size>0}>
                <CaptionEditor
                  words={words}
                  onChange={(next) => {
                    setWords(next)
                    setWordsDirty(true)
                  }}
                  onFormat={async()=>{
                    if (!selected || formatting) return
                    setFormatting(true)
                    try {
                      if (wordsDirty) await api.patchCaptions(selected.id,{words})
                      setWords(await api.readability(selected.id));setWordsDirty(true)
                    } catch(err){setError(err as Error)} finally{setFormatting(false)}
                  }}
                  onSave={saveWords}
                  saving={savingWords || formatting}
                  dirty={wordsDirty}
                />
                </fieldset>

                <div>
                  <p className="eyebrow border-b border-ink-800 pb-2">Framing and captions</p>
                  <label className="mt-4 block text-sm text-ink-200">Framing mode
                    <select className="field mt-2" value={selected.render_options.framing} disabled={savingOptions || exporting.size>0} onChange={e=>saveOptions({...selected.render_options,framing:e.target.value as Clip['render_options']['framing']})}>
                      <option value="auto">Automatic · safe face framing</option><option value="fit">Fit whole scene · preserve all subjects</option><option value="manual">Manual static portrait crop</option>
                    </select>
                  </label>
                  {selected.render_options.framing==='manual' && <div className="mt-3 grid grid-cols-2 gap-4">
                    {(['manual_x','manual_y'] as const).filter(key=>!cropPath || (key==='manual_x' ? cropPath.source_width > cropPath.segments[0].width : cropPath.source_height > cropPath.segments[0].height)).map(key=><label key={key} className="text-xs text-ink-300">{key==='manual_x'?'Horizontal position':'Vertical position'}
                      <input type="range" min="0" max="1" step=".02" className="mt-3 w-full" defaultValue={selected.render_options[key]} key={`${selected.id}-${key}`} disabled={savingOptions || exporting.size>0} onPointerUp={e=>saveOptions({...selected.render_options,[key]:Number(e.currentTarget.value)})} onKeyUp={e=>{if(e.key.startsWith('Arrow'))void saveOptions({...selected.render_options,[key]:Number(e.currentTarget.value)})}} />
                    </label>)}
                    <p className="col-span-2 text-xs text-ink-400">Static crop has no tracking movement. Check the full face throughout the clip; use Fit if no portrait crop can contain it.</p>
                  </div>}

                  <div className="mt-4 grid grid-cols-2 gap-4">
                    {([['size','Caption size',.6,1.4,.05],['max_width','Text width',.55,.9,.05],['bottom','Bottom safe area',.12,.3,.02],['subject_position','Subject position',.35,.65,.05],['face_margin','Face safe margin',.05,.25,.05]] as const).map(([key,label,min,max,step]) => <label key={key} className="text-xs text-ink-300">{label}
                      <input className="field mt-2" type="number" min={min} max={max} step={step} defaultValue={selected.render_options[key]} key={`${selected.id}-${key}-${selected.render_options[key]}`}
                        disabled={savingOptions || exporting.size>0 || ((key==='subject_position' || key==='face_margin') && selected.render_options.framing!=='auto')} onBlur={async(e) => {
                          const value=Number(e.target.value); if (!Number.isFinite(value) || value<min || value>max) return
                          setSavingOptions(true)
                          try {patchClip(await api.renderOptions(selected.id,{...selected.render_options,[key]:value})); setCropPath(await api.getCropPath(selected.id))}
                          catch(err){setError(err as Error)} finally{setSavingOptions(false)}
                        }} />
                    </label>)}
                  </div>
                  <div className="mt-3 space-y-1">
                    {styles.map((style) => (
                      <button
                        key={style.key}
                        disabled={savingOptions || exporting.size > 0}
                        onClick={() => setStyle(selected, style.key)}
                        className={[
                          'block w-full border-l-2 py-2 pl-3 text-left transition-colors duration-200',
                          style.key === selected.caption_style
                            ? 'border-sodium-500 bg-ink-850/60'
                            : 'border-transparent hover:border-ink-700 hover:bg-ink-850/30',
                        ].join(' ')}
                            >
                        <span className="text-sm text-ink-100">{style.label}</span>
                        <span className="mt-0.5 block text-xs leading-snug text-ink-500">
                          {style.description}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="eyebrow border-b border-ink-800 pb-2">Aspect ratio</p>
                  <div className="mt-3 flex gap-2">
                    {RATIOS.map((ratio) => (
                      <button
                        key={ratio}
                        disabled={savingOptions || exporting.size>0}
                        onClick={() => setRatio(selected, ratio)}
                        className={[
                          'numeric btn',
                          ratio === selected.ratio ? 'btn-primary' : 'btn-ghost',
                        ].join(' ')}
                      >
                        {ratio}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="border-t border-ink-800 pt-6">
                  <button
                    onClick={() => exportClip(selected)}
                    disabled={exporting.has(selected.id) || savingOptions || savingWords || formatting}
                    className="btn btn-primary w-full"
                  >
                    {exporting.has(selected.id) ? 'Rendering…' : 'Export this clip'}
                  </button>

                  {selected.exports.length > 0 && (
                    <ul className="mt-4 space-y-2">
                      {selected.exports.map((record) => (
                        <li
                          key={record.id}
                          className="flex items-baseline justify-between gap-3 text-xs"
                        >
                          <a
                            href={record.download_url}
                            download
                            className="truncate text-sodium-500 underline underline-offset-4"
                          >
                            {record.ratio} · {record.style}{record.stale ? ' · previous render' : ' · current'}
                          </a>
                          <span className="numeric shrink-0 text-ink-600">
                            {formatBytes(record.size_bytes)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

function ClipRow({
  clip,
  index,
  selected,
  onSelect,
  onKeep,
  onDiscard,
}: {
  clip: Clip
  index: number
  selected: boolean
  onSelect: () => void
  onKeep: () => void
  onDiscard: () => void
}) {
  return (
    <div
      className={[
        'rise group grid cursor-pointer grid-cols-[2.25rem_1fr] gap-x-3 border-b border-ink-850 py-3 pl-2 transition-colors duration-200',
        selected ? 'bg-ink-850/70' : 'hover:bg-ink-850/35',
        clip.status === 'discarded' ? 'opacity-40' : '',
      ].join(' ')}
      style={{ animationDelay: `${Math.min(index, 10) * 35}ms` }}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onSelect()
      }}
    >
      {/* The score is the thing you scan by, so it gets the display face. */}
      <span
        className={[
          'numeric self-start font-display text-2xl leading-none',
          clip.score >= 85 ? 'text-sodium-500' : selected ? 'text-ink-200' : 'text-ink-500',
        ].join(' ')}
      >
        {clip.score}
      </span>

      <div className="min-w-0">
        <p className="truncate text-[0.9375rem] leading-snug text-ink-100">
          {clip.title || 'Untitled clip'}
        </p>
        <div className="mt-1 flex items-baseline gap-3">
          <span className="numeric text-xs text-ink-500">{formatDuration(clip.duration_s)}</span>
          {clip.user_trimmed && <span className="text-xs text-ink-600">trimmed</span>}
          {clip.exports.length > 0 && (
            <span className="text-xs text-signal-good">exported</span>
          )}

          {/* Secondary actions appear on hover or when the row is current —
              progressive disclosure keeps the scan column clean. */}
          <span
            className={[
              'ml-auto flex gap-3 pr-2 transition-opacity duration-200',
              selected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
            ].join(' ')}
          >
            <button
              onClick={(e) => {
                e.stopPropagation()
                onKeep()
              }}
              className={`text-xs ${clip.status === 'kept' ? 'text-signal-good' : 'text-ink-400 hover:text-ink-100'}`}
            >
              {clip.status === 'kept' ? 'kept' : 'keep'}
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation()
                onDiscard()
              }}
              className="text-xs text-ink-400 hover:text-signal-bad"
            >
              {clip.status === 'discarded' ? 'undo' : 'drop'}
            </button>
          </span>
        </div>
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="max-w-xl pt-20">
      <h2 className="font-display text-3xl text-ink-200">No clips came back.</h2>
      <p className="mt-4 text-sm leading-relaxed text-ink-400">
        The model found nothing self-contained enough to stand alone — which is a real
        answer for some source material, not necessarily a failure.
      </p>
      <p className="mt-3 text-sm leading-relaxed text-ink-400">
        If you expected clips, try a larger provider model, or widen the length range so
        shorter moments qualify.
      </p>
    </div>
  )
}
