"""
Punto de entrada independiente para la aplicación ROM Manager.

Este módulo crea y ejecuta la aplicación PyQt6 utilizando la clase
MainWindow definida en Descargador.py. Separar el punto de entrada
facilita la estructura del proyecto y permite importar la interfaz
gráfica sin ejecutar la aplicación de inmediato.
"""

import sys
import logging
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from .Descargador import MainWindow

def _handle_exception(exc_type, exc_value, exc_tb):
    """Muestra y registra excepciones no capturadas."""
    logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
    err = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        QMessageBox.critical(None, "Error", err)
    except Exception:
        pass


def main() -> None:
    sys.excepthook = _handle_exception
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
