param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$runtimeRoot = Split-Path -Parent $PSScriptRoot
$installDirectory = Join-Path $env:LOCALAPPDATA 'Programs\Keep'
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Keep.lnk'
$menuShortcut = Join-Path ([Environment]::GetFolderPath('Programs')) 'Keep.lnk'
$registryKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Keep'
if ($Uninstall) {
    $resolved = [IO.Path]::GetFullPath($installDirectory)
    $expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\Keep'))
    if ($resolved -ne $expected -or (Split-Path $resolved -Leaf) -ne 'Keep') { throw 'Unexpected installation path.' }
    Remove-Item -LiteralPath $desktopShortcut,$menuShortcut -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $registryKey) { Remove-Item -LiteralPath $registryKey }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
    exit
}
$source = Join-Path $runtimeRoot 'dist\Keep'
if (-not (Test-Path -LiteralPath (Join-Path $source 'Keep.exe'))) { throw 'Build Keep before installing.' }
New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
# Remove only obsolete ICU copies shipped by an earlier Keep build.
foreach ($obsolete in @('icuuc.dll', 'icudt78.dll')) {
    $obsoletePath = Join-Path $installDirectory ('_internal\' + $obsolete)
    if (Test-Path -LiteralPath $obsoletePath) { Remove-Item -LiteralPath $obsoletePath }
}
Copy-Item -Path (Join-Path $source '*') -Destination $installDirectory -Recurse -Force
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $installDirectory 'install.ps1') -Force
$shell = New-Object -ComObject WScript.Shell
foreach ($shortcutPath in @($desktopShortcut, $menuShortcut)) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $installDirectory 'Keep.exe'
    $shortcut.WorkingDirectory = $installDirectory
    $shortcut.Description = 'Keep - Private local AI'
    $shortcut.Save()
}
New-Item -Path $registryKey -Force | Out-Null
New-ItemProperty -Path $registryKey -Name DisplayName -Value 'Keep' -Force | Out-Null
New-ItemProperty -Path $registryKey -Name DisplayVersion -Value '1.4.1' -Force | Out-Null
New-ItemProperty -Path $registryKey -Name DisplayIcon -Value (Join-Path $installDirectory 'Keep.exe') -Force | Out-Null
New-ItemProperty -Path $registryKey -Name InstallLocation -Value $installDirectory -Force | Out-Null
$uninstallCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $installDirectory 'install.ps1') + '" -Uninstall'
New-ItemProperty -Path $registryKey -Name UninstallString -Value $uninstallCommand -Force | Out-Null
Write-Output "Keep installed in $installDirectory. Launch it from Start or your desktop."
$settingsKey = 'HKCU:\Software\Keep\KeepDesktop'
if (-not (Test-Path -LiteralPath $settingsKey)) {
    New-Item -Path $settingsKey | Out-Null
}
$imageRuntime = Join-Path $runtimeRoot '.image-venv\Scripts\python.exe'
if (Test-Path -LiteralPath $imageRuntime) {
    New-ItemProperty -Path $settingsKey -Name image_runtime_root -Value $runtimeRoot -PropertyType String -Force | Out-Null
    Write-Output "Image studio configured from $runtimeRoot."
} else {
    Write-Output "Image studio runtime not found at $imageRuntime."
}
$voiceRuntime = Join-Path $runtimeRoot '.voice-venv\Scripts\python.exe'
if (Test-Path -LiteralPath $voiceRuntime) {
    New-ItemProperty -Path $settingsKey -Name voice_runtime_root -Value $runtimeRoot -PropertyType String -Force | Out-Null
    Write-Output "Voice input configured from $runtimeRoot."
} else {
    Write-Output "Voice runtime not found at $voiceRuntime."
}
