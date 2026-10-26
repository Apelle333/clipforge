param([ValidateRange(1024,65535)][int]$Port=8078,[switch]$Cpu,[switch]$NoBrowser)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
. "$PSScriptRoot\scripts\windows-common.ps1"
$env:AUTOCLIP_HOME=Get-ClipforgeHome
$env:HF_HOME=Join-Path $env:AUTOCLIP_HOME 'huggingface'
$env:PYTHONUTF8='1'
$env:OLLAMA_HOST='127.0.0.1:11436'
$env:OLLAMA_NO_CLOUD='1'
$env:OLLAMA_NUM_PARALLEL='1'
$env:OLLAMA_MAX_LOADED_MODELS='1'
$env:CLIPFORGE_CPU=if($Cpu){'1'}else{'0'}
if($Cpu){$env:CUDA_VISIBLE_DEVICES='-1'}
if(!(Test-Path '.venv\Scripts\autoclip.exe')){throw 'Run Install-CLIPFORGE.ps1 first.'}
New-Item -ItemType Directory -Force $env:AUTOCLIP_HOME | Out-Null
$ollamaProcess=$null
try {
    try { Invoke-RestMethod 'http://127.0.0.1:11436/api/tags' -TimeoutSec 2 | Out-Null }
    catch {
        if(!(Get-Command ollama -ErrorAction SilentlyContinue)){throw 'Ollama missing. Install from ollama.com, then rerun installer.'}
        $ollamaProcess=Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $env:AUTOCLIP_HOME 'ollama-out.log') -RedirectStandardError (Join-Path $env:AUTOCLIP_HOME 'ollama-error.log')
    }
    $browserFlag=if($NoBrowser){'--no-open'}else{'--open'}
    & '.\.venv\Scripts\autoclip.exe' serve --host 127.0.0.1 --port $Port $browserFlag
    $appExitCode=$LASTEXITCODE
} finally { if($ollamaProcess -and !$ollamaProcess.HasExited){Stop-Process -Id $ollamaProcess.Id} }
exit $appExitCode
