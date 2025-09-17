# -*- mode: python ; coding: utf-8 -*-

"""Spec de PyInstaller para generar el ejecutable de RomManager AB."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


def _resolve_base_dir() -> Path:
    """Obtiene el directorio base del proyecto.

    Cuando PyInstaller ejecuta el ``spec`` el nombre ``__file__`` no siempre
    está definido, por lo que calculamos la ruta a partir del directorio de
    trabajo actual como alternativa.
    """

    try:
        return Path(__file__).resolve().parent  # type: ignore[name-defined]
    except NameError:
        return Path.cwd()


# Resolvemos rutas absolutas para que PyInstaller pueda localizar los recursos
# aunque se invoque desde otro directorio.
BASE_DIR = _resolve_base_dir()
ICON_PATH = BASE_DIR / "resources" / "romMan.ico"

block_cipher = None


_py7zr_hidden = collect_submodules('py7zr')
# py7zr depende de módulos auxiliares que no siempre detecta PyInstaller.
# ``collect_submodules`` asegura que todo el soporte para 7z quede incluido
# en el ejecutable generado y evita errores en tiempo de ejecución al extraer
# archivos .7z.
_py7zr_hidden += collect_submodules('pybcj')
_py7zr_hidden += collect_submodules('pyppmd')

a = Analysis(
    ['rom_manager/main.py'],
    pathex=[str(BASE_DIR)],
    binaries=[],
    datas=[(str(ICON_PATH), 'resources')],
    hiddenimports=_py7zr_hidden,
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
