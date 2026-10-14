$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Path qa -Force | Out-Null
& $python -c "from PySide6.QtWidgets import QApplication; from main import make_keep_icon; a=QApplication([]); assert make_keep_icon().pixmap(128,128).save('qa/keep.ico')"
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
& $python -m PyInstaller --clean --noconfirm Keep.spec
if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
