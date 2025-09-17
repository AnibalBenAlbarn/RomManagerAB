"""
Módulo de utilidades para el gestor de ROMs.

Actualmente contiene funciones auxiliares que se utilizan en distintas
partes de la aplicación, como la sanitización de nombres de archivo y la
extracción de archivos comprimidos con soporte para progreso.
"""

from __future__ import annotations

import importlib
import os
import sys
import shutil
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Callable, Optional


def safe_filename(name: str) -> str:
    """Sanitiza un nombre de archivo sustituyendo caracteres no válidos."""

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


_PY7ZR_MODULE: ModuleType | None = None
_PY7ZR_IMPORT_ERROR: BaseException | None = None
_PY7ZR_REQUIRED_MSG = (
    "py7zr es necesario para extraer archivos .7z. "
    "Instálalo con `pip install py7zr`."
)


def extract_archive(
    archive_path: str,
    dest_dir: str,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> None:

    """Descomprime ``archive_path`` en ``dest_dir``.

    Si se proporciona ``progress`` se llamará periódicamente con la cantidad
    de datos procesados, el total estimado y un texto de estado.
    Lanza :class:`RuntimeError` si la extracción no es posible o requiere
    contraseña.
    """

    path = Path(archive_path)
    if not path.exists():
        raise RuntimeError(f'El archivo {path} no existe')

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    base_root = dest.resolve()

    def emit(done: int, total: int, status: str) -> None:
        if progress:
            progress(int(done), int(total), status)

    def safe_target(name: str) -> Path:
        rel = Path(name)
        if rel.is_absolute():
            raise RuntimeError(f'Entrada con ruta no válida: {name}')
        resolved = (base_root / rel).resolve()
        if os.path.commonpath([str(base_root), str(resolved)]) != str(base_root):
            raise RuntimeError(f'Entrada con ruta no válida: {name}')
        return resolved

    try:
        if _is_7z_file(path):
            _extract_7z(path, base_root, emit)
        elif zipfile.is_zipfile(str(path)):
            _extract_zip(path, base_root, emit, safe_target)
        elif tarfile.is_tarfile(str(path)):
            _extract_tar(path, base_root, emit, safe_target)
        else:
            emit(0, 1, 'Extrayendo')
            shutil.unpack_archive(str(path), str(base_root))
            emit(1, 1, 'Extracción completada')
    except RuntimeError:
        raise
    except Exception as exc:  # pragma: no cover - depende de los datos de entrada
        raise RuntimeError(f'No se pudo descomprimir {path.name}: {exc}') from exc


def _py7zr_available() -> bool:
    global _PY7ZR_MODULE, _PY7ZR_IMPORT_ERROR

    if _PY7ZR_MODULE is not None:
        return True

    if _PY7ZR_IMPORT_ERROR is not None:
        return False

    try:
        _PY7ZR_MODULE = importlib.import_module("py7zr")
        return True
    except ModuleNotFoundError as exc:
        _PY7ZR_IMPORT_ERROR = exc
        return False
    except Exception as exc:  # pragma: no cover - depende del entorno
        _PY7ZR_IMPORT_ERROR = exc
        raise RuntimeError(f"No se pudo inicializar py7zr: {exc}") from exc


def _load_py7zr() -> ModuleType:
    global _PY7ZR_MODULE, _PY7ZR_IMPORT_ERROR

    if _PY7ZR_MODULE is not None:
        return _PY7ZR_MODULE

    if not _py7zr_available():
        raise RuntimeError(_PY7ZR_REQUIRED_MSG) from _PY7ZR_IMPORT_ERROR

    # _py7zr_available garantiza que _PY7ZR_MODULE no es None.
    assert _PY7ZR_MODULE is not None
    return _PY7ZR_MODULE


def _is_7z_file(path: Path) -> bool:
    suffix_is_7z = path.suffix.lower() == '.7z'

    if not _py7zr_available():
        if suffix_is_7z:
            raise RuntimeError(_PY7ZR_REQUIRED_MSG)
        return False

    py7zr = _load_py7zr()
    try:
        return bool(py7zr.is_7zfile(str(path)))
    except Exception:  # pragma: no cover - depende de py7zr y del archivo
        return suffix_is_7z


def _extract_7z(path: Path, dest: Path, emit: Callable[[int, int, str], None]) -> None:
    py7zr = _load_py7zr()

    with py7zr.SevenZipFile(path, 'r') as archive:
        infos = archive.list()
        files = [info for info in infos if not getattr(info, 'is_directory', False)]
        total = sum(max(0, int(getattr(info, 'uncompressed', 0) or 0)) for info in files)
        if total <= 0:
            total = max(len(files), 1)

        class _Callback(py7zr.callbacks.ExtractCallback):  # type: ignore[attr-defined]
            def __init__(self) -> None:
                self._done = 0
                self._total = max(int(total), 1)
                self._current = ''
                self._current_done = 0

            def report_start_preparation(self) -> None:
                emit(self._done, self._total, 'Preparando extracción')

            def report_start(self, processing_file_path, processing_bytes) -> None:  # type: ignore[override]
                self._current = processing_file_path or ''
                self._current_done = 0
                status = f'Extrayendo: {self._current}' if self._current else 'Extrayendo'
                emit(self._done, self._total, status)

            def report_update(self, decompressed_bytes) -> None:  # type: ignore[override]
                if decompressed_bytes:
                    self._current_done += int(decompressed_bytes)
                    self._done = min(self._total, self._done + int(decompressed_bytes))
                    status = f'Extrayendo: {self._current}' if self._current else 'Extrayendo'
                    emit(self._done, self._total, status)

            def report_end(self, processing_file_path, wrote_bytes) -> None:  # type: ignore[override]
                remaining = 0
                if wrote_bytes:
                    remaining = int(wrote_bytes) - self._current_done
                if remaining > 0:
                    self._done = min(self._total, self._done + remaining)
                status = f'Extrayendo: {processing_file_path}' if processing_file_path else 'Extrayendo'
                emit(self._done, self._total, status)

            def report_warning(self, message) -> None:  # type: ignore[override]
                emit(self._done, self._total, f'Aviso: {message}')

            def report_postprocess(self) -> None:  # type: ignore[override]
                emit(self._done, self._total, 'Finalizando')

        callback = _Callback()
        try:
            archive.extractall(path=dest, callback=callback)
        except py7zr.PasswordRequired as exc:  # pragma: no cover - depende del archivo
            raise RuntimeError('Se requiere contraseña para descomprimir este archivo .7z') from exc
        emit(total, total, 'Extracción completada')


def _extract_zip(
    path: Path,
    dest: Path,
    emit: Callable[[int, int, str], None],
    safe_target: Callable[[str], Path],
) -> None:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        files = [info for info in infos if not info.is_dir()]
        total = sum(max(0, int(info.file_size)) for info in files)
        if total <= 0:
            total = max(len(files), 1)
        done = 0
        emit(done, total, 'Preparando extracción')
        for info in infos:
            name = info.filename
            if info.is_dir():
                safe_target(name).mkdir(parents=True, exist_ok=True)
                continue
            target = safe_target(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with archive.open(info) as src, open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 256)
            except RuntimeError as exc:  # pragma: no cover - depende del archivo
                if 'password' in str(exc).lower():
                    raise RuntimeError('Se requiere contraseña para descomprimir este archivo .zip') from exc
                raise
            done += int(info.file_size or 0)
            status = f'Extrayendo: {name}' if name else 'Extrayendo'
            emit(done, total, status)
        emit(total, total, 'Extracción completada')


def _extract_tar(
    path: Path,
    dest: Path,
    emit: Callable[[int, int, str], None],
    safe_target: Callable[[str], Path],
) -> None:
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        files = [m for m in members if m.isfile()]
        total = sum(max(0, int(m.size)) for m in files)
        if total <= 0:
            total = max(len(files), 1)
        done = 0
        emit(done, total, 'Preparando extracción')
        for member in members:
            name = member.name
            target = safe_target(name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise RuntimeError(f'No se pudo extraer {name}')
                with extracted, open(target, 'wb') as dst:
                    shutil.copyfileobj(extracted, dst, length=1024 * 256)
                if member.mtime is not None:
                    try:
                        os.utime(target, (member.mtime, member.mtime))
                    except OSError:
                        pass
                if member.mode is not None:
                    try:
                        os.chmod(target, member.mode)
                    except PermissionError:
                        pass
                done += int(member.size or 0)
                status = f'Extrayendo: {name}' if name else 'Extrayendo'
                emit(done, total, status)
                continue
            # Enlaces u otros tipos especiales: delegar en tarfile tras validar ruta
            archive.extract(member, path=str(dest))
        emit(total, total, 'Extracción completada')
