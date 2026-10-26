# v0.1.0-alpha.1 release audit

Recorded 2026-10-27. This is a working Windows-first **alpha**, not a professional
speech-accuracy certification or an internet-hosting security certification.

## Verified results

| Check | Actual result |
| --- | --- |
| Complete backend suite, configured synthetic media and cached-ASR fixtures | **367 passed, 0 failed/skipped**, 104.41 s |
| Clean checkout CPU install (`Install-CLIPFORGE.ps1 -Cpu -SkipModels`) | Passed: fresh isolated environment, pinned dependencies and frontend build |
| Clean environment tests | **342 passed, 25 skipped**, 65.83 s; optional media/ASR fixtures intentionally absent |
| Clean environment dependency consistency | `pip check` passed |
| Frontend action tests | **2 passed** |
| Frontend production build after React Router upgrade | Passed, 1.99 s |
| Clean-checkout launcher | Loopback health HTTP 200; real synthetic MP4 upload HTTP 201 |
| Real local end-to-end processing | 98.533 s synthetic source; real Whisper-small + local phi4-mini, MediaPipe and FFmpeg; 3 MP4 outputs |
| Export checks | 10.133 / 9.700 / 13.000 s, H.264 1080×1920 + AAC; all fully decoded without errors |
| Actual browser test | Isolated headless Chromium; exact rendered preview and seek; no JavaScript errors |
| Responsive geometry | 1920 px viewport / 1920 px document, 390 px viewport / 390 px document: no horizontal overflow |
| Public screenshots/demo | Captured from real isolated synthetic job; desktop screenshot visually inspected; silent GIF from actual export |
| Docker CPU and GPU Compose | Configuration validation passed; image manifests/base digests resolved |
| Docker runtime | **Not tested**: installed Docker client could not connect to the inactive Linux engine |

No paid API was used. Existing private Italian jobs and exports were kept out of
the release. The synthetic fixture uses generated test narration and a documented
public-domain NASA image, not user/YouTube footage. See assets/README.md. The
public GIF has no audio. The demo is not a recording of the pictured person speaking.

## Source/history and license audit

- All **19 upstream commits and 189 historical blobs** were inventoried.
  High-signal credential patterns and a separate detect-secrets scan of every
  historical text blob found no secrets. Generic example user paths in upstream
  tests/comments were reviewed; private machine reports were excluded.
- The publication set excludes environments, node_modules, build caches, logs,
  databases, job artifacts, private reports/scripts, media and model weights.
  Only the explicitly labeled redistributable demo assets are included.
- AutoClip MIT provenance and foundation commit are in NOTICE. Original Jad Ghazi
  copyright is retained; CLIPFORGE modifications are MIT. No OpenClipper/hotclip
  code was incorporated. Bundled fonts retain SIL OFL notices; model cards and
  separate dependency/FFmpeg/NVIDIA terms are recorded in THIRD-PARTY-NOTICES.md.
- No FFmpeg executable, downloaded inference weights or built container image
  is redistributed. Publishing a future binary/container needs its own license
  compliance review. Source license does not override dependency/asset licenses.

## Findings repaired before publication

- Static-file paths are confined to the frontend directory; artifact IDs reject
  separators/traversal. Regression tests include Windows path traversal.
- Trusted-host validation and foreign-Origin write rejection mitigate DNS
  rebinding/cross-site writes. These controls do not implement user authentication.
- Upload size checks, temporary-file cleanup, restricted local container/protocol
  probing and an ffprobe timeout were added. Disguised playlists are rejected.
- Subprocesses use argument lists, not shell interpolation. FFmpeg filter-path
  escaping remains centralized. Caption text cannot introduce ASS override tags.
- CPU mode explicitly selects CPU ASR, CPU Ollama requests and libx264, including
  when a dedicated Ollama server already exists. NVIDIA runtime wheels are optional.
- React Router's two reported npm advisories were resolved by upgrade to 7.18.4.
  The old environment pip had known advisories; pip was upgraded to 26.2.2.
- Final npm audit: **0 known vulnerabilities**. Final pip-audit of the installed
  environment: **0 known vulnerabilities**; the editable local project is skipped
  by the package advisory service and reviewed as source. Audits are point-in-time
  checks, not proof that dependencies are vulnerability-free.

## Remaining limits

Default installation still requires manual Python/Node/FFmpeg/Ollama prerequisites
and potentially large downloads. The clean install used `-SkipModels`; inference
was separately verified using locally cached weights. A first-time cold download
of all default models was not repeated in the clean environment. No execution
policy bypass, administrator install or paid infrastructure was used.

The backend is unauthenticated and intended for a single trusted local user.
Do not expose it or Ollama publicly. Upload checks do not replace reverse-proxy
body limits, rate limits, authentication, storage isolation and resource quotas.
Malformed media remains an attack surface; keep decoders updated and use trusted
media. See SECURITY.md and DEPLOYMENT.md.

Automatic punctuation is conservative and reviewable, not linguistically verified.
The available tools do not support independent listening verification, so WER/CER,
phonetic timing, primary-speaker identity and professional ASR accuracy are not
certified. Titles may be awkward extractive fallbacks; subjective local-model
scores do not predict audience response. Draft CSS preview differs from libass;
use rendered preview. Browser coverage is a smoke test, not comprehensive editor
interaction/accessibility or continuous-video QA. Some rubric notes remain Italian.

CI definitions are supplied for Windows and Ubuntu plus frontend/audit checks.
Local validation above must not be confused with a GitHub-hosted workflow result;
consult the repository Actions tab for actual hosted status.
