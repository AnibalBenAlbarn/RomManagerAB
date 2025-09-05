"""
Punto de entrada independiente para la aplicación ROM Manager.

Este módulo crea y ejecuta la aplicación PyQt6 utilizando la clase
MainWindow definida en Descargador.py. Separar el punto de entrada
facilita la estructura del proyecto y permite importar la interfaz
gráfica sin ejecutar la aplicación de inmediato.
"""

import sys
from PyQt6.QtWidgets import QApplication
from .Descargador import MainWindow

def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
