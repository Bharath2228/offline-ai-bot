$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$python = Join-Path $root '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Path qa -Force | Out-Null
& $python -c "import sys; sys.path.insert(0, 'app'); from PySide6.QtWidgets import QApplication; from main import make_keep_icon; a=QApplication([]); assert make_keep_icon().pixmap(128,128).save('qa/keep.ico')"
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
& $python -m PyInstaller --clean --noconfirm --distpath (Join-Path $root 'dist') --workpath (Join-Path $root 'build') (Join-Path $PSScriptRoot 'Keep.spec')
if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
