$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run scripts\setup.ps1 first.' }
& $pythonExe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Core tests failed.' }
& $pythonExe scripts\make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
& $pythonExe -m PyInstaller --noconfirm PrismCompare.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Copy-Item -LiteralPath README.md -Destination dist\PrismCompare\README.md -Force
Copy-Item -LiteralPath docs\USER_GUIDE.md -Destination dist\PrismCompare\USER_GUIDE.md -Force
Copy-Item -LiteralPath THIRD_PARTY_NOTICES.md -Destination dist\PrismCompare\THIRD_PARTY_NOTICES.md -Force
& $pythonExe scripts\collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'License collection failed.' }
Write-Host 'Built: dist\PrismCompare\PrismCompare.exe. Distribute the entire PrismCompare directory.'
