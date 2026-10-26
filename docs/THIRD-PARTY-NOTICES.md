# Third-party notices

AutoClip by Jad Ghazi is the MIT foundation, commit
`5d0eac36fa615b79dd2104083bf273a96f8d68bb`. See LICENSE and NOTICE. No code from
OpenClipper/hotclip was incorporated. The backend package/CLI retains its
`autoclip` name for compatibility; CLIPFORGE is an independent adaptation.

Bundled Anton, Inter, Archivo and Instrument Serif fonts are SIL OFL 1.1.
Their original license texts are beside the fonts and in docs/licenses;
font-metadata.json records the actual bundled file hashes and embedded notices.
Fonts are not relicensed MIT.

Downloaded assets (weights are not shipped in Git):

| Asset | Model-card license / source |
| --- | --- |
| faster-whisper-small | MIT, [Systran](https://huggingface.co/Systran/faster-whisper-small), pinned revision 536b0662742c02347bc0e980a01041f333bce120 |
| faster-whisper-large-v3 | MIT, [Systran](https://huggingface.co/Systran/faster-whisper-large-v3), tested revision edaa852ec7e145841d8ffdb056a99866b5f0a478 |
| large-v3-turbo conversion | MIT, [Dropbox Dash](https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo) |
| Phi-4-mini-instruct | MIT, [Microsoft](https://huggingface.co/microsoft/Phi-4-mini-instruct); Ollama phi4-mini tag can change |
| MediaPipe face_landmarker v1 | Apache-2.0 model cards, [Google](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker); SHA256 64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff |
| Optional Italian alignment | Apache-2.0, [wav2vec2 Italian](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-italian); WhisperX itself is BSD-2-Clause |

Saved license texts/model cards are in docs/licenses. Optional gated diarization
models are not installed by the default installer. Review the license of any
different model you choose.

FFmpeg is an external executable. Full builds with libx264 are GPL-enabled;
no executable is included in this source release. Dockerfiles install FFmpeg
from Debian. Redistributing a built container/binary requires its own GPL
source/license compliance. NVIDIA runtime wheels use NVIDIA terms and are
optional local dependencies, not MIT assets. Other dependencies retain their
distribution licenses. A Python dependency lock does not relicense packages.

The labeled synthetic demo uses locally generated test narration and the NASA
Eileen Collins astronaut image supplied with scikit-image, documented as public
domain: https://scikit-image.org/docs/stable/api/skimage.data.html#skimage.data.astronaut .
No endorsement by the person pictured is implied. Real user/YouTube footage,
transcripts, job databases and exports are not part of this source release.
