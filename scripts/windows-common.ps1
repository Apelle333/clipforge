function Get-ClipforgeHome {
    if ($env:AUTOCLIP_HOME) { return $env:AUTOCLIP_HOME }
    $existing = Join-Path (Split-Path $PSScriptRoot -Parent) '..\data'
    if (Test-Path (Join-Path $existing 'autoclip.db')) { return [IO.Path]::GetFullPath($existing) }
    return Join-Path $env:LOCALAPPDATA 'CLIPFORGE'
}
function Assert-ClipforgePrerequisites {
    $script:PythonCommand = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($version in @('-3.12','-3.11')) {
            & py $version -c 'import sys; assert (3,11)<=sys.version_info[:2]<(3,13)' 2>$null
            if ($LASTEXITCODE -eq 0) { $script:PythonCommand = @('py',$version); break }
        }
    }
    if (!$script:PythonCommand -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -c 'import sys; assert (3,11)<=sys.version_info[:2]<(3,13)' 2>$null
        if ($LASTEXITCODE -eq 0) { $script:PythonCommand = @('python') }
    }
    if (!$script:PythonCommand) { throw 'Install Python 3.12 from python.org (include launcher), then reopen PowerShell.' }
    foreach ($command in @('node','npm.cmd','ffmpeg','ffprobe','ollama')) {
        if (!(Get-Command $command -ErrorAction SilentlyContinue)) { throw "Missing $command. See README prerequisites; install it, reopen PowerShell and retry." }
    }
    $nodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
    if ($nodeMajor -lt 20) { throw 'Node.js 20+ required. Install an active LTS version.' }
    $filters = (& ffmpeg -v error -filters 2>&1 | Out-String)
    $encoders = (& ffmpeg -v error -encoders 2>&1 | Out-String)
    if ($filters -notmatch '\bass\b' -or $encoders -notmatch 'libx264') { throw 'FFmpeg needs libass and libx264. Install a full build; see README.' }
    Write-Host "Prerequisites OK. Python: $script:PythonCommand; Node: $nodeMajor; FFmpeg: libass/libx264."
}
