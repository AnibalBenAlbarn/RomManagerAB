"""
Módulo de utilidades para el gestor de ROMs.

Actualmente contiene funciones auxiliares que se utilizan en distintas
partes de la aplicación, como la sanitización de nombres de archivo.
"""

from __future__ import annotations

import os
import sys
import shutil
from pathlib import Path


def safe_filename(name: str) -> str:
    """
    Sanitiza un nombre de archivo sustituyendo caracteres no válidos.
    Se utiliza para crear nombres de archivo seguros en diferentes
    sistemas operativos.

    :param name: Nombre de archivo original.
    :return: Nombre de archivo seguro, con caracteres problemáticos
        reemplazados por guiones bajos.
    """
    bad = '<>:"/\\|?*\n\r\t'
    return ''.join('_' if c in bad else c for c in name).strip()


def resource_path(relative_path: str) -> str:
    """Devuelve una ruta válida tanto en desarrollo como en ejecutables."""

    base_path: Path
    if hasattr(sys, "_MEIPASS"):
        base_path = Path(getattr(sys, "_MEIPASS"))  # type: ignore[attr-defined]
    else:
        base_path = Path(__file__).resolve().parent.parent
    return str((base_path / relative_path).resolve())


def extract_archive(archive_path: str, dest_dir: str) -> None:
    """Descomprime ``archive_path`` en ``dest_dir``.

    Se utiliza ``shutil.unpack_archive`` para formatos conocidos (zip, tar,
    etc.) y se recurre a :mod:`py7zr` cuando el archivo es ``.7z``. Lanza
    :class:`RuntimeError` si la extracción no es posible.
    """

    path = Path(archive_path)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    suffix = path.suffix.lower()
    if suffix == '.7z':
        try:
            import py7zr  # type: ignore import-not-found
        except ImportError as exc:  # pragma: no cover - dependencia opcional
            raise RuntimeError('py7zr es necesario para extraer archivos .7z') from exc
        with py7zr.SevenZipFile(path, 'r') as archive:
            archive.extractall(dest)
        return

    try:
        shutil.unpack_archive(str(path), str(dest))
    except shutil.ReadError as exc:  # pragma: no cover - depende de los datos
        raise RuntimeError(f'No se pudo descomprimir {path.name}: {exc}') from exc
