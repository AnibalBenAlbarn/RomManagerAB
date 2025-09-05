"""
ROM Manager (PyQt6) — JavaFX Pane Layout Parity
================================================

Este módulo implementa una aplicación de escritorio en PyQt6 que replica la estructura
de “panes” de la interfaz Java original (JavaFX) para la gestión de ROMs y descargas.
Incluye las siguientes pestañas:

- **Base de datos**: permite seleccionar una base de datos SQLite y conectar para
  cargar los filtros de búsqueda (sistemas, idiomas y formatos).
- **Ajustes de descarga**: selecciona la carpeta de descargas, el número máximo de
  descargas simultáneas (de 1 a 5), opciones adicionales (crear carpetas por
  sistema, eliminar tras descomprimir) y la persistencia de sesión (guardar y
  cargar la lista de descargas).
- **Selector de ROMs**: buscador con filtros por texto, sistema, idioma y
  formato. Los resultados se muestran en una tabla; se pueden añadir a la
  cola de descargas mediante doble clic o un botón.
- **Descargas**: muestra la cola de descargas con su estado, progreso,
  velocidad, ETA y botones para pausar, reanudar o cancelar cada descarga.

La aplicación se basa en el esquema de bases de datos proporcionado (tabla
``systems``, ``roms``, ``links``, ``languages`` y relaciones) y utiliza
``requests`` para descargar los archivos. Las descargas se gestionan con
``QRunnable`` y un ``QThreadPool`` para permitir la ejecución concurrente.

Se incluye soporte para reanudación de descargas mediante archivos ``.part`` y
cabeceras HTTP ``Range``. Además, se aplican cabeceras “de navegador” y se
utiliza ``requests.Session`` con reintentos para mejorar el rendimiento en
servidores que aplican limitaciones al User-Agent o a las conexiones
persistentes.

Requisitos de instalación:

.. code-block:: bash

   pip install PyQt6 requests

Para ejecutar la aplicación directamente:

.. code-block:: bash

   python rom_manager.py

"""

from __future__ import annotations

import os
import sys
import time
import math
import json
import sqlite3
import threading
from dataclasses import dataclass
from typing import Optional, List, Tuple

import requests
import logging
from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QVariant, QObject, pyqtSignal, QRunnable,
    QThreadPool, QTimer, QSettings, QUrl, QEvent
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QGroupBox, QComboBox, QSpinBox,
    QTableView, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QProgressBar, QCheckBox, QTabWidget, QAbstractItemView
)

from PyQt6.QtWidgets import QMenu  # Importar QMenu para menú contextual

from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QStyle

# Configuración de logging para depuración. Los mensajes se muestran en consola y fichero.
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('rom_manager.log', mode='w', encoding='utf-8'),
    ],
)

# -----------------------------
# Utilidades
# -----------------------------

def safe_filename(name: str) -> str:
    """Sanitiza un nombre de archivo sustituyendo caracteres no válidos."""
    bad = '<>:"/\\|?*\n\r\t'
    return ''.join('_' if c in bad else c for c in name).strip()

# -----------------------------
# Acceso a BD
# -----------------------------

class Database:
    """
    Manejador de conexión SQLite para cargar filtros y buscar enlaces de descarga.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Abre la conexión a la base de datos si existe."""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"No existe la BD: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        """Cierra la conexión a la base de datos."""
        if self.conn:
            self.conn.close()
            self.conn = None

    # Cargas de filtros
    def get_systems(self) -> List[Tuple[Optional[int], str]]:
        """Devuelve la lista de sistemas disponibles para el filtro."""
        assert self.conn
        cur = self.conn.execute("SELECT id, name FROM systems ORDER BY name")
        return [(None, "Todos")] + [(r[0], r[1]) for r in cur.fetchall()]

    def get_languages(self) -> List[Tuple[Optional[int], str]]:
        """Devuelve la lista de idiomas disponibles para el filtro."""
        assert self.conn
        cur = self.conn.execute("SELECT id, code FROM languages ORDER BY code")
        return [(None, "Todos")] + [(r[0], r[1]) for r in cur.fetchall()]

    def get_formats(self) -> List[str]:
        """Devuelve la lista de formatos de archivo distintos disponibles."""
        assert self.conn
        cur = self.conn.execute(
            "SELECT DISTINCT fmt FROM links WHERE fmt IS NOT NULL AND TRIM(fmt)<>'' ORDER BY fmt"
        )
        return ["Todos"] + [r[0] for r in cur.fetchall()]

    def search_links(
        self,
        text: str = "",
        system_id: Optional[int] = None,
        language_id: Optional[int] = None,
        fmt: Optional[str] = None,
        limit: int = 1000,
    ) -> List[sqlite3.Row]:
        """
        Realiza una búsqueda de enlaces según el texto y filtros.
        Devuelve filas con información de ROM y link.
        """
        assert self.conn
        params: List = []
        where = ["1=1"]
        if text:
            where.append("(roms.name LIKE ? OR links.label LIKE ? OR links.server_name LIKE ?)")
            like = f"%{text}%"; params += [like, like, like]
        if system_id is not None:
            where.append("roms.system_id = ?"); params.append(system_id)
        if language_id is not None:
            where.append(
                "EXISTS (SELECT 1 FROM link_languages ll WHERE ll.link_id = links.id AND ll.language_id = ?)"
            ); params.append(language_id)
        if fmt is not None and fmt != "Todos":
            where.append("links.fmt = ?"); params.append(fmt)
        sql = f"""
        SELECT
            links.id            AS link_id,
            roms.id             AS rom_id,
            roms.name           AS rom_name,
            links.server_name   AS server,
            links.fmt           AS fmt,
            links.size          AS size,
            COALESCE(GROUP_CONCAT(languages.code, ','), links.languages) AS langs,
            links.url           AS url,
            links.label         AS label
        FROM links
        JOIN roms    ON roms.id = links.rom_id
        LEFT JOIN link_languages ON link_languages.link_id = links.id
        LEFT JOIN languages      ON languages.id = link_languages.language_id
        WHERE {" AND ".join(where)}
        GROUP BY links.id
        ORDER BY roms.name, links.id
        LIMIT ?
        """
        params.append(limit)
        cur = self.conn.execute(sql, params)
        return cur.fetchall()

# -----------------------------
# Modelo de tabla (resultados)
# -----------------------------

class LinksTableModel(QAbstractTableModel):
    """Modelo para mostrar los resultados de búsqueda en un QTableView."""
    HEADERS = ["ROM", "Servidor", "Formato", "Tamaño", "Idiomas", "Etiqueta", "URL"]
    def __init__(self, rows: Optional[List[sqlite3.Row]] = None):
        super().__init__()
        self._rows = rows or []
    def setRows(self, rows: List[sqlite3.Row]):
        self.beginResetModel(); self._rows = rows; self.endResetModel()
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

# -----------------------------
# Descarga con QRunnable
# -----------------------------

class DownloadSignals(QObject):
    """Conjunto de señales para notificar progreso, éxito y fallos durante la descarga."""
    progress = pyqtSignal(int, int, float, float, str)  # done, total, speed, eta, status
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

class DownloadTask(QRunnable):
    """
    Descargador optimizado usando QRunnable.
    Utiliza cabeceras de navegador, ``requests.Session`` con reintentos y
    reanudación mediante el uso de archivos ``.part`` y la cabecera Range.
    """
    def __init__(self, url: str, dest_dir: str, file_name: str, headers: Optional[dict] = None):
        super().__init__()
        self.url = url
        self.dest_dir = dest_dir
        self.file_name = file_name
        # Cabeceras “de navegador” por defecto
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://myrient.erista.me/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        self.signals = DownloadSignals()
        # Eventos para pausa y cancelación
        self._pause = threading.Event(); self._pause.set()
        self._cancel = False

    def pause(self) -> None:
        """Pausa la descarga."""
        self._pause.clear()

    def resume(self) -> None:
        """Reanuda la descarga."""
        self._pause.set()

    def cancel(self) -> None:
        """Cancela la descarga."""
        self._cancel = True
        self._pause.set()

    def run(self) -> None:
        """
        Ejecuta la descarga. Esta función se ejecuta en un hilo del ``QThreadPool``.
        Maneja reanudación, reintentos y notificaciones de progreso.
        """
        try:
            # Asegurar que la carpeta de destino exista
            os.makedirs(self.dest_dir, exist_ok=True)
            final_path = os.path.join(self.dest_dir, safe_filename(self.file_name))
            part_path = final_path + '.part'

            # Preparar cabeceras y calcular bytes descargados previamente
            headers = dict(self.headers)
            downloaded = 0
            if os.path.exists(part_path):
                downloaded = os.path.getsize(part_path)
                if downloaded > 0:
                    headers['Range'] = f'bytes={downloaded}-'

            # Crear sesión con pool de conexiones y reintentos
            session = requests.Session()
            try:
                from requests.adapters import HTTPAdapter
                from urllib3.util.retry import Retry
                retry = Retry(
                    total=3,
                    backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["HEAD", "GET"]
                )
                adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry)
                session.mount("http://", adapter)
                session.mount("https://", adapter)
            except Exception:
                # Si no se pueden aplicar reintentos, se utiliza la sesión por defecto
                pass

            # Intento HEAD para conocer el tamaño total
            total = 0
            try:
                h = session.head(self.url, headers=headers, allow_redirects=True, timeout=(10, 15))
                if h.status_code in (200, 206):
                    total = int(h.headers.get('Content-Length', '0'))
            except Exception:
                pass

            # Iniciar la descarga en streaming
            with session.get(self.url, headers=headers, stream=True, allow_redirects=True,
                              timeout=(10, 60)) as r:
                if r.status_code not in (200, 206):
                    self.signals.failed.emit(f"HTTP {r.status_code}")
                    return

                # Si el servidor no soporta range y enviamos Range, reiniciar el conteo
                if r.status_code == 200 and downloaded > 0:
                    downloaded = 0

                # Ajustar 'total' de bytes según los encabezados
                cl = r.headers.get('Content-Length')
                if cl is not None:
                    clen = int(cl)
                    if r.status_code == 206 and 'Range' in headers:
                        # 206: el servidor envía el tamaño de la franja solicitada. Sumar descargado previo
                        total = clen + downloaded if total == 0 else total
                    else:
                        total = clen
                if 'Content-Range' in r.headers and downloaded:
                    try:
                        total_all = int(r.headers['Content-Range'].split('/')[-1])
                        total = total_all
                    except Exception:
                        if total and total < downloaded:
                            total = downloaded

                # Tamaño del chunk: 512 KB para reducir overhead y mejorar rendimiento
                chunk_size = 1024 * 512
                last_t = time.time(); last_b = downloaded

                # Abrir archivo .part y escribir conforme se reciben datos
                with open(part_path, 'ab' if downloaded > 0 else 'wb') as f:
                    for data in r.iter_content(chunk_size=chunk_size):
                        # Cancelar descarga
                        if self._cancel:
                            self.signals.failed.emit('Cancelado')
                            return
                        # Pausa
                        self._pause.wait()
                        if not data:
                            continue
                        f.write(data)
                        downloaded += len(data)

                        # Calcular velocidad y ETA cada ~0.5 segundos
                        now = time.time(); dt = now - last_t
                        speed = 0.0; eta = math.inf
                        if dt >= 0.5:
                            delta = downloaded - last_b
                            speed = delta / dt
                            last_t = now
                            last_b = downloaded
                            if total and downloaded <= total and speed > 0:
                                eta = (total - downloaded) / speed
                        # Emitir progreso
                        self.signals.progress.emit(downloaded, total, float(speed), float(eta), 'Descargando')

            # Renombrar el archivo descargado correctamente
            if os.path.exists(final_path):
                try:
                    os.remove(final_path)
                except Exception:
                    pass
            os.replace(part_path, final_path)
            # Señalar finalización
            self.signals.progress.emit(downloaded, total, 0.0, 0.0, 'Completado')
            self.signals.finished_ok.emit(final_path)
        except Exception as e:
            # Notificar fallo
            self.signals.failed.emit(str(e))

# -----------------------------
# Gestor de cola
# -----------------------------

@dataclass
class DownloadItem:
    """Estructura que representa un elemento de la cola de descargas."""
    name: str
    url: str
    dest_dir: str
    task: Optional[DownloadTask] = None
    row: Optional[int] = None

class DownloadManager(QObject):
    """
    Administra la cola de descargas y controla cuántas están activas
    simultáneamente.
    """
    queue_changed = pyqtSignal()
    def __init__(self, pool: QThreadPool, max_concurrent: int = 3):
        super().__init__()
        self.pool = pool
        # Limitar el número de descargas concurrentes a 1–5
        self.max_concurrent = max(1, min(5, max_concurrent))
        self._queue: List[DownloadItem] = []
        self._active: List[DownloadItem] = []
    def set_max_concurrent(self, n: int) -> None:
        self.max_concurrent = max(1, min(5, int(n)))
        self.pump()
    def add(self, item: DownloadItem) -> None:
        self._queue.append(item)
        self.queue_changed.emit()
        self.pump()
    def remove(self, item: DownloadItem) -> None:
        """Saca un elemento de la cola o de la lista activa."""
        logging.debug(
            "Removing item from manager: %s (active=%s, queued=%s)",
            item.name,
            item in self._active,
            item in self._queue,
        )
        # Cancelar y retirar de la lista de activos si está en ejecución
        if item in self._active:
            logging.debug("Item %s is active; cancelling and removing from active list", item.name)
            if item.task:
                try:
                    item.task.cancel()
                except Exception:
                    logging.exception("Error cancelling task for %s", item.name)
            try:
                self._active.remove(item)
            except Exception:
                logging.exception("Error removing %s from active list", item.name)
        # Quitar de la cola si todavía estaba en espera
        if item in self._queue:
            logging.debug("Removing %s from queue", item.name)
            try:
                self._queue.remove(item)
            except Exception:
                logging.exception("Error removing %s from queue", item.name)
        else:
            logging.debug("%s not found in queue", item.name)
        self.queue_changed.emit()
        logging.debug("queue_changed emitted after removing %s", item.name)
        self.pump()
    def pump(self) -> None:
        # Lanza nuevas descargas hasta llenar el cupo de concurrencia
        while len(self._active) < self.max_concurrent and self._queue:
            it = self._queue.pop(0)
            self._active.append(it)
            self._start(it)
        self.queue_changed.emit()
    def _start(self, it: DownloadItem) -> None:
        # Crea un DownloadTask y conecta sus señales
        task = DownloadTask(it.url, it.dest_dir, it.name)
        it.task = task
        task.signals.finished_ok.connect(lambda path, i=it: self._on_done(i, True, path))
        task.signals.failed.connect(lambda msg, i=it: self._on_done(i, False, msg))
        self.pool.start(task)
    def _on_done(self, it: DownloadItem, ok: bool, msg: str) -> None:
        # Eliminar de la lista activa y continuar con la cola
        if it in self._active:
            self._active.remove(it)
        self.queue_changed.emit()
        self.pump()
    def pause(self, it: DownloadItem) -> None:
        if it.task:
            it.task.pause()
    def resume(self, it: DownloadItem) -> None:
        if it.task:
            it.task.resume()
    def cancel(self, it: DownloadItem) -> None:
        if it.task:
            logging.debug("Cancelling task for %s", it.name)
            try:
                it.task.cancel()
            except Exception:
                logging.exception("Error cancelling task for %s", it.name)
        else:
            logging.debug("Cancel requested for %s but no task present", it.name)

# -----------------------------
# Ventana principal con pestañas (paridad JavaFX)
# -----------------------------

class MainWindow(QMainWindow):
    """
    Ventana principal de la aplicación. Configura todas las pestañas y
    gestiona la interacción del usuario con la base de datos, el
    gestor de descargas y la visualización de resultados.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ROM Manager — Paridad JavaFX")
        self.resize(1200, 800)
        self.pool = QThreadPool.globalInstance()
        self.db: Optional[Database] = None
        self.session_file = ''

        # Preferencias del usuario
        # Flag para omitir la confirmación al cancelar descargas
        self.no_confirm_cancel: bool = False

        # Estado
        self.model = LinksTableModel([])
        self.manager = DownloadManager(self.pool, 3)
        self.manager.queue_changed.connect(self._refresh_downloads_table)
        self.items: List[DownloadItem] = []

        # Cesta de descargas (agrupa ROMs) y estructura de búsqueda
        # Es importante inicializar estos diccionarios antes de construir las pestañas,
        # ya que algunas pestañas (como el selector) pueden llamar a métodos que
        # dependen de ellos, como `_refresh_basket_table`.
        self.basket_items: dict[int, dict] = {}
        self.search_groups: dict[int, List[sqlite3.Row]] = {}

        # Tabs: mostrar primero el selector, luego descargas y finalmente ajustes
        tabs = QTabWidget(); self.setCentralWidget(tabs)
        # Crear contenedores para cada pestaña
        self.tab_selector = QWidget(); self.tab_downloads = QWidget(); self.tab_settings = QWidget()
        # Añadir pestañas en orden: Selector, Descargas, Ajustes
        tabs.addTab(self.tab_selector, "Selector de ROMs")
        tabs.addTab(self.tab_downloads, "Descargas")
        tabs.addTab(self.tab_settings, "Ajustes")

        # Construir las pestañas
        self._build_selector_tab()
        # La cesta se construirá dentro del selector, no como pestaña aparte
        self._build_downloads_tab()
        self._build_settings_tab()



        # Cargar configuración previa y restaurar estado
        self._load_config()

        # Si existe una ruta de BD guardada, conectar automáticamente
        db_path = self.le_db.text().strip()
        if db_path and os.path.exists(db_path):
            try:
                self._connect_db()
            except Exception:
                pass
        # Cargar cesta guardada después de conectar BD
        if getattr(self, '_saved_basket_json', None) and self.db:
            try:
                self._load_basket_from_saved()
            except Exception:
                pass
        # Cargar sesión de descargas de forma silenciosa
        try:
            self._load_session_silent()
        except Exception:
            pass
        logging.debug("MainWindow initialized. Tabs and settings loaded.")

    # --- Base de datos ---
    def _build_db_tab(self) -> None:
        lay = QVBoxLayout(self.tab_db)
        box = QGroupBox("Ruta de la base de datos"); g = QGridLayout(box)
        self.le_db = QLineEdit(); self.btn_db = QPushButton("Elegir…")
        self.btn_db.clicked.connect(self._choose_db)
        self.btn_connect = QPushButton("Conectar y cargar filtros")
        self.btn_connect.clicked.connect(self._connect_db)
        g.addWidget(QLabel("SQLite:"),0,0); g.addWidget(self.le_db,0,1); g.addWidget(self.btn_db,0,2)
        g.addWidget(self.btn_connect,1,2)
        lay.addWidget(box)

    # --- Ajustes de descarga ---
    def _build_dl_settings_tab(self) -> None:
        lay = QVBoxLayout(self.tab_dl_settings)
        box = QGroupBox("Carpeta de descargas y concurrencia"); g = QGridLayout(box)
        self.le_dir = QLineEdit(); self.btn_dir = QPushButton("Elegir…"); self.btn_dir.clicked.connect(self._choose_dir)
        self.spin_conc = QSpinBox(); self.spin_conc.setRange(1,5); self.spin_conc.setValue(3)
        self.spin_conc.valueChanged.connect(lambda v: self.manager.set_max_concurrent(v))
        self.chk_delete_after = QCheckBox("Eliminar archivo tras descompresión")
        self.chk_create_sys_dirs = QCheckBox("Crear carpetas por sistema")
        self.btn_recommended = QPushButton("Usar ajustes recomendados para máxima velocidad")
        self.btn_recommended.clicked.connect(lambda: (self.spin_conc.setValue(5)))
        g.addWidget(QLabel("Carpeta descargas:"),0,0); g.addWidget(self.le_dir,0,1); g.addWidget(self.btn_dir,0,2)
        g.addWidget(QLabel("Concurrencia (1–5):"),1,0); g.addWidget(self.spin_conc,1,1)
        g.addWidget(self.chk_delete_after,2,0,1,3)
        g.addWidget(self.chk_create_sys_dirs,3,0,1,3)
        g.addWidget(self.btn_recommended,4,0,1,3)
        lay.addWidget(box)
        # Persistencia de sesión
        sess = QGroupBox("Sesión de descargas"); h = QHBoxLayout(sess)
        self.btn_save_session = QPushButton("Guardar sesión")
        self.btn_load_session = QPushButton("Cargar sesión")
        self.btn_save_session.clicked.connect(self._save_session)
        self.btn_load_session.clicked.connect(self._load_session)
        h.addWidget(self.btn_save_session); h.addWidget(self.btn_load_session)
        lay.addWidget(sess)

    # --- Ajustes ---
    def _build_settings_tab(self) -> None:
        """
        Construye la pestaña de Ajustes que agrupa la configuración de la base de
        datos y las opciones de descarga en un único panel. Este método crea
        grupos de controles para la ruta de la base de datos, la ruta de
        descargas, la concurrencia y las preferencias de sesión.
        """
        lay = QVBoxLayout(self.tab_settings)
        logging.debug("Building settings tab with DB and download options.")
        # Grupo de configuración de base de datos
        gb_db = QGroupBox("Base de datos")
        grid_db = QGridLayout(gb_db)
        # Reutilizar widgets existentes para la BD
        # Entrada para ruta de la base de datos y botón para seleccionar
        self.le_db = QLineEdit(); self.btn_db = QPushButton("Elegir…")
        self.btn_db.clicked.connect(self._choose_db)
        self.btn_connect = QPushButton("Conectar y cargar filtros")
        self.btn_connect.clicked.connect(self._connect_db)
        grid_db.addWidget(QLabel("SQLite:"), 0, 0)
        grid_db.addWidget(self.le_db, 0, 1)
        grid_db.addWidget(self.btn_db, 0, 2)
        grid_db.addWidget(self.btn_connect, 1, 2)
        lay.addWidget(gb_db)

        # Grupo de configuración de descargas
        gb_dl = QGroupBox("Descargas")
        grid_dl = QGridLayout(gb_dl)
        self.le_dir = QLineEdit(); self.btn_dir = QPushButton("Elegir…")
        self.btn_dir.clicked.connect(self._choose_dir)
        self.spin_conc = QSpinBox(); self.spin_conc.setRange(1, 5); self.spin_conc.setValue(3)
        self.spin_conc.valueChanged.connect(lambda v: self.manager.set_max_concurrent(v))
        self.chk_delete_after = QCheckBox("Eliminar archivo tras descompresión")
        self.chk_create_sys_dirs = QCheckBox("Crear carpetas por sistema")
        self.btn_recommended = QPushButton("Usar ajustes recomendados para máxima velocidad")
        self.btn_recommended.clicked.connect(lambda: (self.spin_conc.setValue(5)))
        grid_dl.addWidget(QLabel("Carpeta descargas:"), 0, 0); grid_dl.addWidget(self.le_dir, 0, 1); grid_dl.addWidget(self.btn_dir, 0, 2)
        grid_dl.addWidget(QLabel("Concurrencia (1–5):"), 1, 0); grid_dl.addWidget(self.spin_conc, 1, 1)
        grid_dl.addWidget(self.chk_delete_after, 2, 0, 1, 3)
        grid_dl.addWidget(self.chk_create_sys_dirs, 3, 0, 1, 3)
        grid_dl.addWidget(self.btn_recommended, 4, 0, 1, 3)
        lay.addWidget(gb_dl)

        # Grupo de sesión de descargas
        gb_session = QGroupBox("Sesión de descargas")
        hbox_sess = QHBoxLayout(gb_session)
        self.btn_save_session = QPushButton("Guardar sesión")
        self.btn_load_session = QPushButton("Cargar sesión")
        self.btn_save_session.clicked.connect(self._save_session)
        self.btn_load_session.clicked.connect(self._load_session)
        hbox_sess.addWidget(self.btn_save_session)
        hbox_sess.addWidget(self.btn_load_session)
        lay.addWidget(gb_session)

    # --- Selector ROMs ---
    def _build_selector_tab(self) -> None:
        """
        Crea la pestaña de selector de ROMs. Esta versión agrupa los resultados de
        búsqueda por ROM y muestra una única fila por juego con listas
        desplegables para elegir servidor, formato e idioma. Debajo de los
        resultados se muestra la cesta actual para facilitar la gestión de
        descargas.
        """
        lay = QVBoxLayout(self.tab_selector)
        logging.debug("Building selector tab with search and basket tables.")

        # Grupo de filtros y búsqueda
        filters = QGroupBox("Búsqueda y filtros"); f = QGridLayout(filters)
        self.le_search = QLineEdit(); self.le_search.setPlaceholderText("Buscar por ROM/etiqueta/servidor…")
        self.cmb_system = QComboBox(); self.cmb_lang = QComboBox(); self.cmb_fmt = QComboBox()
        self.btn_search = QPushButton("Buscar"); self.btn_search.clicked.connect(self._run_search)
        f.addWidget(QLabel("Texto:"),0,0); f.addWidget(self.le_search,0,1)
        f.addWidget(QLabel("Sistema:"),1,0); f.addWidget(self.cmb_system,1,1)
        f.addWidget(QLabel("Idioma:"),2,0); f.addWidget(self.cmb_lang,2,1)
        f.addWidget(QLabel("Formato:"),3,0); f.addWidget(self.cmb_fmt,3,1)
        f.addWidget(self.btn_search,0,2,4,1)
        lay.addWidget(filters)

        # Tabla de resultados agrupados: columnas ROM, Servidor, Formato, Idiomas, Acciones
        self.table_results = QTableWidget(0, 5)
        self.table_results.setHorizontalHeaderLabels([
            "ROM", "Servidor", "Formato", "Idiomas", "Acciones"
        ])
        self.table_results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table_results)

        # Encabezado de la cesta y tabla de la cesta: se sitúan debajo de los resultados
        basket_label = QLabel("Cesta de descargas")
        basket_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        lay.addWidget(basket_label)
        self.table_basket = QTableWidget(0, 5)
        self.table_basket.setHorizontalHeaderLabels([
            "ROM", "Servidor", "Formato", "Idioma", "Acciones"
        ])
        self.table_basket.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table_basket)

        # Inicializar la cesta vacía
        self._refresh_basket_table()

    # --- Descargas ---
    def _build_downloads_tab(self) -> None:
        lay = QVBoxLayout(self.tab_downloads)
        logging.debug("Building downloads tab with progress table.")
        # Tabla con columnas: Nombre, Servidor, Formato, Tamaño, Estado, Progreso, Velocidad, ETA, Acciones
        self.table_dl = QTableWidget(0, 9)
        self.table_dl.setHorizontalHeaderLabels([
            "Nombre", "Servidor", "Formato", "Tamaño", "Estado", "Progreso", "Velocidad", "ETA", "Acciones"
        ])
        # Ajustar la anchura de las columnas de manera que la de acciones se adapte al contenido
        self.table_dl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_dl.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        # Permitir selección múltiple por fila y capturar tecla Suprimir
        self.table_dl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_dl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # Instalar event filter para detectar pulsación de Delete y habilitar menú contextual
        self.table_dl.installEventFilter(self)

        # Habilitar menú contextual personalizado para acciones de múltiples selecciones
        self.table_dl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_dl.customContextMenuRequested.connect(self._show_downloads_context_menu)
        lay.addWidget(self.table_dl)

    # --- Acciones UI ---
    def _choose_db(self) -> None:
        """Diálogo para seleccionar la base de datos SQLite."""
        fn, _ = QFileDialog.getOpenFileName(self, "Selecciona BD SQLite", "",
                                           "SQLite (*.db *.sqlite *.sqlite3);;Todos (*)")
        if fn:
            self.le_db.setText(fn)

    def _choose_dir(self) -> None:
        """Diálogo para seleccionar la carpeta de descargas."""
        d = QFileDialog.getExistingDirectory(self, "Carpeta de descargas")
        if d:
            self.le_dir.setText(d)
            self.session_file = os.path.join(d, 'downloads_session.json')

    def _connect_db(self) -> None:
        """Conecta a la base de datos y carga los filtros."""
        path = self.le_db.text().strip()
        if not path:
            QMessageBox.warning(self, "BD", "Indica la ruta de la base de datos.")
            return
        try:
            # Cerrar conexión anterior si existía
            if self.db:
                self.db.close()
            self.db = Database(path)
            self.db.connect()
            self._load_filters()
            QMessageBox.information(self, "BD", "Conectado y filtros cargados")
        except Exception as e:
            QMessageBox.critical(self, "Error BD", str(e))

    def _load_filters(self) -> None:
        """Carga los valores de los filtros (sistemas, idiomas, formatos) en los combobox."""
        assert self.db
        self.cmb_system.clear(); [self.cmb_system.addItem(n, i) for i,n in self.db.get_systems()]
        self.cmb_lang.clear();   [self.cmb_lang.addItem(c, i) for i,c in self.db.get_languages()]
        self.cmb_fmt.clear();    [self.cmb_fmt.addItem(x) for x in self.db.get_formats()]

    def _run_search(self) -> None:
        """
        Ejecuta la búsqueda en la base de datos según el texto y filtros seleccionados.
        Agrupa los resultados por ROM y construye la estructura de datos
        necesaria para poblar la tabla agrupada.
        """
        if not self.db:
            QMessageBox.warning(self, "BD", "Conecta la base de datos primero.")
            return
        text = self.le_search.text().strip()
        sys_id = self.cmb_system.currentData()
        lang_id = self.cmb_lang.currentData()
        fmt_val = self.cmb_fmt.currentText(); fmt = None if fmt_val == 'Todos' else fmt_val
        try:
            rows = self.db.search_links(text, sys_id, lang_id, fmt)
            logging.debug(f"Search returned {len(rows)} rows for '{text}' with filters system={sys_id}, lang={lang_id}, fmt={fmt}.")
        except Exception as e:
            logging.exception("Error during search: %s", e)
            QMessageBox.critical(self, "Búsqueda", str(e))
            return
        # Agrupar por rom_id
        groups: dict[int, dict] = {}
        for r in rows:
            rom_id = r["rom_id"]
            group = groups.setdefault(rom_id, {"name": r["rom_name"], "rows": []})
            group["rows"].append(r)
        # Para cada grupo, calcular listas de servidores, formatos y idiomas
        for rom_id, group in groups.items():
            rows_list = group["rows"]
            # Servidores únicos
            servers = sorted(set((row["server"] or "") for row in rows_list))
            # Diccionario: servidor -> lista de formatos únicos
            formats_by_server: dict[str, List[str]] = {}
            for srv in servers:
                fmts = sorted(set((row["fmt"] or "") for row in rows_list if (row["server"] or "") == srv))
                formats_by_server[srv] = fmts
            # Diccionario: (servidor, formato) -> lista de idiomas únicos (cadenas completas)
            langs_by_server_format: dict[tuple[str, str], List[str]] = {}
            for r in rows_list:
                srv = r["server"] or ""
                fmt_val = r["fmt"] or ""
                key = (srv, fmt_val)
                lang_str = r["langs"] or ""
                # Normalizar espacios y separar por coma
                lang_str = ','.join([x.strip() for x in lang_str.split(',') if x.strip()]) or ""
                lst = langs_by_server_format.setdefault(key, [])
                if lang_str not in lst:
                    lst.append(lang_str)
            # Ordenar cada lista de idiomas
            for key in langs_by_server_format:
                # mantener la cadena vacía (sin idiomas) al final
                lst = langs_by_server_format[key]
                lst.sort()
                langs_by_server_format[key] = lst
            # Diccionario de búsqueda: (servidor, formato, idiomas) -> fila
            link_lookup: dict[tuple[str, str, str], sqlite3.Row] = {}
            for r in rows_list:
                srv = r["server"] or ""
                fmt_val = r["fmt"] or ""
                lang_str = r["langs"] or ""
                lang_str = ','.join([x.strip() for x in lang_str.split(',') if x.strip()]) or ""
                link_lookup[(srv, fmt_val, lang_str)] = r
            group["servers"] = servers
            group["formats_by_server"] = formats_by_server
            group["langs_by_server_format"] = langs_by_server_format
            group["link_lookup"] = link_lookup
            group["selected_server"] = 0
            group["selected_format"] = 0
            group["selected_lang"] = 0
        self.search_groups = groups
        # Mostrar resultados agrupados
        self._display_grouped_results()

    def _enqueue_selected(self) -> None:
        """Añade las filas seleccionadas en la tabla de búsqueda a la cola de descargas."""
        save_dir = self.le_dir.text().strip()
        if not save_dir:
            QMessageBox.warning(self, "Descargas", "Selecciona una carpeta de descargas en la pestaña de Ajustes.")
            return
        indexes = self.table_links.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self, "Añadir", "No hay filas seleccionadas.")
            return
        for idx in indexes:
            r = self.model.getRow(idx.row())
            base = r["label"] or r["rom_name"] or os.path.basename(r["url"]) or "archivo.bin"
            name = safe_filename(base)
            item = DownloadItem(name=name, url=r["url"], dest_dir=save_dir)
            # Preparar un diccionario para mostrar el nombre de la ROM en la tabla
            row_data = {
                'server': r['server'] or '',
                'fmt': r['fmt'] or '',
                'size': r['size'] or '',
                'display_name': r['rom_name'] or base,
                'rom_name': r['rom_name'] or base,
            }
            self._add_download_row(item, row_data)  # type: ignore[arg-type]
            self.manager.add(item)
            self.items.append(item)

    def _add_download_row(self, item: DownloadItem, src_row: sqlite3.Row) -> None:
        """
        Inserta una nueva fila en la tabla de descargas para el item dado. Configura
        los botones de pausa, reanudación y cancelación y enlaza las señales del
        ``DownloadTask`` cuando esté disponible.
        """
        row = self.table_dl.rowCount(); self.table_dl.insertRow(row); item.row = row
        logging.debug("Adding download row: item=%s, dest_dir=%s", item.name, item.dest_dir)
        def set_item(c: int, text: str) -> None:
            self.table_dl.setItem(row, c, QTableWidgetItem(text))
        # Mostrar el nombre de la ROM si se proporciona; en su defecto usar el nombre del archivo
        display_name = None
        # src_row puede ser sqlite3.Row o un dict
        try:
            if isinstance(src_row, dict) and 'display_name' in src_row:
                display_name = src_row['display_name']
            elif isinstance(src_row, dict) and 'rom_name' in src_row:
                display_name = src_row['rom_name']
            elif hasattr(src_row, '__getitem__'):
                # Intentar obtener 'rom_name' de una Row
                display_name = src_row.get('rom_name') if hasattr(src_row, 'get') else None
        except Exception:
            display_name = None
        if not display_name:
            display_name = item.name
        set_item(0, display_name)
        # Servidor, formato y tamaño
        # src_row puede ser dict o Row; utilizar get si es dict
        server = ''
        fmt = ''
        size = ''
        if isinstance(src_row, dict):
            server = src_row.get('server', '') or ''
            fmt = src_row.get('fmt', '') or ''
            size = src_row.get('size', '') or ''
        elif hasattr(src_row, '__getitem__'):
            try:
                server = src_row["server"] or ''
                fmt = src_row["fmt"] or ''
                size = src_row["size"] or ''
            except Exception:
                pass
        set_item(1, server)
        set_item(2, fmt)
        set_item(3, size)
        set_item(4, "En cola")
        prog = QProgressBar(); prog.setRange(0, 100); prog.setValue(0); self.table_dl.setCellWidget(row, 5, prog)
        set_item(6, '-')
        set_item(7, '-')
        # Acciones: añadir botones de Pausar, Reanudar, Cancelar, Eliminar y Abrir
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
        # Crear botones con iconos para una mejor distinción visual
        b_pause = QPushButton()
        b_res = QPushButton()
        b_can = QPushButton()
        b_del = QPushButton()
        b_open = QPushButton()
        style = QApplication.style()
        try:
            b_pause.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPause))
            b_res.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            b_can.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
            # Algunas distribuciones pueden no tener SP_TrashIcon, así que usar un ícono alternativo si es necesario
            try:
                b_del.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
            except Exception:
                b_del.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
            b_open.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        except Exception as e:
            logging.exception("Error setting button icons: %s", e)
        # Establecer tooltips para cada botón
        b_pause.setToolTip("Pausar descarga")
        b_res.setToolTip("Reanudar descarga")
        b_can.setToolTip("Cancelar descarga")
        b_del.setToolTip("Eliminar descarga")
        b_open.setToolTip("Abrir ubicación")
        # Añadir botones al layout
        h.addWidget(b_pause); h.addWidget(b_res); h.addWidget(b_can)
        h.addWidget(b_del); h.addWidget(b_open)
        self.table_dl.setCellWidget(row, 8, w)
        # Conectar señales a acciones apropiadas
        b_pause.clicked.connect(lambda _=False, it=item: self.manager.pause(it))
        b_res.clicked.connect(lambda _=False, it=item: self.manager.resume(it))
        b_can.clicked.connect(lambda _=False, it=item: self._cancel_item(it))
        b_del.clicked.connect(lambda _=False, it=item: self._delete_single_item(it))
        b_open.clicked.connect(lambda _=False, it=item: self._open_item_location(it))
        # Esperar a que el task esté creado y enlazar señales
        tmr = QTimer(self); tmr.setInterval(200)
        def bind() -> None:
            if item.task is not None:
                item.task.signals.progress.connect(
                    lambda d, t, s, eta, st, it=item: self._update_progress(it, d, t, s, eta, st)
                )
                item.task.signals.finished_ok.connect(
                    lambda p, it=item: self._on_done(it, True, p)
                )
                item.task.signals.failed.connect(
                    lambda m, it=item: self._on_done(it, False, m)
                )
                tmr.stop()
        tmr.timeout.connect(bind); tmr.start()

    def _update_progress(self, it: DownloadItem, done: int, total: int, speed: float, eta: float, status: str) -> None:
        """Actualiza la fila de la tabla de descargas con los valores recibidos."""
        # Comprobar que la fila sigue siendo válida
        if it.row is None or it.row < 0 or it.row >= self.table_dl.rowCount():
            return
        logging.debug("Update progress: %s done=%d total=%d speed=%.2f eta=%.2f status=%s", it.name, done, total, speed, eta, status)
        row = it.row
        # Estado
        self.table_dl.item(row, 4).setText(status)
        # Progreso
        prog: QProgressBar = self.table_dl.cellWidget(row, 5)  # type: ignore
        percent = int(min(100, max(0, round(done * 100 / total)))) if total > 0 else 0
        prog.setValue(percent)
        # Velocidad y ETA
        self.table_dl.item(row, 6).setText(self._human_size(speed) + '/s' if speed > 0 else '-')
        self.table_dl.item(row, 7).setText(self._fmt_eta(eta) if math.isfinite(eta) and eta > 0 else '-')

    def _on_done(self, it: DownloadItem, ok: bool, msg: str) -> None:
        """Marca la descarga como completada o con error."""
        # Verificar que la fila sea válida antes de actualizar
        if it.row is None or it.row < 0 or it.row >= self.table_dl.rowCount():
            return
        self.table_dl.item(it.row, 4).setText("Completado" if ok else f"Error: {msg}")
        logging.debug("Download finished for %s: ok=%s, msg=%s", it.name, ok, msg)

    def _cancel_item(self, it: DownloadItem) -> None:
        """
        Maneja la cancelación de un elemento de la cola. Si el usuario tiene
        activada la opción de no confirmar, se cancela directamente. De lo
        contrario se muestra un cuadro de diálogo preguntando si desea
        cancelar con un checkbox para recordar la elección.
        """
        try:
            # Si ya se ha solicitado no confirmar, cancelar sin preguntar
            logging.debug("Attempting to cancel download: %s", it.name)
            if self.no_confirm_cancel:
                logging.debug("Cancellation confirmation disabled; cancelling %s directly", it.name)
                self.manager.cancel(it)
                logging.debug("Cancel signal sent for %s", it.name)
                if it.row is not None and 0 <= it.row < self.table_dl.rowCount():
                    self.table_dl.item(it.row, 4).setText("Cancelado")
                return
            # Mostrar diálogo de confirmación
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("Cancelar descarga")
            msg_box.setText("¿Seguro que quieres cancelar la descarga?")
            # Añadir checkbox para no volver a preguntar
            chk = QCheckBox("No volver a preguntar")
            msg_box.setCheckBox(chk)
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)
            res = msg_box.exec()
            logging.debug("Cancellation dialog result for %s: %s", it.name, res)
            if res == QMessageBox.Yes:
                # Actualizar preferencia si el usuario marcó no preguntar
                if chk.isChecked():
                    self.no_confirm_cancel = True
                    logging.debug("User opted to skip future cancel confirmations")
                # Cancelar la descarga
                self.manager.cancel(it)
                logging.debug("Cancel signal sent for %s after confirmation", it.name)
                if it.row is not None and 0 <= it.row < self.table_dl.rowCount():
                    self.table_dl.item(it.row, 4).setText("Cancelado")
            # Guardar preferencia de cancelación
            self._save_config()
        except Exception:
            logging.exception("Error cancelling download %s", it.name)
            try:
                QMessageBox.critical(self, "Error", f"No se pudo cancelar la descarga: {it.name}")
            except Exception:
                pass

    def _open_item_location(self, it: DownloadItem) -> None:
        """Abre la carpeta que contiene el archivo descargado o en descarga."""
        # Construir la ruta final (sin extensión parcial)
        dest_dir = it.dest_dir
        # Intentar obtener el nombre original sin sanitizar
        filename = safe_filename(it.name)
        final_path = os.path.join(dest_dir, filename)
        # Si existe un archivo parcial, se abrirá la carpeta de destino igualmente
        dir_path = os.path.dirname(final_path)
        if not os.path.isdir(dir_path):
            dir_path = dest_dir
        logging.debug("Opening location for %s: %s", it.name, dir_path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(dir_path))

    def _delete_single_item(self, it: DownloadItem) -> None:
        """
        Elimina un único elemento de la tabla de descargas y de la cola. Se
        muestra un cuadro de diálogo para confirmar la operación y opcionalmente
        borrar el fichero descargado.
        """
        try:
            logging.debug(
                "Requesting deletion for single download: %s (row=%s, dest=%s, has_task=%s)",
                it.name,
                it.row,
                it.dest_dir,
                it.task is not None,
            )
            # Dialogo de confirmación
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("Eliminar descarga")
            msg_box.setText("¿Seguro que quieres eliminar esta descarga?")
            chk_del_file = QCheckBox("También eliminar el fichero (si existe)")
            msg_box.setCheckBox(chk_del_file)
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)
            res = msg_box.exec()
            if res != QMessageBox.Yes:
                logging.debug("Deletion canceled by user for %s", it.name)
                return
            # Cancelar cualquier descarga en curso y quitar de la cola
            logging.debug("Deleting item: %s. Delete file: %s", it.name, chk_del_file.isChecked())
            # Cancelar y desconectar señales para evitar actualizaciones concurrentes
            try:
                self.manager.remove(it)
                logging.debug("Removed item from manager: %s", it.name)
            except Exception:
                logging.exception("Error removing item from manager: %s", it.name)
            # Desconectar señales del task para evitar actualizaciones después de eliminar

            if it.task is not None:
                try:
                    it.task.signals.progress.disconnect()
                except Exception:
                    logging.exception(
                        "Error disconnecting progress signal for %s", it.name
                    )
                try:
                    it.task.signals.finished_ok.disconnect()
                except Exception:
                    logging.exception(
                        "Error disconnecting finished_ok signal for %s", it.name
                    )

                try:
                    it.task.signals.failed.disconnect()
                except Exception:
                    logging.exception("Error disconnecting failed signal for %s", it.name)
                it.task = None
            # Eliminar fila de la tabla
            if it.row is not None:
                row = it.row
                logging.debug("Removing table row %s for %s", row, it.name)

                try:
                    self.table_dl.removeRow(row)
                except Exception:
                    logging.exception("Error removing row %s for %s", row, it.name)
                # Actualizar las filas de los items restantes
                for other in self.items:
                    if other.row is not None and other.row > row:
                        other.row -= 1
                # Marcar la fila del item eliminado como None para evitar actualizaciones posteriores
                it.row = None
            # Quitar de la lista de items
            if it in self.items:
                self.items.remove(it)
                logging.debug("Removed %s from internal items list", it.name)
            # Eliminar archivos si procede
            if chk_del_file.isChecked():
                try:
                    dest_dir = it.dest_dir
                    filename = safe_filename(it.name)
                    final_path = os.path.join(dest_dir, filename)
                    part_path = final_path + '.part'
                    # Eliminar archivo final
                    if os.path.exists(final_path):
                        os.remove(final_path)
                    # Eliminar archivo parcial
                    if os.path.exists(part_path):
                        os.remove(part_path)
                    logging.debug("Deleted files for %s", it.name)
                except Exception:
                    logging.exception("Error deleting files for %s", it.name)

            # Guardar sesión después de eliminar
            logging.debug("Saving session after deleting %s", it.name)
            self._save_session_silent()
            logging.debug("Session saved after deleting %s", it.name)
        except Exception:
            logging.exception("Error deleting download %s", it.name)
            try:
                QMessageBox.critical(self, "Error", f"No se pudo eliminar la descarga: {it.name}")
            except Exception:
                pass

    def _delete_selected_items(self) -> None:
        """Elimina todas las filas seleccionadas en la tabla de descargas."""
        try:
            # Obtener índices de filas seleccionadas
            selected_rows = sorted([idx.row() for idx in self.table_dl.selectionModel().selectedRows()])
            logging.debug("Rows selected for deletion: %s", selected_rows)
            if not selected_rows:
                logging.debug("No rows selected for deletion")
                return
            # Mapear filas a DownloadItem
            items_to_delete: List[DownloadItem] = []
            for it in list(self.items):
                if it.row in selected_rows:
                    items_to_delete.append(it)
            if not items_to_delete:
                return
            logging.debug("Requesting deletion for %d selected downloads", len(items_to_delete))
            # Preguntar confirmación para múltiples elementos
            if len(items_to_delete) == 1:
                self._delete_single_item(items_to_delete[0])
                return
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setWindowTitle("Eliminar descargas")
            msg_box.setText("¿Seguro que quieres eliminar las descargas seleccionadas?")
            chk_del_file = QCheckBox("También eliminar los ficheros (si existen)")
            msg_box.setCheckBox(chk_del_file)
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)
            res = msg_box.exec()
            if res != QMessageBox.Yes:
                logging.debug("Batch deletion canceled by user")
                return
            # Eliminar cada item
            # Procesar de mayor a menor índice para evitar problemas al actualizar filas
            for it in sorted(items_to_delete, key=lambda x: x.row if x.row is not None else -1, reverse=True):
                logging.debug("Deleting item in batch: %s", it.name)
                # Cancelar y remover de la cola
                try:
                    self.manager.remove(it)
                except Exception:
                    logging.exception("Error removing %s from manager during batch delete", it.name)
                # Desconectar señales del task para evitar actualizaciones tras la eliminación
                if it.task is not None:
                    try:
                        it.task.signals.progress.disconnect()
                    except Exception:
                        logging.exception("Error disconnecting progress signal for %s", it.name)
                    try:
                        it.task.signals.finished_ok.disconnect()
                    except Exception:
                        logging.exception("Error disconnecting finished_ok signal for %s", it.name)
                    try:
                        it.task.signals.failed.disconnect()
                    except Exception:
                        logging.exception("Error disconnecting failed signal for %s", it.name)
                    it.task = None
                # Eliminar fila de la tabla y ajustar índices
                if it.row is not None:
                    row_index = it.row
                    logging.debug("Removing table row %s for %s", row_index, it.name)
                    try:
                        self.table_dl.removeRow(row_index)
                    except Exception:
                        logging.exception("Error removing row %s for %s", row_index, it.name)
                    # Actualizar filas de items restantes
                    for other in self.items:
                        if other.row is not None and other.row > row_index:
                            other.row -= 1
                    # Marcar la fila del item eliminado como None para evitar actualizaciones posteriores
                    it.row = None
                # Quitar de la lista de items
                if it in self.items:
                    self.items.remove(it)
                    logging.debug("Removed %s from internal items list", it.name)
                # Eliminar archivos si procede
                if chk_del_file.isChecked():
                    try:
                        dest_dir = it.dest_dir
                        filename = safe_filename(it.name)
                        final_path = os.path.join(dest_dir, filename)
                        part_path = final_path + '.part'
                        if os.path.exists(final_path):
                            os.remove(final_path)
                        if os.path.exists(part_path):
                            os.remove(part_path)
                        logging.debug("Deleted files for %s", it.name)
                    except Exception:
                        logging.exception("Error deleting files for %s", it.name)
            # Guardar sesión tras eliminación múltiple
            logging.debug("Saving session after batch deletion of %d items", len(items_to_delete))
            self._save_session_silent()
            logging.debug("Session saved after batch deletion")
        except Exception:
            logging.exception("Error deleting selected downloads")
            try:
                QMessageBox.critical(self, "Error", "No se pudieron eliminar las descargas seleccionadas")
            except Exception:
                pass

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """
        Intercepta eventos del teclado para la tabla de descargas. Si se
        presiona la tecla Suprimir (Delete) se eliminan las descargas
        seleccionadas.
        """
        if obj is self.table_dl and event.type() == QEvent.Type.KeyPress:
            from PyQt6.QtGui import QKeyEvent
            key_event = event  # type: QKeyEvent
            if key_event.key() == Qt.Key.Key_Delete:
                logging.debug("Delete key pressed on downloads table.")
                self._delete_selected_items()
                return True
        return super().eventFilter(obj, event)

    # --- Menú contextual para la tabla de descargas ---
    def _show_downloads_context_menu(self, pos) -> None:
        """
        Muestra un menú contextual al hacer clic derecho en la tabla de descargas.
        Las acciones se aplican a todas las filas seleccionadas (o a la fila clicada
        si no había selección previa).
        """
        try:
            # Determinar la fila bajo el cursor
            index = self.table_dl.indexAt(pos)
            # Si no hay filas seleccionadas o la fila bajo el cursor no está seleccionada,
            # seleccionar esa fila antes de mostrar el menú
            selected = self.table_dl.selectionModel().selectedRows()
            if not selected or (index.isValid() and index.row() not in [r.row() for r in selected]):
                if index.isValid():
                    self.table_dl.selectRow(index.row())
                    selected = [index]
            if not selected:
                return
            # Crear menú y acciones con iconos
            menu = QMenu(self)
            # Iconos estándar para las acciones
            style = self.style()
            act_pause = menu.addAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaPause), "Pausar")
            act_resume = menu.addAction(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "Reanudar")
            act_cancel = menu.addAction(style.standardIcon(QStyle.StandardPixmap.SP_BrowserStop), "Cancelar")
            act_delete = menu.addAction(style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon), "Eliminar")
            act_open = menu.addAction(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon), "Abrir ubicación")
            # Conectar señales
            act_pause.triggered.connect(self._pause_selected_downloads)
            act_resume.triggered.connect(self._resume_selected_downloads)
            act_cancel.triggered.connect(self._cancel_selected_downloads)
            act_delete.triggered.connect(self._delete_selected_items)
            act_open.triggered.connect(self._open_selected_locations)
            # Mostrar el menú
            global_pos = self.table_dl.viewport().mapToGlobal(pos)
            menu.exec(global_pos)
        except Exception:
            logging.exception("Error showing context menu")

    def _get_selected_download_items(self) -> List[DownloadItem]:
        """Devuelve una lista de DownloadItem para las filas actualmente seleccionadas."""
        selected_rows = [idx.row() for idx in self.table_dl.selectionModel().selectedRows()]
        items = []
        for it in list(self.items):
            if it.row in selected_rows:
                items.append(it)
        return items

    def _pause_selected_downloads(self) -> None:
        """Pausa todas las descargas seleccionadas."""
        try:
            items = self._get_selected_download_items()
            for it in items:
                self.manager.pause(it)
                # Actualizar estado
                if it.row is not None and 0 <= it.row < self.table_dl.rowCount():
                    self.table_dl.item(it.row, 4).setText("Pausado")
            logging.debug("Paused %d downloads", len(items))
        except Exception:
            logging.exception("Error pausing selected downloads")

    def _resume_selected_downloads(self) -> None:
        """Reanuda todas las descargas seleccionadas."""
        try:
            items = self._get_selected_download_items()
            for it in items:
                self.manager.resume(it)
                # Actualizar estado
                if it.row is not None and 0 <= it.row < self.table_dl.rowCount():
                    self.table_dl.item(it.row, 4).setText("Descargando")
            logging.debug("Resumed %d downloads", len(items))
        except Exception:
            logging.exception("Error resuming selected downloads")

    def _cancel_selected_downloads(self) -> None:
        """
        Cancela todas las descargas seleccionadas. Si está habilitada la
        preferencia de no confirmar, se cancela directamente. En caso contrario
        se muestra una confirmación única para todas las descargas.
        """
        try:
            items = self._get_selected_download_items()
            if not items:
                return
            # Si no se confirma la cancelación, cancelar todas directamente
            if self.no_confirm_cancel:
                for it in items:
                    self.manager.cancel(it)
                    if it.row is not None and 0 <= it.row < self.table_dl.rowCount():
                        self.table_dl.item(it.row, 4).setText("Cancelado")
                logging.debug("Cancelled %d downloads without confirmation", len(items))
                return
            # Mostrar diálogo de confirmación para múltiples descargas
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("Cancelar descargas")
            if len(items) == 1:
                msg_box.setText("¿Seguro que quieres cancelar la descarga seleccionada?")
            else:
                msg_box.setText("¿Seguro que quieres cancelar las descargas seleccionadas?")
            chk = QCheckBox("No volver a preguntar")
            msg_box.setCheckBox(chk)
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)
            res = msg_box.exec()
            if res == QMessageBox.Yes:
                if chk.isChecked():
                    self.no_confirm_cancel = True
                for it in items:
                    self.manager.cancel(it)
                    if it.row is not None and 0 <= it.row < self.table_dl.rowCount():
                        self.table_dl.item(it.row, 4).setText("Cancelado")
                # Guardar preferencia
                self._save_config()
            else:
                logging.debug("User cancelled cancellation for %d downloads", len(items))
        except Exception:
            logging.exception("Error cancelling selected downloads")

    def _open_selected_locations(self) -> None:
        """Abre la carpeta de destino para todas las descargas seleccionadas."""
        try:
            items = self._get_selected_download_items()
            for it in items:
                self._open_item_location(it)
            logging.debug("Opened location for %d downloads", len(items))
        except Exception:
            logging.exception("Error opening locations for selected downloads")

    def _refresh_downloads_table(self) -> None:
        """Este slot se puede usar para actualizar contadores globales si fuera necesario."""
        pass

    # --- Persistencia de sesión (Ajustes de descarga) ---
    def _session_path(self) -> str:
        """Devuelve la ruta del fichero de sesión en la carpeta de descargas."""
        base = self.le_dir.text().strip() or os.getcwd()
        return os.path.join(base, 'downloads_session.json')

    def _save_session(self) -> None:
        """Guarda la sesión actual de descargas a disco."""
        data = [{"name": it.name, "url": it.url, "dest": it.dest_dir} for it in self.items]
        try:
            with open(self._session_path(), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, 'Sesión', 'Sesión guardada')
        except Exception as e:
            QMessageBox.critical(self, 'Sesión', str(e))

    def _load_session(self) -> None:
        """Carga la sesión previamente guardada y restaura la cola de descargas."""
        try:
            path = self._session_path()
            if not os.path.exists(path):
                QMessageBox.information(self, 'Sesión', 'No hay sesión para cargar')
                return
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for d in data:
                name = d.get('name'); url = d.get('url'); dest_dir = d.get('dest') or self.le_dir.text().strip()
                if not (name and url and dest_dir):
                    continue
                it = DownloadItem(name=name, url=url, dest_dir=dest_dir)
                # Evitar duplicados
                if any(x.name == name for x in self.items):
                    continue
                # Añadir una fila en blanco con mínimos
                dummy_row = {
                    'server': '',
                    'fmt': '',
                    'size': '',
                }
                self._add_download_row(it, dummy_row)  # type: ignore[arg-type]
                self.manager.add(it)
                self.items.append(it)
            QMessageBox.information(self, 'Sesión', 'Sesión cargada')
        except Exception as e:
            QMessageBox.critical(self, 'Sesión', str(e))

    # --- Carga/salva de sesión silenciosa (sin mensajes) ---
    def _save_session_silent(self) -> None:
        """Guarda la sesión actual de descargas en el fichero sin mostrar diálogos."""
        try:
            data = [{"name": it.name, "url": it.url, "dest": it.dest_dir} for it in self.items]
            with open(self._session_path(), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_session_silent(self) -> None:
        """Carga la sesión guardada sin mostrar mensajes (si existe)."""
        try:
            path = self._session_path()
            if not os.path.exists(path):
                return
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for d in data:
                name = d.get('name'); url = d.get('url'); dest_dir = d.get('dest') or self.le_dir.text().strip()
                if not (name and url and dest_dir):
                    continue
                it = DownloadItem(name=name, url=url, dest_dir=dest_dir)
                # Evitar duplicados
                if any(x.name == name for x in self.items):
                    continue
                dummy_row = {
                    'server': '',
                    'fmt': '',
                    'size': '',
                }
                self._add_download_row(it, dummy_row)  # type: ignore[arg-type]
                self.manager.add(it)
                self.items.append(it)
        except Exception:
            pass

    # --- Guardar/cargar configuración y cesta ---
    def _save_config(self) -> None:
        """Guarda la configuración y la cesta en QSettings."""
        try:
            settings = QSettings('RomManager', 'App')
            settings.setValue('db_path', self.le_db.text().strip())
            settings.setValue('download_dir', self.le_dir.text().strip())
            settings.setValue('concurrency', self.spin_conc.value())
            settings.setValue('chk_delete_after', self.chk_delete_after.isChecked())
            settings.setValue('chk_create_sys_dirs', self.chk_create_sys_dirs.isChecked())
            # Guardar cesta
            basket_data = []
            for rom_id, item in self.basket_items.items():
                basket_data.append({
                    'rom_id': rom_id,
                    'selected_server': item.get('selected_server', 0),
                    'selected_format': item.get('selected_format', 0),
                    'selected_lang': item.get('selected_lang', 0),
                })
            settings.setValue('basket_items', json.dumps(basket_data))
            # Guardar preferencia de confirmación de cancelación
            settings.setValue('no_confirm_cancel', self.no_confirm_cancel)
            settings.sync()
        except Exception:
            pass

    def _load_config(self) -> None:
        """Carga la configuración desde QSettings y aplica valores a los widgets."""
        try:
            settings = QSettings('RomManager', 'App')
            db_path = settings.value('db_path', '', type=str)
            download_dir = settings.value('download_dir', '', type=str)
            conc = settings.value('concurrency', 3, type=int)
            chk_del = settings.value('chk_delete_after', False, type=bool)
            chk_sys = settings.value('chk_create_sys_dirs', False, type=bool)
            self.le_db.setText(db_path)
            self.le_dir.setText(download_dir)
            self.spin_conc.setValue(conc)
            self.chk_delete_after.setChecked(chk_del)
            self.chk_create_sys_dirs.setChecked(chk_sys)
            # Restaurar archivo de sesión
            if download_dir:
                self.session_file = os.path.join(download_dir, 'downloads_session.json')
            # Cargar datos de cesta guardados (en formato JSON) después de conectar BD
            basket_json = settings.value('basket_items', '', type=str)
            self._saved_basket_json = basket_json
            # Restaurar preferencia de cancelación
            self.no_confirm_cancel = settings.value('no_confirm_cancel', False, type=bool)
        except Exception:
            self._saved_basket_json = ''

    def _load_basket_from_saved(self) -> None:
        """Restaura la cesta guardada a partir del JSON almacenado en QSettings."""
        try:
            if not self._saved_basket_json:
                return
            data = json.loads(self._saved_basket_json)
            # data es una lista de dicts con rom_id, selected_format, selected_lang
            for d in data:
                rom_id = d.get('rom_id')
                if rom_id is None:
                    continue
                try:
                    rom_id_int = int(rom_id)
                    links = self.db.get_links_by_rom(rom_id_int)
                except Exception:
                    continue
                if not links:
                    continue
                # Construir estructura de grupo similar a la búsqueda
                group_rows = links
                group = {
                    'name': links[0]['rom_name'],
                    'rows': group_rows
                }
                # Servidores únicos
                servers = sorted(set((row['server'] or '') for row in group_rows))
                formats_by_server: dict[str, List[str]] = {}
                for srv in servers:
                    fmts = sorted(set((row['fmt'] or '') for row in group_rows if (row['server'] or '') == srv))
                    formats_by_server[srv] = fmts
                langs_by_server_format: dict[tuple[str, str], List[str]] = {}
                for r in group_rows:
                    srv = r['server'] or ''
                    fmt_val = r['fmt'] or ''
                    key = (srv, fmt_val)
                    lang_str = r['langs'] or ''
                    lang_str = ','.join([x.strip() for x in lang_str.split(',') if x.strip()]) or ''
                    lst = langs_by_server_format.setdefault(key, [])
                    if lang_str not in lst:
                        lst.append(lang_str)
                for key in langs_by_server_format:
                    lst = langs_by_server_format[key]
                    lst.sort()
                    langs_by_server_format[key] = lst
                link_lookup: dict[tuple[str, str, str], sqlite3.Row] = {}
                for r in group_rows:
                    srv = r['server'] or ''
                    fmt_val = r['fmt'] or ''
                    lang_str = r['langs'] or ''
                    lang_str = ','.join([x.strip() for x in lang_str.split(',') if x.strip()]) or ''
                    link_lookup[(srv, fmt_val, lang_str)] = r
                group['servers'] = servers
                group['formats_by_server'] = formats_by_server
                group['langs_by_server_format'] = langs_by_server_format
                group['link_lookup'] = link_lookup
                group['selected_server'] = 0
                group['selected_format'] = 0
                group['selected_lang'] = 0
                # Ajustar índices guardados
                sel_srv = d.get('selected_server', 0)
                sel_fmt = d.get('selected_format', 0)
                sel_lang = d.get('selected_lang', 0)
                # Validar índices
                if sel_srv is None or sel_srv >= len(servers) or sel_srv < 0:
                    sel_srv = 0
                server_name = servers[sel_srv] if servers else ''
                fmt_list = formats_by_server.get(server_name, [])
                if sel_fmt is None or sel_fmt >= len(fmt_list) or sel_fmt < 0:
                    sel_fmt = 0
                fmt_name = fmt_list[sel_fmt] if fmt_list else ''
                lang_list = langs_by_server_format.get((server_name, fmt_name), [])
                if sel_lang is None or sel_lang >= len(lang_list) or sel_lang < 0:
                    sel_lang = 0
                # Guardar item en cesta
                self.basket_items[rom_id] = {
                    'name': group['name'],
                    'group': group,
                    'selected_server': sel_srv,
                    'selected_format': sel_fmt,
                    'selected_lang': sel_lang,
                }
            self._refresh_basket_table()
        except Exception:
            pass

    # --- Construcción de la pestaña Cesta ---
    def _build_basket_tab(self) -> None:
        """Crea la interfaz de la pestaña de cesta de descargas."""
        lay = QVBoxLayout(self.tab_basket)
        self.table_basket = QTableWidget(0, 4)
        self.table_basket.setHorizontalHeaderLabels(["ROM", "Formato", "Idioma", "Acciones"])
        self.table_basket.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table_basket)

    def _refresh_basket_table(self) -> None:
        """
        Actualiza la tabla de la cesta para reflejar las ROMs agrupadas y sus
        opciones. Cada entrada dispone de combinaciones de servidor, formato e
        idioma para seleccionar la variante que se descargará.
        """
        self.table_basket.setRowCount(0)
        # Cada entrada en basket_items crea una fila
        for rom_id, item in self.basket_items.items():
            row = self.table_basket.rowCount()
            self.table_basket.insertRow(row)
            # Columna 0: nombre de la ROM (guardar rom_id en UserRole)
            rom_item = QTableWidgetItem(item['name'])
            rom_item.setData(Qt.ItemDataRole.UserRole, rom_id)
            self.table_basket.setItem(row, 0, rom_item)
            # Columna 1: selector de servidor
            combo_srv = QComboBox()
            for srv in item['group']['servers']:
                combo_srv.addItem(srv or "")
            srv_idx = item.get('selected_server', 0)
            if srv_idx is not None and srv_idx < combo_srv.count():
                combo_srv.setCurrentIndex(srv_idx)
            combo_srv.setProperty('row_idx', row)
            combo_srv.setProperty('rom_id', rom_id)
            combo_srv.currentIndexChanged.connect(self._basket_server_changed)
            self.table_basket.setCellWidget(row, 1, combo_srv)
            # Columna 2: selector de formato (depende del servidor)
            combo_fmt = QComboBox()
            # Obtener el servidor actualmente seleccionado
            srv_name = item['group']['servers'][srv_idx] if item['group']['servers'] else ""
            fmt_list = item['group']['formats_by_server'].get(srv_name, [])
            for fmt in fmt_list:
                combo_fmt.addItem(fmt or "")
            fmt_idx = item.get('selected_format', 0)
            if fmt_idx is not None and fmt_idx < combo_fmt.count():
                combo_fmt.setCurrentIndex(fmt_idx)
            combo_fmt.setProperty('row_idx', row)
            combo_fmt.setProperty('rom_id', rom_id)
            combo_fmt.currentIndexChanged.connect(self._basket_format_changed)
            self.table_basket.setCellWidget(row, 2, combo_fmt)
            # Columna 3: selector de idiomas (depende de servidor y formato)
            combo_lang = QComboBox()
            fmt_name = fmt_list[fmt_idx] if fmt_list and fmt_idx < len(fmt_list) else ""
            lang_list = item['group']['langs_by_server_format'].get((srv_name, fmt_name), [])
            for lang_str in lang_list:
                combo_lang.addItem(lang_str or "")
            lang_idx = item.get('selected_lang', 0)
            if lang_idx is not None and lang_idx < combo_lang.count():
                combo_lang.setCurrentIndex(lang_idx)
            combo_lang.setProperty('row_idx', row)
            combo_lang.setProperty('rom_id', rom_id)
            combo_lang.currentIndexChanged.connect(self._basket_language_changed)
            self.table_basket.setCellWidget(row, 3, combo_lang)
            # Columna 4: botones de acción (Añadir, Eliminar)
            w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
            btn_add = QPushButton("Añadir")
            btn_remove = QPushButton("Eliminar")
            btn_add.setProperty('row_idx', row)
            btn_add.setProperty('rom_id', rom_id)
            btn_remove.setProperty('row_idx', row)
            btn_remove.setProperty('rom_id', rom_id)
            btn_add.clicked.connect(self._basket_add_to_downloads)
            btn_remove.clicked.connect(self._basket_remove_item)
            h.addWidget(btn_add); h.addWidget(btn_remove)
            self.table_basket.setCellWidget(row, 4, w)

    # --- Resultados agrupados ---
    def _display_grouped_results(self) -> None:
        """
        Población de la tabla de resultados agrupados según los datos en
        ``self.search_groups``. Cada fila representa una ROM y dispone de
        desplegables para servidor, formato e idioma, así como un botón para
        añadirla a la cesta.
        """
        logging.debug("Displaying grouped results for %d ROMs.", len(self.search_groups))
        # Limpiar la tabla
        self.table_results.setRowCount(0)
        # Ordenar por nombre de ROM para presentación consistente
        for rom_id in sorted(self.search_groups.keys(), key=lambda x: self.search_groups[x]["name"].lower()):
            group = self.search_groups[rom_id]
            row = self.table_results.rowCount()
            self.table_results.insertRow(row)
            # Columna 0: nombre de la ROM
            rom_item = QTableWidgetItem(group["name"])
            rom_item.setData(Qt.ItemDataRole.UserRole, rom_id)
            self.table_results.setItem(row, 0, rom_item)
            # Columna 1: selector de servidor
            combo_srv = QComboBox()
            for srv in group["servers"]:
                combo_srv.addItem(srv or "")
            # Selección actual
            combo_srv.setCurrentIndex(group.get("selected_server", 0))
            combo_srv.setProperty('rom_id', rom_id)
            combo_srv.setProperty('row_idx', row)
            combo_srv.currentIndexChanged.connect(self._group_server_changed)
            self.table_results.setCellWidget(row, 1, combo_srv)
            # Columna 2: selector de formato (depende del servidor)
            combo_fmt = QComboBox()
            srv_sel_index = group.get("selected_server", 0)
            srv_name = group["servers"][srv_sel_index] if group["servers"] else ""
            fmt_list = group["formats_by_server"].get(srv_name, [])
            for fmt in fmt_list:
                combo_fmt.addItem(fmt or "")
            combo_fmt.setCurrentIndex(group.get("selected_format", 0) if fmt_list else 0)
            combo_fmt.setProperty('rom_id', rom_id)
            combo_fmt.setProperty('row_idx', row)
            combo_fmt.currentIndexChanged.connect(self._group_format_changed)
            self.table_results.setCellWidget(row, 2, combo_fmt)
            # Columna 3: selector de idiomas (depende de servidor y formato)
            combo_lang = QComboBox()
            fmt_sel_index = group.get("selected_format", 0)
            fmt_name = fmt_list[fmt_sel_index] if fmt_list and fmt_sel_index < len(fmt_list) else ""
            lang_list = group["langs_by_server_format"].get((srv_name, fmt_name), [])
            for lang_str in lang_list:
                combo_lang.addItem(lang_str or "")
            combo_lang.setCurrentIndex(group.get("selected_lang", 0) if lang_list else 0)
            combo_lang.setProperty('rom_id', rom_id)
            combo_lang.setProperty('row_idx', row)
            combo_lang.currentIndexChanged.connect(self._group_language_changed)
            self.table_results.setCellWidget(row, 3, combo_lang)
            # Columna 4: botón para añadir a la cesta
            btn_add = QPushButton("Añadir")
            btn_add.setProperty('rom_id', rom_id)
            btn_add.setProperty('row_idx', row)
            btn_add.clicked.connect(self._add_group_to_basket)
            self.table_results.setCellWidget(row, 4, btn_add)

    # --- Manejadores de cambios en los combos de resultados ---
    def _group_server_changed(self, index: int) -> None:
        """
        Maneja el cambio de servidor en la tabla de resultados agrupados. Al
        cambiar el servidor se reinician el formato e idioma seleccionados y
        se actualizan los combos correspondientes en la fila.
        """
        combo = self.sender()
        if combo is None:
            return
        rom_id = combo.property('rom_id')
        row_idx = combo.property('row_idx')
        if rom_id is None or row_idx is None:
            return
        group = self.search_groups.get(rom_id)
        if not group:
            return
        group['selected_server'] = combo.currentIndex()
        group['selected_format'] = 0
        group['selected_lang'] = 0
        # Actualizar combos de formato e idioma en la fila
        row_idx = int(row_idx)
        # Formato
        srv_name = group['servers'][group['selected_server']] if group['servers'] else ""
        fmt_combo: QComboBox = self.table_results.cellWidget(row_idx, 2)  # type: ignore
        fmt_combo.blockSignals(True)
        fmt_combo.clear()
        fmt_list = group['formats_by_server'].get(srv_name, [])
        for fmt in fmt_list:
            fmt_combo.addItem(fmt or "")
        fmt_combo.setCurrentIndex(0 if fmt_list else 0)
        fmt_combo.blockSignals(False)
        # Idiomas
        lang_combo: QComboBox = self.table_results.cellWidget(row_idx, 3)  # type: ignore
        lang_combo.blockSignals(True)
        lang_combo.clear()
        fmt_name = fmt_list[0] if fmt_list else ""
        lang_list = group['langs_by_server_format'].get((srv_name, fmt_name), [])
        for lang_str in lang_list:
            lang_combo.addItem(lang_str or "")
        lang_combo.setCurrentIndex(0 if lang_list else 0)
        lang_combo.blockSignals(False)

    def _group_format_changed(self, index: int) -> None:
        """
        Maneja el cambio de formato en la tabla de resultados agrupados. Al
        cambiar el formato se reinicia el idioma seleccionado y se actualiza
        el combo de idiomas.
        """
        combo = self.sender()
        if combo is None:
            return
        rom_id = combo.property('rom_id')
        row_idx = combo.property('row_idx')
        if rom_id is None or row_idx is None:
            return
        group = self.search_groups.get(rom_id)
        if not group:
            return
        # Actualizar índice de formato seleccionado
        group['selected_format'] = combo.currentIndex()
        group['selected_lang'] = 0
        # Obtener servidor actualmente seleccionado
        srv_idx = group.get('selected_server', 0)
        srv_name = group['servers'][srv_idx] if group['servers'] else ""
        fmt_list = group['formats_by_server'].get(srv_name, [])
        fmt_name = fmt_list[combo.currentIndex()] if fmt_list and combo.currentIndex() < len(fmt_list) else ""
        # Actualizar combo de idiomas
        row_idx = int(row_idx)
        lang_combo: QComboBox = self.table_results.cellWidget(row_idx, 3)  # type: ignore
        lang_combo.blockSignals(True)
        lang_combo.clear()
        lang_list = group['langs_by_server_format'].get((srv_name, fmt_name), [])
        for lang_str in lang_list:
            lang_combo.addItem(lang_str or "")
        lang_combo.setCurrentIndex(0 if lang_list else 0)
        lang_combo.blockSignals(False)

    def _group_language_changed(self, index: int) -> None:
        """
        Guarda la selección de idioma cuando cambia en la tabla de resultados agrupados.
        """
        combo = self.sender()
        if combo is None:
            return
        rom_id = combo.property('rom_id')
        if rom_id is None:
            return
        group = self.search_groups.get(rom_id)
        if not group:
            return
        group['selected_lang'] = combo.currentIndex()

    def _add_group_to_basket(self) -> None:
        """
        Añade la selección actual de una ROM desde la tabla de resultados a la
        cesta. Se basa en la combinación de servidor, formato e idioma
        seleccionados en la fila correspondiente.
        """
        btn = self.sender()
        if btn is None:
            return
        rom_id = btn.property('rom_id')
        if rom_id is None:
            return
        group = self.search_groups.get(rom_id)
        if not group:
            return
        # Obtener selección
        srv_idx = group.get('selected_server', 0)
        srv_name = group['servers'][srv_idx] if group['servers'] else ""
        fmt_idx = group.get('selected_format', 0)
        fmt_list = group['formats_by_server'].get(srv_name, [])
        fmt_name = fmt_list[fmt_idx] if fmt_list and fmt_idx < len(fmt_list) else ""
        lang_idx = group.get('selected_lang', 0)
        lang_list = group['langs_by_server_format'].get((srv_name, fmt_name), [])
        lang_name = lang_list[lang_idx] if lang_list and lang_idx < len(lang_list) else ""
        # Crear/actualizar entrada en la cesta
        self.basket_items[rom_id] = {
            'name': group['name'],
            'group': group,
            'selected_server': srv_idx,
            'selected_format': fmt_idx,
            'selected_lang': lang_idx,
        }
        logging.debug("Added ROM %s to basket with server=%s, fmt=%s, lang=%s", group['name'], srv_name, fmt_name, lang_name)
        # Refrescar la tabla de la cesta
        self._refresh_basket_table()

    def _basket_server_changed(self, index: int) -> None:
        """
        Cuando se cambia el servidor en la cesta, reinicia las selecciones de
        formato e idioma y actualiza la tabla.
        """
        combo = self.sender()
        if combo is None:
            return
        row = combo.property('row_idx')
        rom_id = combo.property('rom_id')
        if rom_id is None:
            return
        # Actualizar el índice de servidor en el item de la cesta
        item = self.basket_items.get(rom_id)
        if not item:
            return
        item['selected_server'] = combo.currentIndex()
        # Reiniciar formato e idioma
        item['selected_format'] = 0
        item['selected_lang'] = 0
        # Refrescar la tabla completa para actualizar los combos
        self._refresh_basket_table()

    def _basket_format_changed(self, index: int) -> None:
        """
        Actualiza la lista de idiomas cuando cambia el formato seleccionado en
        la cesta. Reinicia el idioma y refresca la tabla.
        """
        combo = self.sender()
        if combo is None:
            return
        row = combo.property('row_idx')
        rom_id = combo.property('rom_id')
        if rom_id is None:
            return
        item = self.basket_items.get(rom_id)
        if not item:
            return
        item['selected_format'] = combo.currentIndex()
        item['selected_lang'] = 0
        # Refrescar la tabla para actualizar combo de idiomas
        self._refresh_basket_table()

    def _basket_language_changed(self, index: int) -> None:
        """
        Guarda la selección de idioma cuando cambia en la cesta.
        """
        combo = self.sender()
        if combo is None:
            return
        rom_id = combo.property('rom_id')
        if rom_id is None:
            return
        item = self.basket_items.get(rom_id)
        if not item:
            return
        item['selected_lang'] = combo.currentIndex()

    def _basket_add_to_downloads(self) -> None:
        """
        Añade la ROM seleccionada desde la cesta a la cola de descargas y la
        elimina de la cesta. Se utiliza la combinación de servidor, formato e
        idioma actualmente seleccionada para obtener la URL correcta.
        """
        btn = self.sender()
        if btn is None:
            return
        rom_id = btn.property('rom_id')
        if rom_id is None:
            return
        if rom_id not in self.basket_items:
            return
        item = self.basket_items[rom_id]
        group = item['group']
        # Obtener selección
        srv_idx = item.get('selected_server', 0)
        srv_name = group['servers'][srv_idx] if group['servers'] else ""
        fmt_idx = item.get('selected_format', 0)
        fmt_list = group['formats_by_server'].get(srv_name, [])
        fmt_name = fmt_list[fmt_idx] if fmt_list and fmt_idx < len(fmt_list) else ""
        lang_idx = item.get('selected_lang', 0)
        lang_list = group['langs_by_server_format'].get((srv_name, fmt_name), [])
        lang_name = lang_list[lang_idx] if lang_list and lang_idx < len(lang_list) else ""
        row_data = group['link_lookup'].get((srv_name, fmt_name, lang_name))
        if not row_data:
            return
        # Crear DownloadItem
        logging.debug("Adding from basket to downloads: ROM %s, server=%s, fmt=%s, lang=%s", group['name'], srv_name, fmt_name, lang_name)
        name = safe_filename(row_data['label'] or row_data['rom_name'] or os.path.basename(row_data['url']))
        dest_dir = self.le_dir.text().strip()
        if not dest_dir:
            QMessageBox.warning(self, "Descargas", "Selecciona una carpeta de descargas en la pestaña de Ajustes.")
            return
        download_item = DownloadItem(name=name, url=row_data['url'], dest_dir=dest_dir)
        src_row = {
            'server': row_data['server'] or '',
            'fmt': row_data['fmt'] or '',
            'size': row_data['size'] or '',
            # Almacenar nombre amigable para mostrar en descargas
            'display_name': row_data['rom_name'] or group['name'],
            'rom_name': row_data['rom_name'] or group['name'],
        }
        self._add_download_row(download_item, src_row)  # type: ignore[arg-type]
        self.manager.add(download_item)
        self.items.append(download_item)
        # Quitar de la cesta y refrescar
        del self.basket_items[rom_id]
        self._refresh_basket_table()

    def _basket_remove_item(self) -> None:
        """Elimina una ROM de la cesta sin descargarla."""
        btn = self.sender()
        if btn is None:
            return
        rom_id = btn.property('rom_id')
        if rom_id is None:
            return
        if rom_id in self.basket_items:
            removed = self.basket_items.pop(rom_id)
            logging.debug("Removed ROM %s from basket", removed['name'])
            self._refresh_basket_table()

    def _add_selected_to_basket(self) -> None:
        """
        Agrupa las ROM seleccionadas en la tabla de resultados en la cesta.

        Esta implementación utiliza la tabla de resultados agrupados (``self.table_results``)
        en lugar de la antigua ``self.table_links``. Cada fila seleccionada se corresponde
        con un rom_id almacenado en el ``UserRole`` del primer elemento de la fila. Si la
        ROM ya existe en la cesta, se ignora. Las opciones de servidor, formato e idioma
        predeterminadas se inicializan a 0. La estructura de grupo necesaria para las
        listas desplegables se copia de ``self.search_groups`` cuando está disponible.
        """
        if not self.db:
            QMessageBox.warning(self, "BD", "Conecta la base de datos primero.")
            return
        # Seleccionar filas desde la tabla de resultados agrupados
        indexes = self.table_results.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self, "Cesta", "No hay filas seleccionadas.")
            return
        for idx in indexes:
            row = idx.row()
            rom_item = self.table_results.item(row, 0)
            if rom_item is None:
                continue
            rom_id = rom_item.data(Qt.ItemDataRole.UserRole)
            if rom_id is None:
                continue
            # Evitar duplicados
            if rom_id in self.basket_items:
                continue
            # Obtener filas de links de la BD
            try:
                links = self.db.get_links_by_rom(int(rom_id))
            except Exception:
                continue
            if not links:
                continue
            rom_name = links[0]['rom_name']
            # Copiar la estructura de grupo si existe para mantener servidores, formatos e idiomas
            group = self.search_groups.get(rom_id)
            if group is None:
                # Construir una estructura de agrupación mínima a partir de las filas
                rows_list = links
                # Servidores únicos
                servers = sorted(set((row["server"] or "") for row in rows_list))
                # Diccionario: servidor -> lista de formatos únicos
                formats_by_server: dict[str, List[str]] = {}
                for srv in servers:
                    fmts = sorted(set((row["fmt"] or "") for row in rows_list if (row["server"] or "") == srv))
                    formats_by_server[srv] = fmts
                # Diccionario: (servidor, formato) -> lista de idiomas únicos (cadenas completas)
                langs_by_server_format: dict[tuple[str, str], List[str]] = {}
                for rlink in rows_list:
                    srv = rlink["server"] or ""
                    fmt_val = rlink["fmt"] or ""
                    key = (srv, fmt_val)
                    lang_str = rlink["langs"] or ""
                    lang_str = ','.join([x.strip() for x in lang_str.split(',') if x.strip()]) or ""
                    lst = langs_by_server_format.setdefault(key, [])
                    if lang_str not in lst:
                        lst.append(lang_str)
                # Ordenar idiomas y mantener cadena vacía al final
                for key in langs_by_server_format:
                    lst = langs_by_server_format[key]
                    lst.sort()
                    langs_by_server_format[key] = lst
                # Diccionario de búsqueda: (servidor, formato, idiomas) -> fila
                link_lookup: dict[tuple[str, str, str], sqlite3.Row] = {}
                for rlink in rows_list:
                    srv = rlink["server"] or ""
                    fmt_val = rlink["fmt"] or ""
                    lang_str = rlink["langs"] or ""
                    lang_str = ','.join([x.strip() for x in lang_str.split(',') if x.strip()]) or ""
                    link_lookup[(srv, fmt_val, lang_str)] = rlink
                group = {
                    "name": rom_name,
                    "rows": rows_list,
                    "servers": servers,
                    "formats_by_server": formats_by_server,
                    "langs_by_server_format": langs_by_server_format,
                    "link_lookup": link_lookup,
                    "selected_server": 0,
                    "selected_format": 0,
                    "selected_lang": 0,
                }
            self.basket_items[rom_id] = {
                'name': rom_name,
                'links': links,
                'group': group,
                'selected_server': 0,
                'selected_format': 0,
                'selected_lang': 0,
            }
        # Actualizar la tabla de la cesta después de añadir los elementos
        self._refresh_basket_table()

    # --- Evento de cierre ---
    def closeEvent(self, event) -> None:
        """Sobrecarga para guardar configuración, cesta y sesión automáticamente al cerrar."""
        try:
            # Guardar sesión y configuración de manera silenciosa
            self._save_session_silent()
            self._save_config()
        except Exception:
            pass
        event.accept()
    # --- utilidades de formato ---
    @staticmethod
    def _human_size(nbytes: float) -> str:
        """Convierte bytes a una representación legible (B, KB, MB…)."""
        units = ['B', 'KB', 'MB', 'GB', 'TB']; i = 0
        while nbytes >= 1024 and i < len(units) - 1:
            nbytes /= 1024.0; i += 1
        return f"{int(nbytes)} {units[i]}" if i == 0 else f"{nbytes:.2f} {units[i]}"

    @staticmethod
    def _fmt_eta(sec: float) -> str:
        """Convierte un número de segundos a un formato HH:MM:SS."""
        sec = int(sec); h = sec // 3600; m = (sec % 3600) // 60; s = sec % 60
        if h > 0:
            return f"{h}h {m:02d}m {s:02d}s"
        if m > 0:
            return f"{m}m {s:02d}s"
        return f"{s}s"

# -----------------------------
# Punto de entrada
# -----------------------------

def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow(); win.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()