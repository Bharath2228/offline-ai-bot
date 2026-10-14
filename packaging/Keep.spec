# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from pathlib import Path
import PySide6

# SPECPATH is injected by PyInstaller: the directory containing this .spec file.
ROOT = Path(SPECPATH).resolve().parent
APP = ROOT / 'app'

datas = [(str(APP / 'image_worker.py'), '.'), (str(APP / 'voice_worker.py'), '.')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('httpx')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    [str(APP / 'main.py')],
    pathex=[str(APP)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Qt 6.11 requires a newer VC runtime than Python 3.13's bundled copy.
# Keep the root copy consistent with the runtime distributed with Qt.
qt_directory = Path(PySide6.__file__).parent
runtime_names = {'vcruntime140.dll', 'vcruntime140_1.dll'}
a.binaries = [(dest, str(qt_directory / dest.lower()) if dest.lower() in runtime_names else source, kind)
              for dest, source, kind in a.binaries]
# Qt uses the host Windows ICU API. A build sandbox may have a different
# ICU version; shipping that DLL can break Qt on the destination Windows.
a.binaries = [entry for entry in a.binaries
              if not (entry[0].lower().startswith('icu') and entry[0].lower().endswith('.dll'))]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Keep',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / 'qa' / 'keep.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Keep',
)
