"""Utilidades para calcular rutas de almacenamiento de la aplicación.

Este módulo centraliza la lógica para determinar dónde debe guardar la
aplicación sus archivos de configuración, sesiones y logs. Al hacerlo se
facilita mantener una estructura consistente tanto en modo desarrollo como
cuando se ejecuta el ejecutable generado con PyInstaller.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Iterable


def _detect_app_root() -> Path:
    """Devuelve el directorio base donde se almacenarán los datos."""
    if getattr(sys, "frozen", False):  # Ejecutado desde un binario PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = _detect_app_root()
"""Directorio base para datos persistentes de la aplicación."""

LOG_DIR = APP_ROOT / "logs"
"""Carpeta para almacenar los archivos de log."""

CONFIG_DIR = APP_ROOT / "config"
"""Carpeta donde se ubican configuraciones en formato JSON."""

SESSIONS_DIR = APP_ROOT / "sessions"
"""Carpeta para archivos JSON de sesiones de descarga."""


def ensure_app_directories(extra: Iterable[Path] | None = None) -> None:
    """Crea las carpetas fundamentales de la aplicación si no existen."""
    for directory in (LOG_DIR, CONFIG_DIR, SESSIONS_DIR, *(extra or [])):
        directory.mkdir(parents=True, exist_ok=True)


def log_path(filename: str = "rom_manager.log") -> Path:
    """Ruta completa al fichero de log solicitado."""
    ensure_app_directories()
    return LOG_DIR / filename


def config_path(filename: str) -> Path:
    """Ruta completa a un fichero de configuración dentro de ``config``."""
    ensure_app_directories()
    return CONFIG_DIR / filename


def session_path(filename: str = "downloads_session.json") -> Path:
    """Ruta completa a un fichero de sesión dentro de ``sessions``."""
    ensure_app_directories()
    return SESSIONS_DIR / filename
