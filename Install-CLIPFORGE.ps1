param([switch]$Cpu, [switch]$CheckOnly, [switch]$SkipModels)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
. "$PSScriptRoot\scripts\windows-common.ps1"
Assert-ClipforgePrerequisites
if ($CheckOnly) { Write-Host 'Read-only prerequisite check complete.'; return }
$env:AUTOCLIP_HOME = Get-ClipforgeHome
$env:HF_HOME = Join-Path $env:AUTOCLIP_HOME 'huggingface'
$env:PYTHONUTF8 = '1'
$gpu = !$Cpu -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)
if ($gpu) { & nvidia-smi -L; $gpu = $LASTEXITCODE -eq 0 }
if (!(Test-Path '.venv\Scripts\python.exe')) {
    $pythonExe = $script:PythonCommand[0]
    $pythonArgs = @($script:PythonCommand | Select-Object -Skip 1)
    & $pythonExe @pythonArgs -m venv .venv
    if ($LASTEXITCODE) { throw 'Could not create .venv. Check Python and free disk space.' }
}
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $python -m pip install 'pip>=26.2.2'
if ($LASTEXITCODE) { throw 'pip update failed; check connection or configured package index.' }
$lock = if ($gpu) { 'requirements-windows.lock.txt' } else { 'requirements-cpu.lock.txt' }
& $python -m pip install -r $lock
if ($LASTEXITCODE) { throw "Dependency installation failed ($lock). System Python was not changed." }
Push-Location frontend
try {
    & npm.cmd ci
    if ($LASTEXITCODE) { throw 'Frontend dependency installation failed.' }
    & npm.cmd run build
    if ($LASTEXITCODE) { throw 'Frontend build failed.' }
} finally { Pop-Location }
$bootstrapArgs = @('scripts/bootstrap_models.py')
if (!$gpu) { $bootstrapArgs += '--cpu' }
if (!$SkipModels) { $bootstrapArgs += '--download-models' }
& $python @bootstrapArgs
if ($LASTEXITCODE) { throw 'Local configuration/model setup failed. Existing jobs retained.' }
if (!$SkipModels) {
    $env:OLLAMA_HOST='127.0.0.1:11436'; $env:OLLAMA_NO_CLOUD='1'
    $started=$null
    try {
        try { Invoke-RestMethod 'http://127.0.0.1:11436/api/tags' -TimeoutSec 2 | Out-Null }
        catch {
            $started=Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden -PassThru
            $ready=$false
            for($i=0;$i -lt 30;$i++) {
                try { Invoke-RestMethod 'http://127.0.0.1:11436/api/tags' -TimeoutSec 1 | Out-Null; $ready=$true; break } catch { Start-Sleep -Milliseconds 500 }
            }
            if (!$ready) { throw 'Dedicated Ollama did not start on 127.0.0.1:11436.' }
        }
        & ollama pull phi4-mini
        if ($LASTEXITCODE) { throw 'Ollama download failed. Retry installation when online.' }
    } finally { if ($started -and !$started.HasExited) { Stop-Process -Id $started.Id } }
}
Write-Host "Installed. Data: $env:AUTOCLIP_HOME. Run .\Launch-CLIPFORGE.ps1$(if(!$gpu){' -Cpu'})"
