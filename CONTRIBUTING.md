# Contributing

Thanks for helping improve local video tools. Start with a reproducible issue
and a small focused change. Preserve AutoClip attribution and asset licenses.
Do not submit private videos, transcripts, credentials or model weights.

Use Python 3.12, Node 24 and FFmpeg with libass/libx264. On Windows:

```powershell
.\Install-CLIPFORGE.ps1 -Cpu -SkipModels
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
node --test tests/editor-actions.test.mjs
npm run build
```

Optional real-video tests use `AUTOCLIP_E2E_MEDIA`; the real silence test uses
`AUTOCLIP_QUALITY_ASR_MODEL` pointing to a locally cached model. Without these,
the relevant tests skip. Never download copyrighted footage in CI. Use synthetic
or clearly licensed fixtures and state whether model responses are mocked.

Include tests for behavior changes, exact validation results and limitations.
Do not claim transcription accuracy from fluency or ffprobe alone. UI changes
need real screenshots; frame comparisons need the same source moment. Report
WER/CER only against genuinely listening-verified reference text.

Dependencies/weights may have different licenses from our MIT source. Changes
to installs, subprocess calls, file handling and network access need special
review. Contributions are supplied under the project's MIT license, subject to
third-party notices. No CLA or payment is required.
