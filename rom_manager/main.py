"""Punto de entrada independiente para la aplicación RomManager AB.

Este módulo prepara la configuración de logging, captura excepciones no
controladas y crea la aplicación PyQt6 utilizando la clase ``MainWindow``
definida en :mod:`rom_manager.gui`. Separar el punto de entrada facilita la
estructura del proyecto y permite importar la interfaz gráfica sin ejecutar la
aplicación de inmediato.
"""

from __future__ import annotations

import os
import sys
import logging

from rom_manager.paths import ensure_app_directories, log_path
from rom_manager.utils import resource_path


def _setup_logging() -> None:
    """Configura el logging para consola y archivo ``logs/rom_manager.log``.

    Se establece un ``sys.excepthook`` personalizado para capturar cualquier
    excepción no manejada y registrarla, de modo que el programa no se cierre
    silenciosamente.
    """

    ensure_app_directories()
    log_file = log_path()
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            # Permitir que el usuario interrumpa la ejecución sin stacktrace
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.exception(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = handle_exception


def main() -> None:
    _setup_logging()
    from PyQt6.QtWidgets import QApplication  # Importar tras configurar logging
    from PyQt6.QtGui import QIcon
    from rom_manager.gui import MainWindow

    class Application(QApplication):
        """Subclase que captura excepciones en el bucle de eventos de Qt."""

        def notify(self, receiver, event):  # type: ignore[override]
            try:
                return super().notify(receiver, event)
            except Exception:  # pragma: no cover - solo para depuración
                logging.exception("Unhandled exception in Qt event loop")
                return False

    app = Application(sys.argv)
    icon_path = resource_path(os.path.join("resources", "romMan.ico"))
    if os.path.exists(icon_path):
        icon = QIcon(icon_path)
        if not icon.isNull():
            app.setWindowIcon(icon)
    win = MainWindow()
    if getattr(win, "console_mode_enabled", False):
        win.showFullScreen()
    else:
        win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
