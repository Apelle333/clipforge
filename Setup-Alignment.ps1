$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (!(Test-Path .align-venv\Scripts\python.exe)) {
    py -3.12 -m venv .align-venv
    if ($LASTEXITCODE) { throw 'Could not create isolated alignment environment' }
}
& .\.align-venv\Scripts\python.exe -m pip install torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE) { throw 'CPU PyTorch installation failed' }
& .\.align-venv\Scripts\python.exe -m pip install -r requirements-alignment.lock.txt
if ($LASTEXITCODE) { throw 'WhisperX installation failed' }
& .\.align-venv\Scripts\python.exe -c "from whisperx.alignment import align, load_align_model; print('WhisperX alignment ready; model downloads on first use')"
exit $LASTEXITCODE
