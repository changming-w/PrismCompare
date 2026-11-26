$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$msi=Join-Path $projectRoot 'releases\PrismCompare-0.1.22-x64.msi'
$testRoot=Join-Path $projectRoot ('validation\msi_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
$installDir=Join-Path $testRoot 'installed'
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$keys=@('HKLM:\Software\Classes\*\shell\PrismCompare','HKLM:\Software\Classes\Directory\shell\PrismCompare')
foreach ($key in $keys) { if (Test-Path -LiteralPath $key) { throw 'An existing Prism Compare installation is present; do not overwrite it during tests.' } }
$installed=$false
try {
    $process=Start-Process msiexec.exe -ArgumentList @('/i',('"'+$msi+'"'),'/qn','/norestart',('INSTALLFOLDER="'+$installDir+'"'),'/L*v',('"'+$testRoot+'\install.log"')) -WindowStyle Hidden -PassThru
    $process.WaitForExit()
    if ($process.ExitCode -notin @(0,3010)) { throw "Install failed: $($process.ExitCode). See $testRoot\install.log" }
    $installed=$true
    foreach ($key in $keys) {
        $command=(Get-Item -LiteralPath ($key+'\command')).GetValue('')
        if ($command -ne ('"'+$installDir+'\PrismCompare.exe" --shell "%1"')) { throw "Unexpected context-menu command: $command" }
    }
    if (-not (Test-Path -LiteralPath ([Environment]::GetFolderPath('CommonDesktopDirectory')+'\Prism Compare.lnk'))) { throw 'Desktop shortcut missing.' }
    & scripts/test_packaged.ps1 -Executable (Join-Path $installDir 'PrismCompare.exe')
    & .venv/Scripts/python.exe tests/shell_smoke.py (Join-Path $installDir 'PrismCompare.exe')
    if ($LASTEXITCODE -ne 0) { throw 'Installed application IPC smoke failed.' }
} finally {
    if ($installed) {
        $process=Start-Process msiexec.exe -ArgumentList @('/x',('"'+$msi+'"'),'/qn','/norestart','/L*v',('"'+$testRoot+'\uninstall.log"')) -WindowStyle Hidden -PassThru
        $process.WaitForExit()
        if ($process.ExitCode -notin @(0,3010)) { throw "Uninstall failed: $($process.ExitCode)" }
    }
}
foreach ($key in $keys) { if (Test-Path -LiteralPath $key) { throw "Context menu left after uninstall: $key" } }
if (Test-Path -LiteralPath (Join-Path $installDir 'PrismCompare.exe')) { throw 'Executable left after uninstall.' }
if (Test-Path -LiteralPath ([Environment]::GetFolderPath('CommonDesktopDirectory')+'\Prism Compare.lnk')) { throw 'Desktop shortcut left after uninstall.' }
@{ok=$true;checks=@('install to custom directory','desktop shortcut','file and directory context menus','installed application cross-process IPC','uninstall removes executable and menu keys')} | ConvertTo-Json | Set-Content (Join-Path $testRoot 'result.json') -Encoding UTF8
Get-Content (Join-Path $testRoot 'result.json')
