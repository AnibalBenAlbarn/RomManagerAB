"""Widgets y ventanas de la interfaz gráfica del gestor de ROMs."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, unquote
import json
import logging
import sqlite3
import math
from typing import Optional, List, Dict, Sequence

from PyQt6.QtCore import Qt, QThreadPool, QTimer, QUrl, QEvent, QObject
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QGroupBox, QFrame, QComboBox, QSpinBox, QTableView, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QProgressBar, QCheckBox, QTabWidget,
    QAbstractItemView, QListWidget, QListWidgetItem, QMenu, QStyle, QSystemTrayIcon
)
from PyQt6.QtGui import QDesktopServices, QIcon

from ..database import Database
from ..models import LinksTableModel
from ..download import DownloadManager, DownloadItem, ExtractionTask
from ..emulators import EmulatorInfo, get_all_systems, get_emulator_catalog, get_emulators_for_system
from ..paths import config_path, session_path

from ..utils import safe_filename, extract_archive, resource_path


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
        icon_path = resource_path("resources/romMan.ico")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            if not icon.isNull():
                self.setWindowIcon(icon)
        self.setWindowTitle("RomManager AB")
        self.resize(1200, 800)
        self.pool = QThreadPool.globalInstance()
        self.db: Optional[Database] = None
        self.session_file = str(self._session_storage_path())

        # Preferencias del usuario
        # Flag para omitir la confirmación al cancelar descargas
        self.no_confirm_cancel: bool = False
        # Flag para ocultar la advertencia de servidores al iniciar
        self.hide_server_warning: bool = False

        # Estado
        self.model = LinksTableModel([])
        self.manager = DownloadManager(self.pool, 3)
        self.manager.queue_changed.connect(self._refresh_downloads_table)
        # Seguir descargas en segundo plano
        self.manager.queue_changed.connect(self._check_background_downloads)
        self.background_downloads: bool = False
        self.items: List[DownloadItem] = []
        self._emulator_catalog: List[EmulatorInfo] = []
        self._current_emulator: Optional[EmulatorInfo] = None
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._tray_menu: Optional[QMenu] = None
        self._tray_show_action = None
        self._tray_exit_action = None
        self._tray_message_shown: bool = False
        self._setup_tray_icon()

        # Cesta de descargas (agrupa ROMs) y estructura de búsqueda
        # Es importante inicializar estos diccionarios antes de construir las pestañas,
        # ya que algunas pestañas (como el selector) pueden llamar a métodos que
        # dependen de ellos, como `_refresh_basket_table`.
        self.basket_items: dict[int, dict] = {}
        self.search_groups: dict[int, List[sqlite3.Row]] = {}

        # Tabs: mostrar primero el selector, luego emuladores, descargas y finalmente ajustes
        tabs = QTabWidget(); self.setCentralWidget(tabs)
        # Crear contenedores para cada pestaña
        self.tab_selector = QWidget()
        self.tab_emulators = QWidget()
        self.tab_downloads = QWidget()
        self.tab_settings = QWidget()
        # Añadir pestañas en orden: Selector, Emuladores, Descargas, Ajustes
        tabs.addTab(self.tab_selector, "Selector de ROMs")
        tabs.addTab(self.tab_emulators, "Emuladores")
        tabs.addTab(self.tab_downloads, "Descargas")
        tabs.addTab(self.tab_settings, "Ajustes")

        # Construir las pestañas
        self._build_selector_tab()
        self._build_emulators_tab()
        # La cesta se construirá dentro del selector, no como pestaña aparte
        self._build_downloads_tab()
        self._build_settings_tab()



        # Cargar configuración previa y restaurar estado
        self._load_config()

        # Mostrar advertencia sobre servidores si no está desactivada
        if not self.hide_server_warning:
            self._warn_servers_unavailable()

        # Si existe una ruta de BD guardada, conectar automáticamente
        db_path = self.le_db.text().strip()
        if db_path and os.path.exists(db_path):
            try:
                self._connect_db()
            except Exception:
                pass
        # Advertir si no hay base de datos configurada
        if not self.db:
            self._prompt_db_missing()
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

    # --- Icono de bandeja del sistema ---
    def _session_storage_path(self, download_dir: Optional[str] = None) -> Path:
        """Calcula la ruta de almacenamiento para la sesión de descargas."""

        folder_name = Path(download_dir).name if download_dir else ""
        safe_name = safe_filename(folder_name) if folder_name else ""
        filename = (
            f"{safe_name}_downloads_session.json"
            if safe_name
            else "downloads_session.json"
        )
        return session_path(filename)

    def _config_file_path(self) -> Path:
        """Ruta del fichero JSON donde se guarda la configuración."""

        return config_path("settings.json")

    def _setup_tray_icon(self) -> None:
        """Configura el icono de la bandeja del sistema para el modo en segundo plano."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self)
        icon_path = resource_path("resources/romMan.ico")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            if not icon.isNull():
                tray.setIcon(icon)
        tray.setToolTip("RomManager AB — Descargas en segundo plano")
        menu = QMenu(self)
        show_action = menu.addAction("Mostrar ventana")
        show_action.triggered.connect(self._restore_from_tray)
        exit_action = menu.addAction("Salir")
        exit_action.triggered.connect(self._quit_from_tray)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_icon_activated)
        tray.hide()
        self.tray_icon = tray
        self._tray_menu = menu
        self._tray_show_action = show_action
        self._tray_exit_action = exit_action

    def _enter_background_mode(self) -> bool:
        """Activa el modo en segundo plano mostrando el icono de bandeja."""
        if not self.tray_icon:
            QMessageBox.warning(
                self,
                'Descargas en segundo plano',
                'No es posible ejecutar en segundo plano porque el sistema no permite iconos en la bandeja.'
            )
            return False
        self.background_downloads = True
        if not self.tray_icon.isVisible():
            self.tray_icon.show()
        if QSystemTrayIcon.supportsMessages() and not self._tray_message_shown:
            self.tray_icon.showMessage(
                'RomManager AB',
                'Las descargas continúan en segundo plano. Haz doble clic en el icono para volver a abrir la ventana.',
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
            self._tray_message_shown = True
        return True

    def _restore_from_tray(self) -> None:
        """Restaura la ventana principal desde el icono de la bandeja."""
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.hide()
        self.background_downloads = False
        self.showNormal()
        self.show()
        self.activateWindow()
        try:
            self.raise_()
        except Exception:
            pass

    def _on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Responde a la interacción del usuario con el icono de la bandeja."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._restore_from_tray()

    def _quit_from_tray(self) -> None:
        """Cierra la aplicación desde el icono de la bandeja."""
        self.background_downloads = False
        self.close()

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
        self.chk_extract_after = QCheckBox("Descomprimir al finalizar")
        self.chk_delete_after = QCheckBox("Eliminar archivo tras descompresión")
        self.chk_delete_after.setEnabled(False)
        self.chk_extract_after.toggled.connect(lambda v: self.chk_delete_after.setEnabled(v))
        self.chk_create_sys_dirs = QCheckBox("Crear carpetas por sistema")
        self.btn_recommended = QPushButton("Usar ajustes recomendados para máxima velocidad")
        self.btn_recommended.clicked.connect(lambda: (self.spin_conc.setValue(5)))
        g.addWidget(QLabel("Carpeta descargas:"),0,0); g.addWidget(self.le_dir,0,1); g.addWidget(self.btn_dir,0,2)
        g.addWidget(QLabel("Concurrencia (1–5):"),1,0); g.addWidget(self.spin_conc,1,1)
        g.addWidget(self.chk_extract_after,2,0,1,3)
        g.addWidget(self.chk_delete_after,3,0,1,3)
        g.addWidget(self.chk_create_sys_dirs,4,0,1,3)
        g.addWidget(self.btn_recommended,5,0,1,3)
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
        self.chk_extract_after = QCheckBox("Descomprimir al finalizar")
        self.chk_delete_after = QCheckBox("Eliminar archivo tras descompresión")
        self.chk_delete_after.setEnabled(False)
        self.chk_extract_after.toggled.connect(lambda v: self.chk_delete_after.setEnabled(v))
        self.chk_create_sys_dirs = QCheckBox("Crear carpetas por sistema")
        self.btn_recommended = QPushButton("Usar ajustes recomendados para máxima velocidad")
        self.btn_recommended.clicked.connect(lambda: (self.spin_conc.setValue(5)))
        grid_dl.addWidget(QLabel("Carpeta descargas:"), 0, 0); grid_dl.addWidget(self.le_dir, 0, 1); grid_dl.addWidget(self.btn_dir, 0, 2)
        grid_dl.addWidget(QLabel("Concurrencia (1–5):"), 1, 0); grid_dl.addWidget(self.spin_conc, 1, 1)
        grid_dl.addWidget(self.chk_extract_after, 2, 0, 1, 3)
        grid_dl.addWidget(self.chk_delete_after, 3, 0, 1, 3)
        grid_dl.addWidget(self.chk_create_sys_dirs, 4, 0, 1, 3)
        grid_dl.addWidget(self.btn_recommended, 5, 0, 1, 3)
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
        self.le_search.returnPressed.connect(self._run_search)
        self.cmb_system = QComboBox(); self.cmb_lang = QComboBox(); self.cmb_region = QComboBox(); self.cmb_fmt = QComboBox()
        self.btn_search = QPushButton("Buscar"); self.btn_search.clicked.connect(self._run_search)
        f.addWidget(QLabel("Texto:"),0,0); f.addWidget(self.le_search,0,1)
        f.addWidget(QLabel("Sistema:"),1,0); f.addWidget(self.cmb_system,1,1)
        f.addWidget(QLabel("Idioma:"),2,0); f.addWidget(self.cmb_lang,2,1)
        f.addWidget(QLabel("Región:"),3,0); f.addWidget(self.cmb_region,3,1)
        f.addWidget(QLabel("Formato:"),4,0); f.addWidget(self.cmb_fmt,4,1)
        f.addWidget(self.btn_search,0,2,5,1)
        lay.addWidget(filters)

        # Tabla de resultados agrupados: columnas ROM, Sistema, Servidor, Formato, Idiomas, Acciones
        self.table_results = QTableWidget(0, 6)
        self.table_results.setHorizontalHeaderLabels([
            "ROM", "Sistema", "Servidor", "Formato", "Idiomas", "Acciones"
        ])
        self.table_results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table_results)

        # Encabezado de la cesta y tabla de la cesta: se sitúan debajo de los resultados
        basket_label = QLabel("Cesta de descargas")
        basket_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        lay.addWidget(basket_label)
        self.table_basket = QTableWidget(0, 6)
        self.table_basket.setHorizontalHeaderLabels([
            "ROM", "Sistema", "Servidor", "Formato", "Idioma", "Acciones"
        ])
        self.table_basket.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table_basket)
        self.btn_basket_add_all = QPushButton("Añadir todo a descargas")
        self.btn_basket_add_all.clicked.connect(self._basket_add_all_to_downloads)
        lay.addWidget(self.btn_basket_add_all)

        # Inicializar la cesta vacía
        self._refresh_basket_table()

    # --- Emuladores ---
    def _build_emulators_tab(self) -> None:
        """Construye la pestaña de emuladores con selección dependiente por sistema."""

        lay = QVBoxLayout(self.tab_emulators)

        # Carpeta base para instalar los emuladores descargados
        path_box = QGroupBox("Carpeta de emuladores")
        path_grid = QGridLayout(path_box)
        self.le_emulator_dir = QLineEdit()
        self.btn_emulator_dir = QPushButton("Explorar…")
        self.btn_emulator_dir.clicked.connect(self._choose_emulator_dir)
        self.chk_emulator_delete = QCheckBox("Eliminar archivo comprimido tras la extracción")
        path_grid.addWidget(QLabel("Carpeta base:"), 0, 0)
        path_grid.addWidget(self.le_emulator_dir, 0, 1)
        path_grid.addWidget(self.btn_emulator_dir, 0, 2)
        path_grid.addWidget(self.chk_emulator_delete, 1, 0, 1, 3)
        lay.addWidget(path_box)

        # Selector dependiente sistema -> emulador
        selector_box = QGroupBox("Catálogo de emuladores")
        selector_grid = QGridLayout(selector_box)
        self.cmb_emulator_system = QComboBox()
        self.cmb_emulator = QComboBox()
        self.cmb_emulator.setEnabled(False)
        selector_grid.addWidget(QLabel("Sistema:"), 0, 0)
        selector_grid.addWidget(self.cmb_emulator_system, 0, 1)
        selector_grid.addWidget(QLabel("Emulador:"), 1, 0)
        selector_grid.addWidget(self.cmb_emulator, 1, 1)
        self.btn_emulator_download = QPushButton("Descargar e instalar")
        self.btn_emulator_download.setEnabled(False)
        self.btn_emulator_download.clicked.connect(self._download_selected_emulator)
        selector_grid.addWidget(self.btn_emulator_download, 2, 0, 1, 2)
        lay.addWidget(selector_box)

        # Detalles del emulador seleccionado
        details_box = QGroupBox("Detalles del emulador")
        form = QFormLayout(details_box)
        self.lbl_emulator_systems = QLabel("—")
        self.lbl_emulator_systems.setWordWrap(True)
        form.addRow("Sistemas compatibles:", self.lbl_emulator_systems)

        url_container = QWidget()
        url_layout = QHBoxLayout(url_container)
        url_layout.setContentsMargins(0, 0, 0, 0)
        self.le_emulator_url = QLineEdit()
        self.le_emulator_url.setReadOnly(True)
        self.btn_emulator_open_url = QPushButton("Abrir enlace")
        self.btn_emulator_open_url.setEnabled(False)
        self.btn_emulator_open_url.clicked.connect(self._open_emulator_url)
        url_layout.addWidget(self.le_emulator_url)
        url_layout.addWidget(self.btn_emulator_open_url)
        form.addRow("URL de descarga:", url_container)

        self.list_emulator_extras = QListWidget()
        self.list_emulator_extras.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_emulator_extras.itemSelectionChanged.connect(self._on_extra_selection_changed)
        self.list_emulator_extras.itemDoubleClicked.connect(lambda _: self._download_selected_extra())
        form.addRow("Archivos extra:", self.list_emulator_extras)

        self.btn_emulator_download_extra = QPushButton("Descargar archivo extra")
        self.btn_emulator_download_extra.setEnabled(False)
        self.btn_emulator_download_extra.clicked.connect(self._download_selected_extra)
        form.addRow("", self.btn_emulator_download_extra)

        self.lbl_emulator_notes = QLabel("—")
        self.lbl_emulator_notes.setWordWrap(True)
        form.addRow("Notas:", self.lbl_emulator_notes)
        lay.addWidget(details_box)

        feedback_box = QFrame()
        feedback_box.setObjectName("emulatorFeedbackBox")
        feedback_layout = QHBoxLayout(feedback_box)
        feedback_layout.setContentsMargins(12, 8, 12, 8)
        feedback_layout.setSpacing(10)
        icon_label = QLabel()
        icon_label.setObjectName("emulatorFeedbackIcon")
        icon_label.setVisible(False)
        feedback_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)
        message_label = QLabel("")
        message_label.setObjectName("emulatorFeedbackMessage")
        message_label.setWordWrap(True)
        feedback_layout.addWidget(message_label, 1)
        feedback_box.setVisible(False)
        lay.addWidget(feedback_box)

        self._emulator_feedback_box = feedback_box
        self._emulator_feedback_icon = icon_label
        self._emulator_feedback_label = message_label
        self._emulator_feedback_timer = QTimer(self)
        self._emulator_feedback_timer.setSingleShot(True)
        self._emulator_feedback_timer.timeout.connect(self._hide_emulator_feedback)
        self._apply_emulator_feedback_style("info")

        # Cargar catálogo y poblar combos
        self._emulator_catalog = get_emulator_catalog()
        self.cmb_emulator_system.addItem("Selecciona un sistema…", "")
        for system in get_all_systems():
            self.cmb_emulator_system.addItem(system, system)
        self.cmb_emulator_system.addItem("Todos los sistemas", "__all__")
        self.cmb_emulator_system.currentIndexChanged.connect(self._on_emulator_system_changed)
        self.cmb_emulator.currentIndexChanged.connect(self._on_emulator_selected)
        self._on_emulator_system_changed(0)

    def _on_emulator_system_changed(self, index: int) -> None:
        """Actualiza la lista de emuladores al cambiar de sistema."""

        value = self.cmb_emulator_system.currentData()
        if value == "__all__":
            data = self._emulator_catalog
        elif not value:
            data = []
        else:
            data = get_emulators_for_system(str(value))
        self._populate_emulator_combo(data)

    def _populate_emulator_combo(self, emulators: List[EmulatorInfo]) -> None:
        self.cmb_emulator.blockSignals(True)
        self.cmb_emulator.clear()
        for emu in emulators:
            self.cmb_emulator.addItem(emu.name, emu)
        self.cmb_emulator.blockSignals(False)
        has_data = bool(emulators)
        self.cmb_emulator.setEnabled(has_data)
        self.btn_emulator_download.setEnabled(False)
        if has_data:
            self.cmb_emulator.setCurrentIndex(0)
            self._update_emulator_details(emulators[0])
        else:
            self._update_emulator_details(None)

    def _reset_extra_list(self, message: str = "No hay archivos extra disponibles") -> None:
        if not hasattr(self, "list_emulator_extras"):
            return
        self.list_emulator_extras.blockSignals(True)
        self.list_emulator_extras.clear()
        self.list_emulator_extras.blockSignals(False)
        item = QListWidgetItem(message)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.list_emulator_extras.addItem(item)
        self.list_emulator_extras.setEnabled(False)
        if hasattr(self, "btn_emulator_download_extra"):
            self.btn_emulator_download_extra.setEnabled(False)

    def _populate_extra_list(self, extras: Sequence[Dict[str, str]]) -> None:
        self.list_emulator_extras.blockSignals(True)
        self.list_emulator_extras.clear()
        for extra in extras:
            label = extra.get("label") or extra.get("url") or "Archivo extra"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, extra)
            self.list_emulator_extras.addItem(item)
        self.list_emulator_extras.blockSignals(False)
        self.list_emulator_extras.setEnabled(bool(extras))
        self._on_extra_selection_changed()

    def _on_emulator_selected(self, index: int) -> None:
        emu = self.cmb_emulator.currentData()
        if isinstance(emu, EmulatorInfo):
            self._update_emulator_details(emu)
        else:
            self._update_emulator_details(None)

    def _on_extra_selection_changed(self) -> None:
        if not hasattr(self, "btn_emulator_download_extra"):
            return
        has_selection = bool(self.list_emulator_extras.selectedItems()) and self.list_emulator_extras.isEnabled()
        self.btn_emulator_download_extra.setEnabled(has_selection)

    def _extra_folder_name(self, label: str, url: str) -> str:
        text = f"{label} {url}".lower()
        if "bios" in text:
            return "BIOS"
        return "Archivos extras"

    def _update_emulator_details(self, emulator: Optional[EmulatorInfo]) -> None:
        self._current_emulator = emulator
        if not emulator:
            self.lbl_emulator_systems.setText("—")
            self.le_emulator_url.setText("")
            self._reset_extra_list("Selecciona un emulador para ver archivos extra")
            self.lbl_emulator_notes.setText("—")
            self.btn_emulator_download.setEnabled(False)
            self.btn_emulator_open_url.setEnabled(False)
            return

        systems_text = ", ".join(emulator.systems)
        self.lbl_emulator_systems.setText(systems_text)
        self.le_emulator_url.setText(emulator.url)
        self.btn_emulator_open_url.setEnabled(bool(emulator.url))
        self.btn_emulator_download.setEnabled(bool(emulator.url))
        if emulator.extras:
            self._populate_extra_list(emulator.extras)
        else:
            self._reset_extra_list()
        self.lbl_emulator_notes.setText(emulator.notes or "—")

    def _apply_emulator_feedback_style(self, kind: str) -> None:
        if not hasattr(self, "_emulator_feedback_box"):
            return
        palette = {
            "success": ("#d4edda", "#1e8449"),
            "info": ("#d6eaf8", "#1b4f72"),
            "warning": ("#fcf3cf", "#9a7d0a"),
        }
        background, border = palette.get(kind, palette["info"])
        text_color = border
        self._emulator_feedback_box.setStyleSheet(
            f"""
            QFrame#emulatorFeedbackBox {{
                background-color: {background};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            QLabel#emulatorFeedbackMessage {{
                color: {text_color};
                font-weight: 600;
            }}
            QLabel#emulatorFeedbackIcon {{
                color: {text_color};
            }}
            """
        )

    def _show_emulator_feedback(self, message: str, kind: str = "info", duration_ms: int = 5000) -> None:
        if not hasattr(self, "_emulator_feedback_box"):
            return
        self._apply_emulator_feedback_style(kind)
        icon_map = {
            "success": QStyle.StandardPixmap.SP_DialogApplyButton,
            "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
            "warning": QStyle.StandardPixmap.SP_MessageBoxWarning,
        }
        std_icon = self.style().standardIcon(icon_map.get(kind, icon_map["info"]))
        if std_icon.isNull():
            self._emulator_feedback_icon.clear()
            self._emulator_feedback_icon.setVisible(False)
        else:
            self._emulator_feedback_icon.setPixmap(std_icon.pixmap(24, 24))
            self._emulator_feedback_icon.setVisible(True)
        self._emulator_feedback_label.setText(message)
        self._emulator_feedback_box.setVisible(True)
        if hasattr(self, "_emulator_feedback_timer"):
            self._emulator_feedback_timer.stop()
            self._emulator_feedback_timer.start(duration_ms)
        self.statusBar().showMessage(message, duration_ms)

    def _hide_emulator_feedback(self) -> None:
        if not hasattr(self, "_emulator_feedback_box"):
            return
        self._emulator_feedback_box.setVisible(False)
        self._emulator_feedback_label.clear()
        if hasattr(self, "_emulator_feedback_icon"):
            self._emulator_feedback_icon.clear()
            self._emulator_feedback_icon.setVisible(False)

    def _choose_emulator_dir(self) -> None:
        base = self.le_emulator_dir.text().strip() or os.getcwd()
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de emuladores", base)
        if path:
            self.le_emulator_dir.setText(path)

    def _open_emulator_url(self) -> None:
        url = self.le_emulator_url.text().strip()
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _download_selected_emulator(self) -> None:
        base_dir = self.le_emulator_dir.text().strip()
        if not base_dir:
            QMessageBox.warning(self, "Emuladores", "Selecciona una carpeta base para los emuladores.")
            return
        system_value = self.cmb_emulator_system.currentData()
        if not system_value or system_value == "__all__":
            QMessageBox.information(self, "Emuladores", "Selecciona un sistema concreto para clasificar el emulador.")
            return
        emulator = self._current_emulator
        if not isinstance(emulator, EmulatorInfo):
            QMessageBox.information(self, "Emuladores", "Selecciona un emulador válido.")
            return
        url = emulator.url.strip()
        if not url:
            QMessageBox.warning(self, "Emuladores", "El emulador seleccionado no tiene URL de descarga.")
            return

        system_dir = os.path.join(base_dir, safe_filename(str(system_value)))
        final_dir = os.path.join(system_dir, safe_filename(emulator.name))
        os.makedirs(final_dir, exist_ok=True)

        name = self._build_download_name(url)
        delete_archive = self.chk_emulator_delete.isChecked()
        metadata = {
            "emulator_name": emulator.name,
            "system": str(system_value),
            "delete_archive": delete_archive,
        }
        download_item = DownloadItem(
            name=name,
            url=url,
            dest_dir=final_dir,
            system_name=str(system_value),
            category="emulator",
            metadata=metadata,
        )
        row = {
            "display_name": emulator.name,
            "system_name": str(system_value),
            "fmt": "Emulador",
            "size": "",
        }
        self._add_download_row(download_item, row)  # type: ignore[arg-type]
        self.manager.enqueue(download_item)
        self._bind_item_signals(download_item)
        self.items.append(download_item)
        system_label = self.cmb_emulator_system.currentText().strip() or str(system_value)
        self._show_emulator_feedback(
            f"{emulator.name} se añadió a Descargas para {system_label}.",
            kind="success",
        )


    def _download_selected_extra(self) -> None:
        base_dir = self.le_emulator_dir.text().strip()
        if not base_dir:
            QMessageBox.warning(self, "Emuladores", "Selecciona una carpeta base para los emuladores.")
            return
        system_value = self.cmb_emulator_system.currentData()
        if not system_value or system_value == "__all__":
            QMessageBox.information(self, "Emuladores", "Selecciona un sistema concreto para clasificar los archivos extra.")
            return
        emulator = self._current_emulator
        if not isinstance(emulator, EmulatorInfo):
            QMessageBox.information(self, "Emuladores", "Selecciona un emulador válido.")
            return
        selected_items = [item for item in self.list_emulator_extras.selectedItems() if item.flags() & Qt.ItemFlag.ItemIsSelectable]
        if not selected_items:
            QMessageBox.information(self, "Emuladores", "Selecciona al menos un archivo extra.")
            return

        system_dir = os.path.join(base_dir, safe_filename(str(system_value)))
        emulator_dir = os.path.join(system_dir, safe_filename(emulator.name))
        os.makedirs(emulator_dir, exist_ok=True)

        added_labels: List[str] = []
        skipped_existing = 0

        for list_item in selected_items:
            extra = list_item.data(Qt.ItemDataRole.UserRole) or {}
            if not isinstance(extra, dict):
                continue
            url = (extra.get("url") or "").strip()
            if not url:
                QMessageBox.warning(self, "Emuladores", f"El archivo extra '{list_item.text()}' no tiene una URL válida.")
                continue
            label = extra.get("label") or list_item.text() or os.path.basename(url) or "Archivo extra"
            folder_name = self._extra_folder_name(label, url)
            final_dir = os.path.join(emulator_dir, folder_name)
            os.makedirs(final_dir, exist_ok=True)

            if any(x.url == url and x.dest_dir == final_dir for x in self.items):
                logging.debug("Extra already enqueued: %s -> %s", url, final_dir)
                skipped_existing += 1
                continue

            name = self._build_download_name(url)
            metadata = {
                "emulator_name": emulator.name,
                "system": str(system_value),
                "extra_label": label,
                "folder_name": folder_name,
                "delete_archive": True,
            }
            download_item = DownloadItem(
                name=name,
                url=url,
                dest_dir=final_dir,
                system_name=str(system_value),
                category="emulator-extra",
                metadata=metadata,
            )
            row = {
                "display_name": f"{emulator.name} — {label}",
                "system_name": str(system_value),
                "fmt": folder_name,
                "size": "",
            }
            self._add_download_row(download_item, row)  # type: ignore[arg-type]
            self.manager.enqueue(download_item)
            self._bind_item_signals(download_item)
            self.items.append(download_item)
            added_labels.append(label)

        added_count = len(added_labels)
        if added_count:
            system_label = self.cmb_emulator_system.currentText().strip() or str(system_value)
            if added_count == 1:
                message = f"{added_labels[0]} de {emulator.name} se añadió a Descargas ({system_label})."
            else:
                message = f"Se añadieron {added_count} archivos extra de {emulator.name} a Descargas ({system_label})."
            if skipped_existing:
                plural = "" if skipped_existing == 1 else "s"
                message += f" {skipped_existing} elemento{plural} ya estaba en la cola."
            self._show_emulator_feedback(message, kind="success")
        elif skipped_existing:
            plural = "o" if skipped_existing == 1 else "os"
            self._show_emulator_feedback(
                f"Los archivos seleccionados ya estaban en la cola de descarg{plural}.",
                kind="info",
                duration_ms=3500,
            )

    def _handle_emulator_install(self, item: DownloadItem) -> None:
        dest_file = os.path.join(item.dest_dir, safe_filename(item.name))

        if not os.path.exists(dest_file):
            logging.warning("Archivo de emulador no encontrado tras la descarga: %s", dest_file)
            if item.row is not None and 0 <= item.row < self.table_dl.rowCount():
                self.table_dl.item(item.row, 4).setText('Error: archivo no encontrado')
            return

        delete_archive = False
        if isinstance(item.metadata, dict):
            delete_archive = bool(item.metadata.get("delete_archive"))

        self._start_extraction(
            item,
            dest_file,
            item.dest_dir,
            delete_archive=delete_archive,
            success_status='Instalado',
        )

    def _should_extract_extra(self, file_path: str) -> bool:
        path = Path(file_path)
        suffixes = [s.lower() for s in path.suffixes]
        if not suffixes:
            return False
        if suffixes[-1] in {'.zip', '.7z'}:
            return True
        if suffixes[-1] == '.tar':
            return True
        if len(suffixes) >= 2 and suffixes[-2] == '.tar' and suffixes[-1] in {'.gz', '.bz2', '.xz'}:
            return True
        return False

    def _handle_emulator_extra(self, item: DownloadItem) -> None:
        dest_file = os.path.join(item.dest_dir, safe_filename(item.name))
        if not os.path.exists(dest_file):
            logging.warning("Archivo extra no encontrado tras la descarga: %s", dest_file)
            return

        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        label = metadata.get("extra_label") or os.path.basename(dest_file)
        delete_archive = bool(metadata.get("delete_archive", True))
        extracted = False
        extraction_failed = False

        if self._should_extract_extra(dest_file):
            try:
                extract_archive(dest_file, item.dest_dir)
                extracted = True
            except Exception as exc:
                extraction_failed = True
                logging.exception("Error extracting extra archive %s", dest_file)
                QMessageBox.warning(
                    self,
                    "Emuladores",
                    f"No se pudo descomprimir {label}.\n{exc}",
                )
            else:
                if delete_archive:
                    try:
                        os.remove(dest_file)
                    except Exception:
                        logging.exception("Error deleting extra archive %s", dest_file)

        status_text = "Extra instalado" if extracted else ("Error al descomprimir" if extraction_failed else "Extra descargado")
        if item.row is not None and 0 <= item.row < self.table_dl.rowCount():
            self.table_dl.item(item.row, 4).setText(status_text)

    # --- Descargas ---
    def _build_downloads_tab(self) -> None:
        lay = QVBoxLayout(self.tab_downloads)
        logging.debug("Building downloads tab with progress table.")
        # Tabla con columnas: Nombre, Sistema, Formato, Tamaño, Estado, Progreso, Velocidad, ETA, Acciones
        self.table_dl = QTableWidget(0, 9)
        self.table_dl.setHorizontalHeaderLabels([
            "Nombre", "Sistema", "Formato", "Tamaño", "Estado", "Progreso", "Velocidad", "ETA", "Acciones"
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
    def _warn_servers_unavailable(self) -> None:
        """Muestra advertencia sobre servidores con problemas al iniciar."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Aviso de servidores")
        msg.setText(
            "Los servidores de Internet Archive están experimentando problemas y algunas descargas podrían fallar."
        )
        chk = QCheckBox("No volver a mostrar este mensaje")
        msg.setCheckBox(chk)
        msg.exec()
        if chk.isChecked():
            self.hide_server_warning = True
            self._save_config()

    def _prompt_db_missing(self) -> None:
        """Muestra advertencia y permite elegir una base de datos si no está configurada."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("BD no configurada")
        msg.setText("No se ha configurado ninguna base de datos. ¿Deseas seleccionarla ahora?")
        btn_browse = msg.addButton("Explorar…", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.exec()
        if msg.clickedButton() == btn_browse:
            self._choose_db()
            if self.le_db.text().strip():
                try:
                    self._connect_db()
                except Exception:
                    pass

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
            self.session_file = str(self._session_storage_path(d))

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
        except Exception as e:
            QMessageBox.critical(self, "Error BD", str(e))

    def _load_filters(self) -> None:
        """Carga los valores de los filtros (sistemas, idiomas, regiones, formatos) en los combobox."""
        assert self.db
        self.cmb_system.clear(); [self.cmb_system.addItem(n, i) for i,n in self.db.get_systems()]
        self.cmb_lang.clear();   [self.cmb_lang.addItem(c, i) for i,c in self.db.get_languages()]
        self.cmb_region.clear(); [self.cmb_region.addItem(c, i) for i,c in self.db.get_regions()]
        self.cmb_fmt.clear();    [self.cmb_fmt.addItem(x) for x in self.db.get_formats()]

    def _default_server_index(self, servers: List[str]) -> int:
        """Devuelve el índice de 'myrient' si está en la lista de servidores."""
        for idx, srv in enumerate(servers):
            if srv.lower() == "myrient":
                return idx
        return 0

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
        region_id = self.cmb_region.currentData()
        fmt_val = self.cmb_fmt.currentText(); fmt = None if fmt_val == 'Todos' else fmt_val
        try:
            rows = self.db.search_links(text, sys_id, lang_id, region_id, fmt)
            logging.debug(
                f"Search returned {len(rows)} rows for '{text}' with filters system={sys_id}, lang={lang_id}, region={region_id}, fmt={fmt}."
            )
        except Exception as e:
            logging.exception("Error during search: %s", e)
            QMessageBox.critical(self, "Búsqueda", str(e))
            return
        # Agrupar por rom_id
        groups: dict[int, dict] = {}
        for r in rows:
            rom_id = r["rom_id"]
            group = groups.setdefault(rom_id, {"name": r["rom_name"], "rows": [], "system_name": r["system_name"]})
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
            group["selected_server"] = self._default_server_index(servers)
            group["selected_format"] = 0
            group["selected_lang"] = 0
        self.search_groups = groups
        # Mostrar resultados agrupados
        self._display_grouped_results()

    def _build_download_name(self, url: str) -> str:
        """Devuelve el nombre de archivo original decodificando la URL."""
        path = urlsplit(url).path
        base = os.path.basename(path) or "archivo"
        base = unquote(base)
        return safe_filename(base)

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
            label = r["label"] if "label" in r.keys() else None
            rom_name = r["rom_name"] if "rom_name" in r.keys() else None
            fmt_val = r["fmt"] if "fmt" in r.keys() else None
            base_display = rom_name or label or os.path.basename(r["url"]) or "archivo"
            name = self._build_download_name(r["url"])
            expected_hash = r["hash"] if "hash" in r.keys() else None
            dest_dir = save_dir
            sys_name = r["system_name"] if "system_name" in r.keys() else ""
            if self.chk_create_sys_dirs.isChecked():
                if sys_name:
                    dest_dir = os.path.join(dest_dir, safe_filename(sys_name))
            item = DownloadItem(name=name, url=r["url"], dest_dir=dest_dir, expected_hash=expected_hash, system_name=sys_name)
            # Preparar un diccionario para mostrar el nombre de la ROM en la tabla
            row_data = {
                'server': r['server'] or '',
                'fmt': fmt_val or '',
                'size': r['size'] or '',
                'system_name': sys_name,
                'display_name': rom_name or base_display,
                'rom_name': rom_name or base_display,
            }
            self._add_download_row(item, row_data)  # type: ignore[arg-type]
            self.manager.add(item)
            self._bind_item_signals(item)
            self.items.append(item)

    def _add_download_row(self, item: DownloadItem, src_row: sqlite3.Row, loaded: bool = False) -> None:
        """
        Inserta una nueva fila en la tabla de descargas para el item dado y configura
        los botones de pausa, reanudación y cancelación o reinicio.
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
        # Sistema, formato y tamaño
        # src_row puede ser dict o Row; utilizar get si es dict
        system = ''
        fmt = ''
        size = ''
        if isinstance(src_row, dict):
            system = src_row.get('system_name', '') or ''
            fmt = src_row.get('fmt', '') or ''
            size = src_row.get('size', '') or ''
        elif hasattr(src_row, '__getitem__'):
            try:
                system = src_row["system_name"] or ''
                fmt = src_row["fmt"] or ''
                size = src_row["size"] or ''
            except Exception:
                pass
        if not system:
            system = getattr(item, 'system_name', '')
        set_item(1, system)
        set_item(2, fmt)
        set_item(3, size)
        set_item(4, "En cola")
        prog = QProgressBar(); prog.setRange(0, 100); prog.setValue(0); self.table_dl.setCellWidget(row, 5, prog)
        set_item(6, '-')
        set_item(7, '-')
        # Acciones: añadir botones de Pausar, Reanudar, Cancelar/Reiniciar, Eliminar y Abrir
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
            if loaded:
                b_can.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
            else:
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
        b_can.setToolTip("Reiniciar descarga" if loaded else "Cancelar descarga")
        b_del.setToolTip("Eliminar descarga")
        b_open.setToolTip("Abrir ubicación")
        # Añadir botones al layout
        h.addWidget(b_pause); h.addWidget(b_res); h.addWidget(b_can)
        h.addWidget(b_del); h.addWidget(b_open)
        self.table_dl.setCellWidget(row, 8, w)
        # Conectar señales a acciones apropiadas
        b_pause.clicked.connect(lambda _=False, it=item: self.manager.pause(it))
        b_res.clicked.connect(lambda _=False, it=item: self.manager.resume(it))
        if loaded:
            b_can.clicked.connect(lambda _=False, it=item, btn=b_can: self._restart_item(it, btn))
        else:
            b_can.clicked.connect(lambda _=False, it=item: self._cancel_item(it))
        b_del.clicked.connect(lambda _=False, it=item: self._delete_single_item(it))
        b_open.clicked.connect(lambda _=False, it=item: self._open_item_location(it))

    def _bind_item_signals(self, item: DownloadItem) -> None:
        """Enlaza las señales del ``DownloadTask`` con la interfaz."""

        def do_bind() -> bool:
            if item.task is None:
                return False
            item.task.signals.progress.connect(
                lambda d, t, s, eta, st, it=item: self._update_progress(it, d, t, s, eta, st)
            )
            item.task.signals.finished_ok.connect(
                lambda p, it=item: self._on_done(it, True, p)
            )
            item.task.signals.failed.connect(
                lambda m, it=item: self._on_done(it, False, m)
            )
            return True

        if not do_bind():
            tmr = QTimer(self)
            tmr.setInterval(200)
            tmr.timeout.connect(lambda: do_bind() and tmr.stop())
            setattr(item, "_bind_timer", tmr)
            tmr.start()

    def _restart_item(self, it: DownloadItem, btn: QPushButton) -> None:
        """Reinicia la descarga para un elemento previamente cargado."""
        try:
            final_path = os.path.join(it.dest_dir, it.name)
            part_path = final_path + '.part'
            if os.path.exists(final_path):
                os.remove(final_path)
            if os.path.exists(part_path):
                os.remove(part_path)
        except Exception:
            pass
        if it.row is not None and 0 <= it.row < self.table_dl.rowCount():
            self.table_dl.item(it.row, 4).setText('En cola')
            prog: QProgressBar = self.table_dl.cellWidget(it.row, 5)  # type: ignore
            prog.setValue(0)
            prog.setStyleSheet('')
            self.table_dl.item(it.row, 6).setText('-')
            self.table_dl.item(it.row, 7).setText('-')
        it.extract_task = None
        style = QApplication.style()
        try:
            btn.clicked.disconnect()
        except Exception:
            pass
        try:
            btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton))
        except Exception:
            pass
        btn.setToolTip('Cancelar descarga')
        btn.clicked.connect(lambda _=False, it=it: self._cancel_item(it))
        self.manager.add(it)
        self._bind_item_signals(it)

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
        if it.row is None or it.row < 0 or it.row >= self.table_dl.rowCount():
            return

        current_status = self.table_dl.item(it.row, 4).text()
        if not ok:
            if current_status.startswith('Integridad'):
                logging.debug("Download finished for %s with integrity status (error reported separately): %s", it.name, current_status)
            else:
                self.table_dl.item(it.row, 4).setText(f"Error: {msg}")
                logging.debug("Download failed for %s: %s", it.name, msg)
            return

        category = getattr(it, 'category', '')
        if category == 'emulator':
            self._handle_emulator_install(it)

            return
        if category == 'emulator-extra':
            self._handle_emulator_extra(it)
            return

        start_rom_extraction = False
        if self.chk_extract_after.isChecked():
            system = getattr(it, 'system_name', '')
            if 'mame' not in system.lower():
                start_rom_extraction = True

        if start_rom_extraction:
            logging.debug("Download finished for %s, starting archive extraction", it.name)
            self.table_dl.item(it.row, 4).setText('Preparando extracción')
            self._start_extraction(
                it,
                archive_path,
                it.dest_dir,
                delete_archive=self.chk_delete_after.isChecked(),
                success_status='Extraído',
            )
            return

        if current_status.startswith('Integridad'):
            logging.debug("Download finished for %s with integrity status: %s", it.name, current_status)
        else:
            self.table_dl.item(it.row, 4).setText('Completado')
            logging.debug("Download finished for %s: ok=%s, msg=%s", it.name, ok, msg)

    def _start_extraction(
        self,
        item: DownloadItem,
        archive_path: str,
        dest_dir: str,
        *,
        delete_archive: bool = False,
        success_status: str = 'Extraído',
    ) -> None:
        """Lanza la extracción del archivo asociado a ``item`` en segundo plano."""

        if not os.path.exists(archive_path):
            logging.warning("Archivo para extraer no encontrado: %s", archive_path)
            if item.row is not None and 0 <= item.row < self.table_dl.rowCount():
                self.table_dl.item(item.row, 4).setText('Error: archivo no encontrado para extraer')
            return

        if item.row is None or item.row < 0 or item.row >= self.table_dl.rowCount():
            logging.debug("Extraction requested for %s but row is invalid", item.name)
            return

        prog: QProgressBar = self.table_dl.cellWidget(item.row, 5)  # type: ignore
        prog.setRange(0, 100)
        prog.setValue(0)
        prog.setStyleSheet('QProgressBar::chunk { background-color: #4caf50; }')
        self.table_dl.item(item.row, 6).setText('-')
        self.table_dl.item(item.row, 7).setText('-')

        task = ExtractionTask(archive_path, dest_dir)
        item.extract_task = task

        task.signals.progress.connect(
            lambda done, total, _speed, _eta, status, it=item: self._update_progress(it, done, total, 0.0, 0.0, status)
        )
        task.signals.finished_ok.connect(
            lambda _res, it=item, arc=archive_path, delete=delete_archive, st=success_status: self._on_extraction_finished(
                it, arc, delete, st
            )
        )
        task.signals.failed.connect(
            lambda message, it=item, arc=archive_path: self._on_extraction_failed(it, message, arc)
        )
        self.pool.start(task)

    def _on_extraction_finished(
        self,
        item: DownloadItem,
        archive_path: str,
        delete_archive: bool,
        success_status: str,
    ) -> None:
        """Actualiza la interfaz cuando la extracción finaliza correctamente."""

        item.extract_task = None
        if item.row is not None and 0 <= item.row < self.table_dl.rowCount():
            self.table_dl.item(item.row, 4).setText(success_status)
            prog: QProgressBar = self.table_dl.cellWidget(item.row, 5)  # type: ignore
            prog.setStyleSheet('')
            prog.setValue(100)
            self.table_dl.item(item.row, 6).setText('-')
            self.table_dl.item(item.row, 7).setText('-')

        if delete_archive and os.path.exists(archive_path):
            try:
                os.remove(archive_path)
            except Exception:
                logging.exception("Error deleting archive %s", archive_path)

    def _on_extraction_failed(self, item: DownloadItem, message: str, archive_path: str) -> None:
        """Muestra el error en la tabla cuando la extracción falla."""

        item.extract_task = None
        logging.error("Extraction failed for %s: %s", item.name, message)
        if item.row is not None and 0 <= item.row < self.table_dl.rowCount():
            self.table_dl.item(item.row, 4).setText(f"Error extracción: {message}")
            prog: QProgressBar = self.table_dl.cellWidget(item.row, 5)  # type: ignore
            prog.setStyleSheet('')
            self.table_dl.item(item.row, 6).setText('-')
            self.table_dl.item(item.row, 7).setText('-')

        if getattr(item, 'category', '') == 'emulator':
            QMessageBox.warning(
                self,
                'Emuladores',
                f"No se pudo descomprimir {os.path.basename(archive_path)}.\n{message}",
            )

    def _cancel_item(self, it: DownloadItem) -> None:
        """
        Maneja la cancelación de un elemento de la cola. Si el usuario tiene
        activada la opción de no confirmar, se cancela directamente. De lo
        contrario se muestra un cuadro de diálogo preguntando si desea
        cancelar con un checkbox para recordar la elección.
        """
        # Si ya se ha solicitado no confirmar, cancelar sin preguntar
        logging.debug("Attempting to cancel download: %s", it.name)
        if self.no_confirm_cancel:
            self.manager.cancel(it)
            if it.row is not None and 0 <= it.row < self.table_dl.rowCount():
                self.table_dl.item(it.row, 4).setText("Cancelado")
            return
        # Mostrar diálogo de confirmación
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setWindowTitle("Cancelar descarga")
        msg_box.setText("¿Seguro que quieres cancelar la descarga?")
        # Añadir checkbox para no volver a preguntar
        chk = QCheckBox("No volver a preguntar")
        msg_box.setCheckBox(chk)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        res = msg_box.exec()
        if res == QMessageBox.StandardButton.Yes:
            # Actualizar preferencia si el usuario marcó no preguntar
            if chk.isChecked():
                self.no_confirm_cancel = True
            # Cancelar la descarga
            self.manager.cancel(it)
            if it.row is not None and 0 <= it.row < self.table_dl.rowCount():
                self.table_dl.item(it.row, 4).setText("Cancelado")
        # Guardar preferencia de cancelación
        self._save_config()

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

    def _remove_item_files(self, it: DownloadItem) -> None:
        """Elimina el archivo final y el parcial para un item de descarga."""
        try:
            dest_dir = os.path.expanduser(it.dest_dir)
            filename = safe_filename(it.name)
            final_path = os.path.join(dest_dir, filename)
            part_path = final_path + '.part'
            for path in (final_path, part_path):
                if os.path.exists(path):
                    os.remove(path)
            logging.debug("Deleted files for %s", it.name)
        except Exception:
            logging.exception("Error deleting files for %s", it.name)

    def _delete_single_item(self, it: DownloadItem) -> None:
        """
        Elimina un único elemento de la tabla de descargas y de la cola. Se
        muestra un cuadro de diálogo para confirmar la operación y opcionalmente
        borrar el fichero descargado.
        """
        logging.debug(
            "Requesting deletion for single download: %s (row=%s, dest=%s, has_task=%s)",
            it.name,
            it.row,
            it.dest_dir,
            it.task is not None,
        )
        # Dialogo de confirmación
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Eliminar descarga")
        msg_box.setText("¿Seguro que quieres eliminar esta descarga?")
        chk_del_file = QCheckBox("También eliminar el fichero (si existe)")
        msg_box.setCheckBox(chk_del_file)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        res = msg_box.exec()
        if res != QMessageBox.StandardButton.Yes:
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
        had_task = it.task is not None
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
            # Liberar referencia a la tarea
            it.task = None
        if it.extract_task is not None:
            try:
                it.extract_task.signals.progress.disconnect()
            except Exception:
                logging.exception("Error disconnecting extraction progress for %s", it.name)
            try:
                it.extract_task.signals.finished_ok.disconnect()
            except Exception:
                logging.exception("Error disconnecting extraction finished for %s", it.name)
            try:
                it.extract_task.signals.failed.disconnect()
            except Exception:
                logging.exception("Error disconnecting extraction failed for %s", it.name)
            it.extract_task = None
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
            if had_task:
                QTimer.singleShot(500, lambda it=it: self._remove_item_files(it))
            else:
                self._remove_item_files(it)
        # Guardar sesión después de eliminar
        logging.debug("Saving session after deleting %s", it.name)
        self._save_session_silent()
        logging.debug("Session saved after deleting %s", it.name)

    def _delete_selected_items(self) -> None:
        """Elimina todas las filas seleccionadas en la tabla de descargas."""
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
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Eliminar descargas")
        msg_box.setText("¿Seguro que quieres eliminar las descargas seleccionadas?")
        chk_del_file = QCheckBox("También eliminar los ficheros (si existen)")
        msg_box.setCheckBox(chk_del_file)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        res = msg_box.exec()
        if res != QMessageBox.StandardButton.Yes:
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
            had_task = it.task is not None
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
            if it.extract_task is not None:
                try:
                    it.extract_task.signals.progress.disconnect()
                except Exception:
                    logging.exception("Error disconnecting extraction progress for %s", it.name)
                try:
                    it.extract_task.signals.finished_ok.disconnect()
                except Exception:
                    logging.exception("Error disconnecting extraction finished for %s", it.name)
                try:
                    it.extract_task.signals.failed.disconnect()
                except Exception:
                    logging.exception("Error disconnecting extraction failed for %s", it.name)
                it.extract_task = None
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
                if had_task:
                    QTimer.singleShot(500, lambda it=it: self._remove_item_files(it))
                else:
                    self._remove_item_files(it)
        # Guardar sesión tras eliminación múltiple
        logging.debug("Saving session after batch deletion of %d items", len(items_to_delete))
        self._save_session_silent()
        logging.debug("Session saved after batch deletion")

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
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Cancelar descargas")
            if len(items) == 1:
                msg_box.setText("¿Seguro que quieres cancelar la descarga seleccionada?")
            else:
                msg_box.setText("¿Seguro que quieres cancelar las descargas seleccionadas?")
            chk = QCheckBox("No volver a preguntar")
            msg_box.setCheckBox(chk)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg_box.setDefaultButton(QMessageBox.StandardButton.No)
            res = msg_box.exec()
            if res == QMessageBox.StandardButton.Yes:
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

    def _check_background_downloads(self) -> None:
        """Cierra la aplicación cuando las descargas en segundo plano finalizan."""
        if self.background_downloads and not self.manager._active and not self.manager._queue:
            try:
                self._save_session_silent()
                self._save_config()
            except Exception:
                pass
            if self.tray_icon and self.tray_icon.isVisible():
                self.tray_icon.hide()
            QApplication.instance().quit()

    # --- Persistencia de sesión (Ajustes de descarga) ---
    def _session_path(self) -> str:
        """Devuelve la ruta del fichero de sesión dentro de ``sessions``."""

        if self.session_file:
            path = Path(self.session_file)
        else:
            path = self._session_storage_path(self.le_dir.text().strip() or None)
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _save_session(self) -> None:
        """Guarda la sesión actual de descargas a disco."""
        data = []
        for it in self.items:
            entry = {
                "name": it.name,
                "url": it.url,
                "dest": it.dest_dir,
                "hash": it.expected_hash,
                "system": getattr(it, 'system_name', ''),
                "category": getattr(it, 'category', ''),
            }
            metadata = getattr(it, 'metadata', None)
            if isinstance(metadata, dict):
                entry["metadata"] = metadata
            data.append(entry)
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
                expected_hash = d.get('hash')
                system = d.get('system', '')
                category = d.get('category', '')
                metadata = d.get('metadata') if isinstance(d.get('metadata'), dict) else None
                if not (name and url and dest_dir):
                    continue
                it = DownloadItem(
                    name=name,
                    url=url,
                    dest_dir=dest_dir,
                    expected_hash=expected_hash,
                    system_name=system,
                    category=category,
                    metadata=metadata,
                )
                # Evitar duplicados
                if any(x.name == name for x in self.items):
                    continue
                final_path = os.path.join(dest_dir, it.name)
                part_path = final_path + '.part'
                dummy_row = {
                    'system_name': system,
                    'fmt': '',
                    'size': '',
                }
                if category == 'emulator':
                    dummy_row['fmt'] = 'Emulador'
                    if metadata:
                        dummy_row['display_name'] = metadata.get('emulator_name', name)
                elif category == 'emulator-extra':
                    folder_name = metadata.get('folder_name', 'Archivos extras') if metadata else 'Archivos extras'
                    dummy_row['fmt'] = folder_name
                    if metadata:
                        extra_label = metadata.get('extra_label', name)
                        emulator_name = metadata.get('emulator_name', '')
                        dummy_row['display_name'] = f"{emulator_name} — {extra_label}".strip(" —")
                if os.path.exists(final_path):
                    self._add_download_row(it, dummy_row, loaded=True)  # type: ignore[arg-type]
                    self.items.append(it)
                    if it.row is not None:
                        self.table_dl.item(it.row, 4).setText('Completado')
                        prog: QProgressBar = self.table_dl.cellWidget(it.row, 5)  # type: ignore
                        prog.setValue(100)
                elif os.path.exists(part_path):
                    self._add_download_row(it, dummy_row, loaded=False)  # type: ignore[arg-type]
                    self.items.append(it)
                    self.manager.add(it)
                    self._bind_item_signals(it)
                    self._bind_item_signals(it)
                else:
                    self._add_download_row(it, dummy_row, loaded=True)  # type: ignore[arg-type]
                    self.items.append(it)
                    if it.row is not None:
                        self.table_dl.item(it.row, 4).setText('Error: fichero no encontrado')
                        prog: QProgressBar = self.table_dl.cellWidget(it.row, 5)  # type: ignore
                        prog.setValue(0)
            QMessageBox.information(self, 'Sesión', 'Sesión cargada')
        except Exception as e:
            QMessageBox.critical(self, 'Sesión', str(e))

    # --- Carga/salva de sesión silenciosa (sin mensajes) ---
    def _save_session_silent(self) -> None:
        """Guarda la sesión actual de descargas en el fichero sin mostrar diálogos."""
        try:
            data = []
            for it in self.items:
                entry = {
                    "name": it.name,
                    "url": it.url,
                    "dest": it.dest_dir,
                    "hash": it.expected_hash,
                    "system": getattr(it, 'system_name', ''),
                    "category": getattr(it, 'category', ''),
                }
                metadata = getattr(it, 'metadata', None)
                if isinstance(metadata, dict):
                    entry["metadata"] = metadata
                data.append(entry)
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
                expected_hash = d.get('hash')
                system = d.get('system', '')
                category = d.get('category', '')
                metadata = d.get('metadata') if isinstance(d.get('metadata'), dict) else None
                if not (name and url and dest_dir):
                    continue
                it = DownloadItem(
                    name=name,
                    url=url,
                    dest_dir=dest_dir,
                    expected_hash=expected_hash,
                    system_name=system,
                    category=category,
                    metadata=metadata,
                )
                # Evitar duplicados
                if any(x.name == name for x in self.items):
                    continue
                final_path = os.path.join(dest_dir, it.name)
                part_path = final_path + '.part'
                dummy_row = {
                    'system_name': system,
                    'fmt': '',
                    'size': '',
                }
                if category == 'emulator':
                    dummy_row['fmt'] = 'Emulador'
                    if metadata:
                        dummy_row['display_name'] = metadata.get('emulator_name', name)
                elif category == 'emulator-extra':
                    folder_name = metadata.get('folder_name', 'Archivos extras') if metadata else 'Archivos extras'
                    dummy_row['fmt'] = folder_name
                    if metadata:
                        extra_label = metadata.get('extra_label', name)
                        emulator_name = metadata.get('emulator_name', '')
                        dummy_row['display_name'] = f"{emulator_name} — {extra_label}".strip(" —")
                if os.path.exists(final_path):
                    self._add_download_row(it, dummy_row, loaded=True)  # type: ignore[arg-type]
                    self.items.append(it)
                    if it.row is not None:
                        self.table_dl.item(it.row, 4).setText('Completado')
                        prog: QProgressBar = self.table_dl.cellWidget(it.row, 5)  # type: ignore
                        prog.setValue(100)
                elif os.path.exists(part_path):
                    self._add_download_row(it, dummy_row, loaded=False)  # type: ignore[arg-type]
                    self.items.append(it)
                    self.manager.add(it)
                else:
                    self._add_download_row(it, dummy_row, loaded=True)  # type: ignore[arg-type]
                    self.items.append(it)
                    if it.row is not None:
                        self.table_dl.item(it.row, 4).setText('Error: fichero no encontrado')
                        prog: QProgressBar = self.table_dl.cellWidget(it.row, 5)  # type: ignore
                        prog.setValue(0)
        except Exception:
            pass

    # --- Guardar/cargar configuración y cesta ---
    def _save_config(self) -> None:
        """Guarda la configuración de la aplicación en ``config/settings.json``."""

        try:
            basket_data = []
            for rom_id, item in self.basket_items.items():
                basket_data.append({
                    'rom_id': rom_id,
                    'selected_server': item.get('selected_server', 0),
                    'selected_format': item.get('selected_format', 0),
                    'selected_lang': item.get('selected_lang', 0),
                })

            payload = {
                'db_path': self.le_db.text().strip(),
                'download_dir': self.le_dir.text().strip(),
                'concurrency': self.spin_conc.value(),
                'chk_extract_after': self.chk_extract_after.isChecked(),
                'chk_delete_after': self.chk_delete_after.isChecked(),
                'chk_create_sys_dirs': self.chk_create_sys_dirs.isChecked(),
                'emulator_dir': self.le_emulator_dir.text().strip(),
                'emulator_delete_archive': self.chk_emulator_delete.isChecked(),
                'basket_items': basket_data,
                'no_confirm_cancel': self.no_confirm_cancel,
                'hide_server_warning': self.hide_server_warning,
                'session_file': self.session_file,
            }

            path = self._config_file_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except Exception:
            logging.exception('Failed to save configuration', exc_info=True)

    def _load_config(self) -> None:
        """Carga la configuración desde ``config/settings.json``."""

        try:
            data: dict = {}
            path = self._config_file_path()
            if path.exists():
                with path.open('r', encoding='utf-8') as fh:
                    data = json.load(fh)

            db_path = str(data.get('db_path', '') or '')
            download_dir = str(data.get('download_dir', '') or '')
            conc = int(data.get('concurrency', 3) or 3)
            chk_extract = bool(data.get('chk_extract_after', False))
            chk_del = bool(data.get('chk_delete_after', False))
            chk_sys = bool(data.get('chk_create_sys_dirs', False))
            emulator_dir = str(data.get('emulator_dir', '') or '')
            emulator_delete = bool(data.get('emulator_delete_archive', False))

            self.le_db.setText(db_path)
            self.le_dir.setText(download_dir)
            self.spin_conc.setValue(conc)
            self.chk_extract_after.setChecked(chk_extract)
            self.chk_delete_after.setChecked(chk_del)
            self.chk_delete_after.setEnabled(chk_extract)
            self.chk_create_sys_dirs.setChecked(chk_sys)
            self.le_emulator_dir.setText(emulator_dir)
            self.chk_emulator_delete.setChecked(emulator_delete)

            session_file = data.get('session_file')
            if isinstance(session_file, str) and session_file.strip():
                self.session_file = session_file
            else:
                self.session_file = str(self._session_storage_path(download_dir))

            basket_data = data.get('basket_items', [])
            if isinstance(basket_data, str):
                self._saved_basket_json = basket_data
            elif isinstance(basket_data, list):
                self._saved_basket_json = json.dumps(basket_data)
            else:
                self._saved_basket_json = ''

            self.no_confirm_cancel = bool(data.get('no_confirm_cancel', False))
            self.hide_server_warning = bool(data.get('hide_server_warning', False))
        except Exception:
            logging.exception('Failed to load configuration', exc_info=True)
            self._saved_basket_json = ''

    def _load_basket_from_saved(self) -> None:
        """Restaura la cesta guardada a partir del JSON almacenado en configuración."""
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
                    'rows': group_rows,
                    'system_name': links[0].get('system_name', '')
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
                group['selected_server'] = self._default_server_index(servers)
                group['selected_format'] = 0
                group['selected_lang'] = 0
                # Ajustar índices guardados
                sel_srv = d.get('selected_server', group['selected_server'])
                sel_fmt = d.get('selected_format', 0)
                sel_lang = d.get('selected_lang', 0)
                # Validar índices
                if sel_srv is None or sel_srv >= len(servers) or sel_srv < 0:
                    sel_srv = group['selected_server']
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
            # Columna 1: sistema
            sys_item = QTableWidgetItem(item['group'].get('system_name', '') or '')
            self.table_basket.setItem(row, 1, sys_item)
            # Columna 2: selector de servidor
            combo_srv = QComboBox()
            for srv in item['group']['servers']:
                combo_srv.addItem(srv or "")
            srv_idx = item.get('selected_server', 0)
            if srv_idx is not None and srv_idx < combo_srv.count():
                combo_srv.setCurrentIndex(srv_idx)
            combo_srv.setProperty('row_idx', row)
            combo_srv.setProperty('rom_id', rom_id)
            combo_srv.currentIndexChanged.connect(self._basket_server_changed)
            self.table_basket.setCellWidget(row, 2, combo_srv)
            # Columna 3: selector de formato (depende del servidor)
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
            self.table_basket.setCellWidget(row, 3, combo_fmt)
            # Columna 4: selector de idiomas (depende de servidor y formato)
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
            self.table_basket.setCellWidget(row, 4, combo_lang)
            # Columna 5: botones de acción (Añadir, Eliminar)
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
            self.table_basket.setCellWidget(row, 5, w)

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
            # Columna 1: sistema
            sys_item = QTableWidgetItem(group.get("system_name", "") or "")
            self.table_results.setItem(row, 1, sys_item)
            # Columna 2: selector de servidor
            combo_srv = QComboBox()
            for srv in group["servers"]:
                combo_srv.addItem(srv or "")
            # Selección actual
            combo_srv.setCurrentIndex(group.get("selected_server", 0))
            combo_srv.setProperty('rom_id', rom_id)
            combo_srv.setProperty('row_idx', row)
            combo_srv.currentIndexChanged.connect(self._group_server_changed)
            self.table_results.setCellWidget(row, 2, combo_srv)
            # Columna 3: selector de formato (depende del servidor)
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
            self.table_results.setCellWidget(row, 3, combo_fmt)
            # Columna 4: selector de idiomas (depende de servidor y formato)
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
            self.table_results.setCellWidget(row, 4, combo_lang)
            # Columna 5: botón para añadir a la cesta
            btn_add = QPushButton("Añadir")
            btn_add.setProperty('rom_id', rom_id)
            btn_add.setProperty('row_idx', row)
            btn_add.clicked.connect(self._add_group_to_basket)
            self.table_results.setCellWidget(row, 5, btn_add)

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
        fmt_combo: QComboBox = self.table_results.cellWidget(row_idx, 3)  # type: ignore
        fmt_combo.blockSignals(True)
        fmt_combo.clear()
        fmt_list = group['formats_by_server'].get(srv_name, [])
        for fmt in fmt_list:
            fmt_combo.addItem(fmt or "")
        fmt_combo.setCurrentIndex(0 if fmt_list else 0)
        fmt_combo.blockSignals(False)
        # Idiomas
        lang_combo: QComboBox = self.table_results.cellWidget(row_idx, 4)  # type: ignore
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
        lang_combo: QComboBox = self.table_results.cellWidget(row_idx, 4)  # type: ignore
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

    def _process_basket_item_to_downloads(self, rom_id: int, base_dir: str) -> None:
        """Convierte un elemento de la cesta en una descarga."""
        if rom_id not in self.basket_items:
            return
        item = self.basket_items[rom_id]
        group = item['group']
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
        logging.debug(
            "Adding from basket to downloads: ROM %s, server=%s, fmt=%s, lang=%s",
            group['name'], srv_name, fmt_name, lang_name,
        )
        final_dir = base_dir
        sys_name = group.get('system_name', '')
        if self.chk_create_sys_dirs.isChecked() and sys_name:
            final_dir = os.path.join(final_dir, safe_filename(sys_name))
        name = self._build_download_name(row_data['url'])
        expected_hash = row_data['hash'] if 'hash' in row_data.keys() else None
        download_item = DownloadItem(name=name, url=row_data['url'], dest_dir=final_dir, expected_hash=expected_hash, system_name=sys_name)
        src_row = {
            'server': row_data['server'] or '',
            'fmt': row_data['fmt'] or '',
            'size': row_data['size'] or '',
            'system_name': sys_name,
            'display_name': row_data['rom_name'] or group['name'],
            'rom_name': row_data['rom_name'] or group['name'],
        }
        self._add_download_row(download_item, src_row)  # type: ignore[arg-type]
        self.manager.add(download_item)
        self._bind_item_signals(download_item)
        self.items.append(download_item)
        del self.basket_items[rom_id]

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
        dest_dir = self.le_dir.text().strip()
        if not dest_dir:
            QMessageBox.warning(self, "Descargas", "Selecciona una carpeta de descargas en la pestaña de Ajustes.")
            return
        self._process_basket_item_to_downloads(int(rom_id), dest_dir)
        self._refresh_basket_table()

    def _basket_add_all_to_downloads(self) -> None:
        """Añade todas las ROM de la cesta a la cola de descargas."""
        dest_dir = self.le_dir.text().strip()
        if not dest_dir:
            QMessageBox.warning(self, "Descargas", "Selecciona una carpeta de descargas en la pestaña de Ajustes.")
            return
        for rom_id in list(self.basket_items.keys()):
            self._process_basket_item_to_downloads(rom_id, dest_dir)
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
                    "selected_server": self._default_server_index(servers),
                    "selected_format": 0,
                    "selected_lang": 0,
                    "system_name": links[0].get('system_name', ''),
                }
            sel_srv = group.get('selected_server', 0)
            self.basket_items[rom_id] = {
                'name': rom_name,
                'links': links,
                'group': group,
                'selected_server': sel_srv,
                'selected_format': 0,
                'selected_lang': 0,
            }
        # Actualizar la tabla de la cesta después de añadir los elementos
        self._refresh_basket_table()

    # --- Evento de cierre ---
    def closeEvent(self, event) -> None:
        """Pregunta al usuario si desea salir cuando hay descargas activas."""
        if self.manager._active or self.manager._queue:
            box = QMessageBox(self)
            box.setWindowTitle("Descargas en curso")
            box.setText("Hay descargas en curso. ¿Quieres salir?")
            box.setIcon(QMessageBox.Icon.Warning)
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            chk = QCheckBox("Seguir descargando en segundo plano")
            box.setCheckBox(chk)
            resp = box.exec()
            if resp == QMessageBox.StandardButton.Yes:
                if chk.isChecked():
                    if self._enter_background_mode():
                        self.hide()
                        event.ignore()
                        return
            else:
                event.ignore()
                return
        try:
            # Guardar sesión y configuración de manera silenciosa
            self._save_session_silent()
            self._save_config()
        except Exception:
            pass
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.hide()
        self.background_downloads = False
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
