# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[('.venv/Lib/site-packages/fmod_toolkit/libfmod/Windows/x64/fmod.dll', '.')],
    datas=[('.venv/Lib/site-packages/UnityPy/resources', 'UnityPy/resources'), ('.venv/Lib/site-packages/fmod_toolkit/libfmod', 'fmod_toolkit/libfmod'), ('.venv/Lib/site-packages/archspec/json', 'archspec/json')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='manosaba-character-export-cli-x64',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
