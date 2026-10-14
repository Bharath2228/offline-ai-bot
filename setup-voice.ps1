$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$chatPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $chatPython)) { throw 'Run Keep.cmd once first.' }
$voicePython = Join-Path $PSScriptRoot '.voice-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $voicePython)) {
    & $chatPython -m venv .voice-venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the voice runtime.' }
}
& $voicePython -m pip install -r requirements-voice.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install the voice libraries.' }
& $voicePython setup_voice_model.py
if ($LASTEXITCODE -ne 0) { throw 'Could not download the voice model.' }
$settingsKey = 'HKCU:\Software\Keep\KeepDesktop'
if (-not (Test-Path -LiteralPath $settingsKey)) { New-Item -Path $settingsKey | Out-Null }
New-ItemProperty -Path $settingsKey -Name voice_runtime_root -Value $PSScriptRoot -PropertyType String -Force | Out-Null
Write-Output 'Offline voice input is ready.'
