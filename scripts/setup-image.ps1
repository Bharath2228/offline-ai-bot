$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$chatPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $chatPython)) { throw 'Run Keep.cmd once to set up the desktop runtime first.' }
$imagePython = Join-Path $root '.image-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $imagePython)) {
    & $chatPython -m venv .image-venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the image runtime.' }
}
& $imagePython -m pip install 'torch==2.14.0' 'torchvision' --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'Could not install the local image engine.' }
& $imagePython -m pip install -r requirements-image.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install the image libraries.' }
& $chatPython app\setup_image_model.py
if ($LASTEXITCODE -ne 0) { throw 'The image model download did not complete.' }
$settingsKey = 'HKCU:\Software\Keep\KeepDesktop'
if (-not (Test-Path -LiteralPath $settingsKey)) { New-Item -Path $settingsKey | Out-Null }
New-ItemProperty -Path $settingsKey -Name image_runtime_root -Value $root -PropertyType String -Force | Out-Null
Write-Output 'Stable Diffusion 1.5 is ready. Open Image studio in Keep.'
