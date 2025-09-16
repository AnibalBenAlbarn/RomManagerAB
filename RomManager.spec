# -*- mode: python ; coding: utf-8 -*-

"""Spec de PyInstaller para generar el ejecutable de ROM Manager."""

from pathlib import Path

# Resolvemos rutas absolutas para que PyInstaller pueda localizar los recursos
# aunque se invoque desde otro directorio.
BASE_DIR = Path(__file__).resolve().parent
ICON_PATH = BASE_DIR / "resources" / "romMan.ico"

block_cipher = None


a = Analysis(
    ['rom_manager/main.py'],
    pathex=[str(BASE_DIR)],
    binaries=[],
    datas=[(str(ICON_PATH), 'resources')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RomManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RomManager',
)
