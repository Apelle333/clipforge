param([switch]$Cpu,[switch]$SkipModels)
$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if(!(Get-Command git -ErrorAction SilentlyContinue)){throw 'Git required. ZIP installs: download the new release into a separate folder.'}
if(git status --porcelain){throw 'Local changes found. Preserve/commit them before updating; nothing was overwritten.'}
$remoteName='origin'
$remote=git remote get-url origin
if($remote -notmatch '^https://github\.com/Apelle333/clipforge(?:\.git)?$') {
    $remoteName='clipforge'
    $remote=git remote get-url clipforge 2>$null
    if($remote -notmatch '^https://github\.com/Apelle333/clipforge(?:\.git)?$'){throw 'Updates require an official HTTPS origin/clipforge remote; no remote was changed.'}
}
Write-Host 'Stop CLIPFORGE before updating. Runtime data is outside the checkout.'
git pull --ff-only $remoteName main
if($LASTEXITCODE){throw 'Fast-forward update failed; no reset or force operation was used.'}
& "$PSScriptRoot\Install-CLIPFORGE.ps1" @PSBoundParameters
