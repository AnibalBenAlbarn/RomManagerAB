"""
Modelos de datos utilizados por la interfaz gráfica.

En este módulo se define el modelo de tabla para los resultados de búsqueda
de enlaces. Se separa en un módulo independiente para que el código de la
interfaz principal sea más conciso y modular.
"""

from typing import Optional, List
import sqlite3

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant


class LinksTableModel(QAbstractTableModel):
    """
    Modelo para mostrar los resultados de búsqueda en un QTableView.
    Extraído a un módulo separado para mejorar la legibilidad.
    """

    HEADERS = ["ROM", "Servidor", "Formato", "Tamaño", "Idiomas", "Etiqueta", "URL"]

    def __init__(self, rows: Optional[List[sqlite3.Row]] = None) -> None:
        super().__init__()
        self._rows = rows or []

    def setRows(self, rows: List[sqlite3.Row]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> QVariant:
        if not index.isValid():
            return QVariant()
        r = self._rows[index.row()]
        c = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return [
                r["rom_name"],
                r["server"] or '',
                r["fmt"] or '',
                r["size"] or '',
                r["langs"] or '',
                r["label"] or '',
                r["url"],
            ][c]
        if role == Qt.ItemDataRole.ToolTipRole:
            return r["url"]
        return QVariant()

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> QVariant:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return QVariant()

    def getRow(self, i: int) -> sqlite3.Row:
        return self._rows[i]
