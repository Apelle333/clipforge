# Installation details

Use README prerequisites first. Supported Python versions are 3.11/3.12;
Windows/Python 3.12 is the locally tested priority. The scripts never change
execution policy, request administrator access or install packages into system
Python. Downloads use public package/model registries and require internet.

`Install-CLIPFORGE.ps1 -CheckOnly` detects commands and FFmpeg features without
installing anything. `-Cpu` avoids optional NVIDIA runtime dependencies.
`-SkipModels` prepares code/UI only; actual inference will still need weights.
Installation preserves existing configuration and data. It is not a transactional
rollback of failed dependency installation; rerun after fixing a reported error.

## Manual commands when scripts cannot be run

These do not change or bypass PowerShell execution policy:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "pip>=26.2.2"
.\.venv\Scripts\python.exe -m pip install -r requirements-cpu.lock.txt
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
$env:AUTOCLIP_HOME=Join-Path $env:LOCALAPPDATA 'CLIPFORGE'
$env:HF_HOME=Join-Path $env:AUTOCLIP_HOME 'huggingface'
$env:CLIPFORGE_CPU='1'
$env:OLLAMA_HOST='127.0.0.1:11436'
$env:OLLAMA_NO_CLOUD='1'
.\.venv\Scripts\python.exe scripts\bootstrap_models.py --cpu --download-models
Start-Process ollama -ArgumentList serve -WindowStyle Hidden
ollama pull phi4-mini
.\.venv\Scripts\autoclip.exe serve --host 127.0.0.1 --port 8078 --open
```

If a dedicated Ollama server is already running, reuse it rather than start a
second one. Manual startup does not automatically stop Ollama when the app exits.
Use the Windows GPU lock instead of the CPU lock only with a supported NVIDIA
driver; omit CLIPFORGE_CPU or set it to 0 to allow GPU inference.

`AUTOCLIP_HOME` contains private paths/settings; do not commit it. `.env` is
not loaded by the Windows launcher. Keep several GB free for weights, environments
and temporary renders, plus space for copies of input videos and exports.

Optional alignment: `Setup-Alignment.ps1` installs a separate CPU environment;
it is slower and can reject alignment, retaining original ASR times. It does
not install gated diarization or make inaccurate words correct.

## Updating safely

Stop the server and back up runtime data. `Update-CLIPFORGE.ps1` supports a
clean checkout from the official origin and refuses local edits/non-fast-forward
changes. It does not erase jobs. ZIP installs should use a new extracted folder.
For source contributors, update manually and review merges; never reset away
work to satisfy the updater.
