param([string]$Version='0.1.13')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$msi=Join-Path $projectRoot ('releases\PrismCompare-'+$Version+'-x64.msi')
$target=Join-Path $projectRoot ('validation\extract_'+$Version+'_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $target -Force | Out-Null
$commandKey='HKLM:\Software\Classes\*\shell\PrismCompare\command'
$before=if (Test-Path -LiteralPath $commandKey) { (Get-Item -LiteralPath $commandKey).GetValue('') } else { '' }
$process=Start-Process msiexec.exe -ArgumentList @('/a',('"'+$msi+'"'),'/qn',('TARGETDIR="'+$target+'"'),'/L*v',('"'+$target+'\extract.log"')) -WindowStyle Hidden -PassThru
$process.WaitForExit()
if ($process.ExitCode -ne 0) { throw "MSI extraction failed: $($process.ExitCode)" }
$executables=@(Get-ChildItem -LiteralPath $target -Filter PrismCompare.exe -Recurse)
if ($executables.Count -ne 1) { throw 'Expected one extracted application.' }
& scripts/test_packaged.ps1 -Executable $executables[0].FullName
& .venv/Scripts/python.exe tests/shell_smoke.py $executables[0].FullName
if ($LASTEXITCODE -ne 0) { throw 'Extracted program IPC test failed.' }
$after=if (Test-Path -LiteralPath $commandKey) { (Get-Item -LiteralPath $commandKey).GetValue('') } else { '' }
if ($before -ne $after) { throw 'Existing context menu changed unexpectedly.' }
@{ok=$true;version=$Version;checks=@('MSI payload extraction','packaged startup and four-image comparison','packaged context-menu IPC','existing installation unchanged')} | ConvertTo-Json | Set-Content (Join-Path $target 'result.json') -Encoding UTF8
Get-Content (Join-Path $target 'result.json')
