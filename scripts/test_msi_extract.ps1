param([string]$Version='0.1.22')
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
$installer=New-Object -ComObject WindowsInstaller.Installer
$db=$installer.OpenDatabase($msi,0)
$view=$db.OpenView('SELECT `Key`, `Value` FROM `Registry`')
$view.Execute()
$registered=@{}
while($record=$view.Fetch()) { $registered[$record.StringData(1)]=$record.StringData(2) }
$view.Close()
foreach($kind in @('*','Directory')) {
    $key="Software\Classes\$kind\shell\PrismCompareNewWindow\command"
    if($registered[$key] -ne '"[INSTALLFOLDER]PrismCompare.exe" --shell-new "%1"') {
        throw "Missing or incorrect new-window verb: $key"
    }
}
& scripts/test_packaged.ps1 -Executable $executables[0].FullName
& .venv/Scripts/python.exe tests/shell_smoke.py $executables[0].FullName
if ($LASTEXITCODE -ne 0) { throw 'Extracted program IPC test failed.' }
$after=if (Test-Path -LiteralPath $commandKey) { (Get-Item -LiteralPath $commandKey).GetValue('') } else { '' }
if ($before -ne $after) { throw 'Existing context menu changed unexpectedly.' }
@{ok=$true;version=$Version;checks=@('MSI payload extraction','packaged startup and four-image comparison','packaged context-menu IPC','existing installation unchanged')} | ConvertTo-Json | Set-Content (Join-Path $target 'result.json') -Encoding UTF8
Get-Content (Join-Path $target 'result.json')
