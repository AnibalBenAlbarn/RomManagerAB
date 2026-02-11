"""Widgets y ventanas de la interfaz gráfica del gestor de ROMs."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit, unquote
import json
import logging
import sqlite3
import math
import subprocess
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Sequence

if __package__ is None or __package__ == "":
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    __package__ = "rom_manager.gui"

from PyQt6.QtCore import Qt, QThreadPool, QTimer, QUrl, QEvent, QObject
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QGroupBox, QFrame, QComboBox, QSpinBox, QTableView, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QProgressBar, QCheckBox, QTabWidget,
    QAbstractItemView, QListWidget, QListWidgetItem, QMenu, QStyle, QSystemTrayIcon,
    QAbstractButton, QToolButton, QDialog, QDialogButtonBox, QTextEdit
)
from PyQt6.QtGui import QDesktopServices, QIcon, QKeyEvent, QGuiApplication

from rom_manager.database import Database
from rom_manager.models import LinksTableModel
from rom_manager.download import DownloadManager, DownloadItem, ExtractionTask
from rom_manager.emulators import EmulatorInfo, get_all_systems, get_emulator_catalog, get_emulators_for_system
from rom_manager.paths import config_path, session_path

from rom_manager.console_input import PygameConsoleController
from rom_manager.utils import safe_filename, extract_archive, resource_path


# -----------------------------
# Ventana principal con pestañas (paridad JavaFX)
# -----------------------------

class MainWindow(QMainWindow):
    """
    Ventana principal de la aplicación. Configura todas las pestañas y
    gestiona la interacción del usuario con la base de datos, el
    gestor de descargas y la visualización de resultados.
    """

    _KNOWN_ROM_EXTENSIONS = {
        ".7z",
        ".zip",
        ".rar",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".zst",
        ".iso",
        ".cso",
        ".wbfs",
        ".wdf",
        ".wad",
        ".cia",
        ".nds",
        ".3ds",
        ".xci",
        ".nsp",
        ".gba",
        ".gbc",
        ".gb",
        ".nes",
        ".sfc",
        ".smc",
        ".z64",
        ".n64",
        ".v64",
        ".chd",
        ".bin",
        ".cue",
        ".img",
        ".mdf",
        ".mds",
        ".ccd",
        ".sub",
        ".dmg",
        ".pkg",
        ".apk",
        ".pbp",
        ".vpk",
        ".elf",
        ".dol",
        ".xiso",
        ".adf",
        ".int",
        ".smd",
        ".001",
        ".002",
        ".003",
    }
    _ARCADE_SYSTEM_ID = 32

    _RETROBAT_ROM_FOLDERS: Dict[str, str] = {
        "3do": "3DO",
        "3ds": "Nintendo 3DS",
        "actionmax": "Actionmax",
        "adam": "Coleco Adam",
        "advision": "Adventure Vision",
        "amiga500": "Amiga OCS/ECS",
        "amiga1200": "Amiga AGA",
        "amiga4000": "Amiga 4000",
        "amigacd32": "Amiga CD32",
        "amigacdtv": "Amiga CDTV",
        "amstradcpc": "Amstrad CPC",
        "apple2": "Apple II",
        "apple2gs": "Apple IIGS",
        "aquarius": "Mattel Aquarius",
        "arcadia": "Arcadia 2001 (Gen 2 Arcade)",
        "atari2600": "Atari 2600",
        "atari5200": "Atari 5200",
        "atari7800": "Atari 7800",
        "atari800": "Atari 800",
        "atarist": "Atari ST",
        "cgenius": "C-Genie",
        "cavestory": "Cave Story (port)",
        "cdi": "Philips CD-i",
        "cps1": "Capcom CPS-1 Arcade",
        "cps2": "Capcom CPS-2 Arcade",
        "cps3": "Capcom CPS-3 Arcade",
        "doom3": "Doom 3 (game engine port)",
        "dos": "MS-DOS",
        "dreamcast": "Sega Dreamcast",
        "fbneo": "FinalBurn Neo Arcade",
        "fds": "Nintendo Famicom Disk System",
        "gameandwatch": "Nintendo Game & Watch",
        "gamegear": "Sega Game Gear",
        "gb": "Nintendo Game Boy",
        "gba": "Nintendo Game Boy Advance",
        "gbc": "Nintendo Game Boy Color",
        "gp32": "GamePark GP32",
        "n64": "Nintendo 64",
        "nds": "Nintendo DS",
        "neogeo": "SNK Neo Geo",
        "neogeocd": "SNK Neo Geo CD",
        "nes": "Nintendo Entertainment System",
        "psx": "Sony PlayStation (PS1)",
        "ps2": "Sony PlayStation 2",
        "psp": "Sony PlayStation Portable",
        "psvita": "Sony PlayStation Vita",
        "saturn": "Sega Saturn",
        "snes": "Super Nintendo Entertainment System",
        "megadrive": "Sega Mega Drive / Genesis",
        "megacd": "Sega Mega CD (Mega-CD)",
        "mastersystem": "Sega Master System",
        "vectrex": "Vectrex",
        "zx81": "Sinclair ZX81",
        "zxspectrum": "ZX Spectrum",
    }

    _RETROBAT_EMULATOR_FOLDERS: Dict[str, str] = {
        "3dsen": "3DS Emulator (probablemente Citra o frontend)",
        "altirra": "Altirra (Emulador Atari 8-bit)",
        "applewin": "AppleWin (Emulador Apple II)",
        "arcadeflashweb": "Arcade Flash Web (Flash Player Arcade)",
        "ares": "ARES (Multisistema)",
        "azahar": "Azahar (Frontend/Emulador)",
        "bigpemu": "BigPEmu (Emulador portátil)",
        "bizhawk": "BizHawk (Multisistema)",
        "capriceforever": "Caprice Forever (Amstrad CPC)",
        "cdogs": "cdogs SDL (Juego, no emulador)",
        "cemu": "Cemu (Wii U emulator)",
        "cgenius": "C-Genie Emulator",
        "chihiro": "Chihiro (Arcade system)",
        "citra": "Citra (Nintendo 3DS emulator)",
        "citron": "Citron (Versión avanzada Citra)",
        "corsixth": "CorsixTH (Theme Hospital engine)",
        "cxbx-reloaded": "Cxbx-Reloaded (Xbox emulator)",
        "daphne": "Daphne (Laserdisc arcade emulator)",
        "demul": "Demul (Dreamcast/Naomi/Xbox Classic)",
        "demul-old": "Demul (versión antigua)",
        "devilutionx": "DevilutionX (Diablo engine)",
        "dhewm3": "DHEWM3 (Doom 3 engine port)",
        "dolphin-emu": "Dolphin (GameCube/Wii)",
        "dolphin-triforce": "Dolphin-Triforce variant",
        "dosbox": "DOSBox (DOS emulator)",
        "duckstation": "DuckStation (PS1 emulator)",
        "eden": "Eden (PS1/PS2 frontend)",
        "eduke32": "EDuke32 (Duke Nukem)",
        "eka2l1": "EKA2L1 (Symbian emulator)",
        "fbneo": "FinalBurn Neo",
        "flycast": "Flycast (Dreamcast/Atomiswave)",
        "fpinball": "Future Pinball",
        "gemrb": "GEMRB (Baldur’s Gate engine)",
        "gopher64": "Gopher64 (C64 emulator)",
        "gsplus": "GS+ (Apple IIgs emulator)",
        "gzdoom": "GZDoom (Doom engine)",
        "hatari": "Hatari (Atari ST/STE/TT/Falcon)",
        "hbmame": "Homebrew MAME",
        "hypseus": "Hypseus (Coleco/A7800)",
        "jgenesis": "JGenesis (Genesis/MegaDrive)",
        "jynx": "Jynx (Atari Lynx)",
        "kega-fusion": "Kega Fusion (Sega)",
        "kronos": "Kronos (Arcade)",
        "lime3ds": "LIME3DS (3DS emulator)",
        "love": "LÖVE (Lua game engine)",
        "m2emulator": "M2 Emulator (Arcade)",
        "magicengine": "MagicEngine (PC Engine/Turbografx)",
        "mame": "MAME",
        "mandarine": "Mandarine emu",
        "mednafen": "Mednafen",
        "melonds": "melonDS (Nintendo DS emulator)",
        "mesen": "Mesen (NES/Famicom)",
        "mgba": "mGBA (Game Boy Advance emulator)",
        "mupen64": "Mupen64Plus (N64)",
        "nosgba": "NO$GBA (GBA/DS emulator)",
        "openbor": "OpenBOR (Beat-em-up engine)",
        "opengoal": "OpenGOAL (Engine)",
        "openjazz": "OpenJAZZ (Jazz Jackrabbit engine)",
        "openmsx": "openMSX (MSX)",
        "oricutron": "Oricutron (Oric emulator)",
        "pcsx2": "PCSX2 (PS2 emulator)",
        "pcsx2-16": "PCSX2 v1.6",
        "pdark": "PC Dark (Engine)",
        "phoenix": "Phoenix emu",
        "pico8": "PICO-8 (Fantasy console)",
        "play": "Play! (PS2 emulator)",
        "ppsspp": "PPSSPP (PSP emulator)",
        "project64": "Project64 (N64 emulator)",
        "psxmame": "PSX in MAME core",
        "raine": "Raine (Arcade emulator)",
        "raze": "Raze (Doom/Heretic/Hexen engine)",
        "redream": "reDream (Dreamcast)",
        "retroarch": "RetroArch (Frontend + Cores)",
        "rpcs3": "RPCS3 (PS3 emulator)",
        "rpcs5": "RPCS5 (PS5 emulator)",
        "ruffle": "Ruffle (Flash emulator)",
        "ryujinx": "Ryujinx (Nintendo Switch)",
        "scummvm": "ScummVM (Adventure engines)",
        "shadps4": "ShadePS4 (PS4 emulator)",
        "simcoupe": "SimCoupe (SPECTRUM clone)",
        "simple64": "Simple64 (C64 emulator)",
        "singe2": "Singe2 engine",
        "snes9x": "Snes9x (SNES emulator)",
        "soh": "Secrets of Harmony (mod engine)",
        "solarus": "Solarus (Zelda engine)",
        "sonic3air": "Sonic 3 A.I.R. engine",
        "sonicmania": "Sonic Mania engine",
        "sonicretro": "Sonic Retro projects",
        "sonicretrocd": "Sonic Retro CD",
        "ssf": "SSF (Sega Saturn emulator)",
        "starship": "Starship (Emulator)",
        "steam": "Steam (not an emulator)",
        "stella": "Stella (Atari 2600 emulator)",
        "sudachi": "Sudachi (Emulator engine)",
        "supermodel": "Supermodel (Arcade Model3)",
        "suyu": "Suyu emu",
        "teknoparrot": "TeknoParrot (Arcade)",
        "theforceengine": "The Force Engine (Star Wars)",
        "tsugaru": "Tsugaru engine",
        "vita3k": "Vita3K (PS Vita emulator)",
        "vpinball": "Visual Pinball",
        "winuae": "WinUAE (Amiga emulation)",
        "xemu": "Xemu (Xbox emulator)",
        "xenia": "Xenia (Xbox One emulator)",
        "xenia-canary": "Xenia Canary",
        "xenia-manager": "Xenia Manager",
        "xm6pro": "XM6Pro (SharpX68000)",
        "xroar": "XRoar (Dragon/CoCo)",
        "yabasanshiro": "Yaba Sanshiro (Saturn emulator)",
        "yuzu": "Yuzu (Nintendo Switch)",
        "zesarux": "ZEsarUX (ZX Spectrum)",
        "zinc": "Zinc (Atari ST/STE emulator)",
    }

    _RETROBAT_BIOS_FOLDERS: Dict[str, str] = {
        "cannonball": "Cannonball (engine de Out Run)",
        "Databases": "Bases de datos internas (MAME / RetroArch)",
        "dc": "Sega Dreamcast",
        "dinothawr": "Dinothawr (juego homebrew)",
        "dolphin-emu": "Nintendo GameCube / Wii (Dolphin)",
        "dragon": "Dragon 32 / Dragon 64",
        "eka2l1": "Symbian OS (EKA2L1)",
        "fba": "Final Burn Alpha (Arcade)",
        "fbalpha2012": "Final Burn Alpha 2012",
        "fbneo": "Final Burn Neo (Arcade)",
        "fmtowns": "Fujitsu FM Towns",
        "fmtownsux": "Fujitsu FM Towns UX",
        "hatari": "Atari ST / STE / TT / Falcon",
        "hatarib": "Atari ST (variantes BIOS)",
        "hbmame": "HB-MAME (homebrew arcade)",
        "HdPacks": "Paquetes HD (MAME / otros)",
        "keropi": "PC-98 (NEC)",
        "kronos": "Sega Saturn (Kronos emulator)",
        "Machines": "MAME (definiciones de máquinas)",
        "mame": "MAME (Arcade)",
        "mame2000": "MAME 2000",
        "mame2003": "MAME 2003",
        "mame2003-plus": "MAME 2003 Plus",
        "mame2010": "MAME 2010",
        "mame2014": "MAME 2014",
        "mame2016": "MAME 2016",
        "melonDS DS": "Nintendo DS (melonDS BIOS)",
        "Mupen64plus": "Nintendo 64 (Mupen64Plus)",
        "neocd": "Neo Geo CD",
        "np2kai": "NEC PC-98 (Neko Project II Kai)",
        "nxengine": "Cave Story (NXEngine)",
        "openlara": "Tomb Raider (OpenLara engine)",
        "openmsx": "MSX / MSX2 / TurboR",
        "pcsx2": "Sony PlayStation 2",
        "PPSSPP": "Sony PlayStation Portable",
        "psxmame": "PlayStation 1 (PSX vía MAME)",
        "quasi88": "NEC PC-8801",
        "raine": "Arcade (Raine emulator)",
        "same_cdi": "Philips CD-i",
        "scummvm": "Motores LucasArts / aventuras gráficas",
        "swanstation": "Sony PlayStation (DuckStation core)",
        "vice": "Commodore (C64 / C128 / VIC-20 / PET)",
        "xmil": "Sharp X1",
        "xrick": "Rick Dangerous (engine)",
    }
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
        # Flag para iniciar en modo consola (pantalla completa + mando)
        self.console_mode_enabled: bool = False

        # Estado
        self.model = LinksTableModel([])
        self.manager = DownloadManager(self.pool, 3)
        self.manager.queue_changed.connect(self._refresh_downloads_table)
        # Seguir descargas en segundo plano
        self.manager.queue_changed.connect(self._check_background_downloads)
        self.background_downloads: bool = False
        self.items: List[DownloadItem] = []
        self.table_dl: Optional[QTableWidget] = None
        self._emulator_catalog: List[EmulatorInfo] = []
        self._current_emulator: Optional[EmulatorInfo] = None
        self._retrobat_root: str = ""
        self._retrobat_exe: str = ""
        self._retrobat_inventory: List[Dict[str, object]] = []
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._tray_menu: Optional[QMenu] = None
        self._tray_show_action = None
        self._tray_exit_action = None
        self._tray_message_shown: bool = False
        self._console_controller: Optional[PygameConsoleController] = None
        self._setup_tray_icon()

        # Cesta de descargas (agrupa ROMs) y estructura de búsqueda
        # Es importante inicializar estos diccionarios antes de construir las pestañas,
        # ya que algunas pestañas (como el selector) pueden llamar a métodos que
        # dependen de ellos, como `_refresh_basket_table`.
        self.basket_items: dict[int, dict] = {}
        self.search_groups: dict[int, List[sqlite3.Row]] = {}
        self.arcades_search_groups: dict[int, dict] = {}

        # Tabs: mostrar primero el selector, luego emuladores, descargas y finalmente ajustes
        tabs = QTabWidget(); self.setCentralWidget(tabs); self.tabs = tabs
        # Crear contenedores para cada pestaña
        self.tab_selector = QWidget()
        self.tab_frontends = QWidget()
        self.tab_emulators = QWidget()
        self.tab_downloads = QWidget()
        self.tab_settings = QWidget()
        # Añadir pestañas en orden: Selector, Emuladores, Descargas, Ajustes
        tabs.addTab(self.tab_selector, "Selector de ROMs")
        tabs.addTab(self.tab_frontends, "Frontends")
        tabs.addTab(self.tab_emulators, "Emuladores")
        tabs.addTab(self.tab_downloads, "Descargas")
        tabs.addTab(self.tab_settings, "Ajustes")

        self._create_fullscreen_exit_button()
        self._apply_console_stylesheet()
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        # Construir las pestañas
        self._build_selector_tab()
        self._build_frontends_tab()
        self._build_emulators_tab()
        # La cesta se construirá dentro del selector, no como pestaña aparte
        self._build_downloads_tab()
        self._build_settings_tab()

        tabs.currentChanged.connect(self._on_tab_changed)



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
        if self.console_mode_enabled:
            self.showFullScreen()
        else:
            self.showNormal()
            if not self.isVisible():
                self.show()
        self.activateWindow()
        try:
            self.raise_()
        except Exception:
            pass
        self._update_fullscreen_exit_button()

    def _on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Responde a la interacción del usuario con el icono de la bandeja."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._restore_from_tray()

    def _quit_from_tray(self) -> None:
        """Cierra la aplicación desde el icono de la bandeja."""
        self.background_downloads = False
        self.close()

    # --- Modo consola / pantalla completa ---
    def _apply_console_stylesheet(self) -> None:
        """Aplica un tema oscuro con realce eléctrico para facilitar la navegación con mando."""
        stylesheet = r'''
            QMainWindow { background-color: #0b1221; color: #e5e7eb; }
            QWidget { background-color: #0b1221; color: #e5e7eb; }
            QLabel { color: #e5e7eb; }
            QGroupBox { border: 1px solid #1f2937; border-radius: 8px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: #9ca3af; }
            QPushButton, QToolButton, QLineEdit, QComboBox, QSpinBox, QCheckBox, QTableWidget, QTabWidget { border-radius: 6px; }
            QPushButton, QToolButton, QComboBox, QLineEdit, QSpinBox { background-color: #111827; border: 1px solid #1f2937; padding: 6px 10px; color: #e5e7eb; }
            QPushButton:hover, QToolButton:hover { border-color: #2563eb; }
            QPushButton:pressed, QToolButton:pressed { background-color: #0f172a; }
            QPushButton:focus, QToolButton:focus, QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QTabBar::tab:focus {
                border: 2px solid #00bfff; color: #e0f2fe; box-shadow: 0 0 8px #00bfff;
            }
            QTabBar::tab { background: #111827; border: 1px solid #1f2937; padding: 8px 14px; margin-right: 2px; }
            QTabBar::tab:selected { background: #1f2937; color: #7dd3fc; }
            QTabBar::tab:hover { color: #60a5fa; }
            QTableWidget { gridline-color: #1f2937; alternate-background-color: #111827; }
            QHeaderView::section { background-color: #0f172a; color: #cbd5e1; padding: 6px; border: 0px; }
            QProgressBar { border: 1px solid #1f2937; border-radius: 6px; text-align: center; color: #e5e7eb; }
            QProgressBar::chunk { background-color: #22d3ee; }
        '''
        self.setStyleSheet(stylesheet)

    def _create_fullscreen_exit_button(self) -> None:
        """Crea un botón visible en modo pantalla completa para salir rápidamente."""
        self._exit_fullscreen_button = QToolButton(self)
        self._exit_fullscreen_button.setText("Salir")
        self._exit_fullscreen_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        try:
            self._exit_fullscreen_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton))
        except Exception:
            pass
        self._exit_fullscreen_button.clicked.connect(self.close)
        self._exit_fullscreen_button.setStyleSheet(
            "QToolButton { background: #111827; border: 1px solid #2563eb; padding: 6px 12px;"
            " border-radius: 10px; color: #e5e7eb; font-weight: 600; }"
            "QToolButton:hover { background: #0f172a; }"
            "QToolButton:focus { border: 2px solid #00bfff; box-shadow: 0 0 8px #00bfff; }"
        )
        if hasattr(self, "tabs"):
            self.tabs.setCornerWidget(self._exit_fullscreen_button, Qt.Corner.TopRightCorner)
        self._update_fullscreen_exit_button()

    def _update_fullscreen_exit_button(self) -> None:
        if hasattr(self, "_exit_fullscreen_button"):
            self._exit_fullscreen_button.setVisible(self.isFullScreen())

    def _show_virtual_keyboard(self) -> None:
        """Solicita mostrar el teclado virtual cuando el modo consola está activo."""
        try:
            input_method = QGuiApplication.inputMethod()
            if input_method:
                input_method.show()
        except Exception:
            logging.exception("No se pudo mostrar el teclado virtual")

    def _ensure_console_controller(self) -> Optional[PygameConsoleController]:
        """Crea el controlador de mandos si aún no existe."""
        if self._console_controller is None:
            try:
                self._console_controller = PygameConsoleController(self)
            except Exception:
                logging.exception("No se pudo crear el controlador de mandos")
                self._console_controller = None
        return self._console_controller

    def _apply_console_mode(self, enabled: bool, *, save: bool = False, initial: bool = False) -> None:
        """
        Activa o desactiva el modo consola (pantalla completa + atajos de mando)
        y persiste el estado si se solicita.
        """
        self.console_mode_enabled = bool(enabled)
        if hasattr(self, "chk_console_mode"):
            self.chk_console_mode.blockSignals(True)
            self.chk_console_mode.setChecked(self.console_mode_enabled)
            self.chk_console_mode.blockSignals(False)

        if self.console_mode_enabled:
            if initial and not self.isVisible():
                self.setWindowState(self.windowState() | Qt.WindowState.WindowFullScreen)
            else:
                self.showFullScreen()
        else:
            if self.isFullScreen():
                if initial and not self.isVisible():
                    self.setWindowState(self.windowState() & ~Qt.WindowState.WindowFullScreen)
                else:
                    self.showNormal()

        controller = self._ensure_console_controller()
        if self.console_mode_enabled and controller:
            controller.start()
        elif controller:
            controller.stop()

        if save:
            self._save_config()
        self._update_fullscreen_exit_button()

    def _activate_focused_control(self) -> bool:
        """Simula un clic/activación sobre el widget enfocado."""
        widget = self.focusWidget()
        if isinstance(widget, QAbstractButton):
            widget.click()
            return True
        if isinstance(widget, QComboBox):
            widget.showPopup()
            return True
        return False

    def _switch_tab_with_delta(self, delta: int) -> bool:
        """Navega entre pestañas desplazando el índice actual."""
        if not hasattr(self, "tabs"):
            return False
        try:
            current = self.tabs.currentIndex()
            total = self.tabs.count()
            if total <= 0:
                return False
            new_index = (current + delta) % total
            if new_index != current:
                self.tabs.setCurrentIndex(new_index)
                return True
        except Exception:
            logging.exception("Failed to switch tab with delta %s", delta)
        return False

    def _handle_console_back_action(self) -> bool:
        """Acción de retroceso para mandos (tab anterior o abandonar pantalla completa)."""
        if self._switch_tab_with_delta(-1):
            return True
        if self.console_mode_enabled and self.isFullScreen():
            self._apply_console_mode(False, save=True)
            return True
        return False

    # --- Acciones expuestas para controladores externos (pygame) ---
    def trigger_console_activate(self) -> None:
        self._activate_focused_control()

    def trigger_console_back(self) -> None:
        self._handle_console_back_action()

    def trigger_console_tab_left(self) -> None:
        self._switch_tab_with_delta(-1)

    def trigger_console_tab_right(self) -> None:
        self._switch_tab_with_delta(1)

    def trigger_console_toggle(self) -> None:
        self._apply_console_mode(not self.console_mode_enabled, save=True)

    def trigger_console_focus_next(self) -> None:
        try:
            self.focusNextPrevChild(True)
        except Exception:
            logging.exception("No se pudo mover el foco al siguiente control")

    def trigger_console_focus_prev(self) -> None:
        try:
            self.focusNextPrevChild(False)
        except Exception:
            logging.exception("No se pudo mover el foco al control anterior")

    def _handle_gamepad_navigation(self, key: int) -> bool:
        """
        Gestiona movimientos básicos cuando el modo consola está activo y el
        usuario usa teclas de gamepad compatibles con Qt.
        """
        if not self.console_mode_enabled:
            return False

        focus_widget = self.focusWidget()
        is_text_input = isinstance(focus_widget, (QLineEdit, QComboBox))

        if key == Qt.Key.Key_PageUp:
            return self._switch_tab_with_delta(-1)
        if key == Qt.Key.Key_PageDown:
            return self._switch_tab_with_delta(1)
        if key in (Qt.Key.Key_GamepadL1, Qt.Key.Key_GamepadShoulderLeft):
            return self._switch_tab_with_delta(-1)
        if key in (Qt.Key.Key_GamepadR1, Qt.Key.Key_GamepadShoulderRight):
            return self._switch_tab_with_delta(1)
        if key == Qt.Key.Key_Guide:
            self._apply_console_mode(not self.console_mode_enabled, save=True)
            return True
        if key in (Qt.Key.Key_Back, Qt.Key.Key_Backspace):
            return self._handle_console_back_action()
        if key in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Select,
            Qt.Key.Key_Space,
            Qt.Key.Key_GamepadA,
        ):
            return self._activate_focused_control()
        if key in (Qt.Key.Key_GamepadB,):
            return self._handle_console_back_action()
        if not is_text_input and key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
            return self.focusNextPrevChild(False)
        if not is_text_input and key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            return self.focusNextPrevChild(True)
        if not is_text_input and key in (Qt.Key.Key_GamepadDpadUp, Qt.Key.Key_GamepadLeft):
            return self.focusNextPrevChild(False)
        if not is_text_input and key in (Qt.Key.Key_GamepadDpadDown, Qt.Key.Key_GamepadRight):
            return self.focusNextPrevChild(True)
        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        """Soporte de teclado/mando para el modo consola."""
        try:
            if event.key() == Qt.Key.Key_F11:
                self._apply_console_mode(not self.console_mode_enabled, save=True)
                return
            if event.key() == Qt.Key.Key_Guide:
                self._apply_console_mode(not self.console_mode_enabled, save=True)
                return
            if self.console_mode_enabled and event.key() == Qt.Key.Key_Escape:
                self._apply_console_mode(False, save=True)
                return
            if self._handle_gamepad_navigation(event.key()):
                return
        except Exception:
            logging.exception("Error handling console key event")
        super().keyPressEvent(event)

    def _on_tab_changed(self, index: int) -> None:
        try:
            widget = self.tabs.widget(index)
        except Exception:
            return
        if widget is self.tab_frontends:
            if not self._retrobat_root:
                self._ensure_retrobat_path_configured(prompt=True)
            self._scan_retrobat_inventory()

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

        # Grupo de modo consola (pantalla completa + mando)
        gb_console = QGroupBox("Interfaz tipo consola")
        console_layout = QVBoxLayout(gb_console)
        self.chk_console_mode = QCheckBox("Iniciar en modo consola (pantalla completa y mando)")
        self.chk_console_mode.toggled.connect(lambda checked: self._apply_console_mode(checked, save=True))
        console_layout.addWidget(self.chk_console_mode)
        lbl_console_hint = QLabel(
            "Al activar este modo, la aplicación arranca en pantalla completa y habilita atajos de mando: "
            "F11 o Guía alternan pantalla completa, LB/RB (o RePág/AvPág) cambian de pestaña, A acepta, "
            "B retrocede y la cruceta/cursores navegan entre controles. Al enfocar un campo de texto se "
            "invoca el teclado en pantalla para escribir con el mando."
        )
        lbl_console_hint.setWordWrap(True)
        console_layout.addWidget(lbl_console_hint)
        lay.addWidget(gb_console)

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

        self.selector_subtabs = QTabWidget()
        self.selector_tab_consoles = QWidget()
        self.selector_tab_arcades = QWidget()
        self.selector_subtabs.addTab(self.selector_tab_consoles, "Consolas")
        self.selector_subtabs.addTab(self.selector_tab_arcades, "Arcades")
        lay.addWidget(self.selector_subtabs)

        consoles_lay = QVBoxLayout(self.selector_tab_consoles)

        # Grupo de filtros y búsqueda
        filters = QGroupBox("Búsqueda y filtros"); f = QGridLayout(filters)
        self.le_search = QLineEdit(); self.le_search.setPlaceholderText("Buscar por ROM/etiqueta/servidor…")
        self.le_search.returnPressed.connect(self._run_search)
        self.cmb_system = QComboBox(); self.cmb_lang = QComboBox(); self.cmb_region = QComboBox(); self.cmb_fmt = QComboBox()
        self.btn_search = QPushButton("Buscar"); self.btn_search.clicked.connect(self._run_search)
        self.btn_import_list = QPushButton("Importar lista…"); self.btn_import_list.clicked.connect(self._import_rom_list)
        self.btn_paste_list = QPushButton("Pegar lista…"); self.btn_paste_list.clicked.connect(self._paste_rom_list)
        f.addWidget(QLabel("Texto:"),0,0); f.addWidget(self.le_search,0,1)
        f.addWidget(QLabel("Sistema:"),1,0); f.addWidget(self.cmb_system,1,1)
        f.addWidget(QLabel("Idioma:"),2,0); f.addWidget(self.cmb_lang,2,1)
        f.addWidget(QLabel("Región:"),3,0); f.addWidget(self.cmb_region,3,1)
        f.addWidget(QLabel("Formato:"),4,0); f.addWidget(self.cmb_fmt,4,1)
        f.addWidget(self.btn_search,0,2,5,1)
        f.addWidget(self.btn_import_list,5,0,1,3)
        f.addWidget(self.btn_paste_list,6,0,1,3)
        consoles_lay.addWidget(filters)

        # Tabla de resultados agrupados: columnas ROM, Sistema, Servidor, Formato, Idiomas, Acciones
        self.table_results = QTableWidget(0, 6)
        self.table_results.setHorizontalHeaderLabels([
            "ROM", "Sistema", "Servidor", "Formato", "Idiomas", "Acciones"
        ])
        self.table_results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        consoles_lay.addWidget(self.table_results)

        # Encabezado de la cesta y tabla de la cesta: se sitúan debajo de los resultados
        basket_label = QLabel("Cesta de descargas")
        basket_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        consoles_lay.addWidget(basket_label)

        download_target_box = QGroupBox("Destino de descarga")
        target_layout = QHBoxLayout(download_target_box)
        target_layout.setContentsMargins(8, 4, 8, 4)
        self.cmb_download_target = QComboBox()
        self.cmb_download_target.addItem("Descarga Windows", "windows")
        self.cmb_download_target.addItem("Descarga RetroBat", "retrobat")
        self.cmb_download_target.currentIndexChanged.connect(self._on_download_target_changed)
        target_layout.addWidget(QLabel("Enviar descargas a:"))
        target_layout.addWidget(self.cmb_download_target, 1)
        consoles_lay.addWidget(download_target_box)

        self.table_basket = QTableWidget(0, 6)
        self.table_basket.setHorizontalHeaderLabels([
            "ROM", "Sistema", "Servidor", "Formato", "Idioma", "Acciones"
        ])
        self.table_basket.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        consoles_lay.addWidget(self.table_basket)
        self.btn_basket_add_all = QPushButton("Añadir todo a descargas")
        self.btn_basket_add_all.clicked.connect(self._basket_add_all_to_downloads)
        consoles_lay.addWidget(self.btn_basket_add_all)

        self._build_arcades_selector_tab()

        # Inicializar la cesta vacía
        self._refresh_basket_table()

    def _build_arcades_selector_tab(self) -> None:
        """Construye la subpestaña Arcades con la misma maqueta visual que Consolas."""
        lay = QVBoxLayout(self.selector_tab_arcades)

        filters = QGroupBox("Búsqueda y filtros"); f = QGridLayout(filters)
        self.le_search_arcades = QLineEdit(); self.le_search_arcades.setPlaceholderText("Buscar por ROM/etiqueta/servidor…")
        self.le_search_arcades.returnPressed.connect(self._run_arcades_search)
        self.cmb_system_arcades = QComboBox(); self.cmb_system_arcades.addItem("Arcade (MAME)", self._ARCADE_SYSTEM_ID)
        self.cmb_system_arcades.setEnabled(False)
        self.cmb_lang_arcades = QComboBox(); self.cmb_lang_arcades.setEnabled(False)
        self.cmb_region_arcades = QComboBox(); self.cmb_region_arcades.setEnabled(False)
        self.cmb_fmt_arcades = QComboBox(); self.cmb_fmt_arcades.setEnabled(False)
        self.btn_search_arcades = QPushButton("Buscar"); self.btn_search_arcades.clicked.connect(self._run_arcades_search)
        self.btn_arcades_import = QPushButton("Importar lista (TXT/XML)"); self.btn_arcades_import.clicked.connect(self._import_arcade_rom_list)
        self.btn_arcades_paste = QPushButton("Pegar lista…"); self.btn_arcades_paste.clicked.connect(self._paste_arcade_rom_list)
        f.addWidget(QLabel("Texto:"),0,0); f.addWidget(self.le_search_arcades,0,1)
        f.addWidget(QLabel("Sistema:"),1,0); f.addWidget(self.cmb_system_arcades,1,1)
        f.addWidget(QLabel("Idioma:"),2,0); f.addWidget(self.cmb_lang_arcades,2,1)
        f.addWidget(QLabel("Región:"),3,0); f.addWidget(self.cmb_region_arcades,3,1)
        f.addWidget(QLabel("Formato:"),4,0); f.addWidget(self.cmb_fmt_arcades,4,1)
        f.addWidget(self.btn_search_arcades,0,2,5,1)
        f.addWidget(self.btn_arcades_import,5,0,1,3)
        f.addWidget(self.btn_arcades_paste,6,0,1,3)
        lay.addWidget(filters)

        self.table_arcades = QTableWidget(0, 6)
        self.table_arcades.setHorizontalHeaderLabels([
            "ROM", "Sistema", "Servidor", "Formato", "Idiomas", "Acciones"
        ])
        self.table_arcades.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table_arcades)

        basket_label = QLabel("Cesta de descargas")
        basket_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        lay.addWidget(basket_label)

        download_target_box = QGroupBox("Destino de descarga")
        target_layout = QHBoxLayout(download_target_box)
        target_layout.setContentsMargins(8, 4, 8, 4)
        self.cmb_download_target_arcades = QComboBox()
        self.cmb_download_target_arcades.addItem("Descarga Windows", "windows")
        self.cmb_download_target_arcades.addItem("Descarga RetroBat", "retrobat")
        self.cmb_download_target_arcades.currentIndexChanged.connect(self._on_arcades_download_target_changed)
        target_layout.addWidget(QLabel("Enviar descargas a:"))
        target_layout.addWidget(self.cmb_download_target_arcades, 1)
        lay.addWidget(download_target_box)

        self.table_basket_arcades = QTableWidget(0, 6)
        self.table_basket_arcades.setHorizontalHeaderLabels([
            "ROM", "Sistema", "Servidor", "Formato", "Idioma", "Acciones"
        ])
        self.table_basket_arcades.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table_basket_arcades)
        self.btn_basket_add_all_arcades = QPushButton("Añadir todo a descargas")
        self.btn_basket_add_all_arcades.clicked.connect(self._basket_add_all_to_downloads)
        lay.addWidget(self.btn_basket_add_all_arcades)

    # --- Frontends (RetroBat) ---
    def _build_frontends_tab(self) -> None:
        """Construye la pestaña para gestionar frontends como RetroBat."""

        lay = QVBoxLayout(self.tab_frontends)
        intro = QLabel(
            "Configura la ruta de RetroBat para inventariar ROMs, emuladores y BIOS, "
            "además de lanzar el frontend directamente."
        )
        intro.setWordWrap(True)
        lay.addWidget(intro)

        path_box = QGroupBox("Ubicación de RetroBat")
        grid = QGridLayout(path_box)
        self.le_retrobat_root = QLineEdit()
        self.le_retrobat_root.setPlaceholderText("Selecciona la carpeta raíz de RetroBat…")
        self.le_retrobat_root.setReadOnly(True)
        self.btn_retrobat_browse = QPushButton("Elegir carpeta…")
        self.btn_retrobat_browse.clicked.connect(lambda: self._ensure_retrobat_path_configured(prompt=True))
        self.btn_retrobat_scan = QPushButton("Actualizar inventario")
        self.btn_retrobat_scan.clicked.connect(self._scan_retrobat_inventory)
        grid.addWidget(QLabel("Carpeta RetroBat:"), 0, 0)
        grid.addWidget(self.le_retrobat_root, 0, 1)
        grid.addWidget(self.btn_retrobat_browse, 0, 2)
        grid.addWidget(self.btn_retrobat_scan, 1, 2)

        self.le_retrobat_exe = QLineEdit()
        self.le_retrobat_exe.setPlaceholderText("Ruta del ejecutable RetroBat.exe")
        self.le_retrobat_exe.setReadOnly(True)
        self.btn_retrobat_exe = QPushButton("Elegir .exe…")
        self.btn_retrobat_exe.clicked.connect(self._choose_retrobat_exe)
        self.btn_retrobat_launch = QPushButton("Ejecutar RetroBat")
        self.btn_retrobat_launch.clicked.connect(self._launch_retrobat)
        grid.addWidget(QLabel("Ejecutable:"), 1, 0)
        grid.addWidget(self.le_retrobat_exe, 1, 1)
        grid.addWidget(self.btn_retrobat_exe, 2, 2)
        grid.addWidget(self.btn_retrobat_launch, 2, 1)
        lay.addWidget(path_box)

        summary_box = QGroupBox("Resumen de contenido")
        summary_layout = QVBoxLayout(summary_box)
        self.lbl_retrobat_summary = QLabel("Selecciona la carpeta de RetroBat para ver el inventario.")
        self.lbl_retrobat_summary.setWordWrap(True)
        summary_layout.addWidget(self.lbl_retrobat_summary)
        lay.addWidget(summary_box)

        systems_box = QGroupBox("Sistemas disponibles")
        systems_layout = QHBoxLayout(systems_box)
        self.table_retrobat_systems = QTableWidget(0, 5)
        self.table_retrobat_systems.setHorizontalHeaderLabels([
            "Carpeta", "Sistema", "ROMs", "Emulador", "BIOS"
        ])
        self.table_retrobat_systems.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_retrobat_systems.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_retrobat_systems.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_retrobat_systems.itemSelectionChanged.connect(self._on_retrobat_system_selected)

        self.list_retrobat_roms = QListWidget()
        self.list_retrobat_roms.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

        systems_layout.addWidget(self.table_retrobat_systems, 2)
        systems_layout.addWidget(self.list_retrobat_roms, 3)
        lay.addWidget(systems_box)

        lay.addStretch()

    def _ensure_retrobat_path_configured(self, *, prompt: bool = False) -> bool:
        if self._retrobat_root and os.path.isdir(self._retrobat_root):
            self.le_retrobat_root.setText(self._retrobat_root)
            return True

        if not prompt:
            return False

        QMessageBox.information(
            self,
            "RetroBat",
            "Selecciona la carpeta raíz de RetroBat para poder inventariar ROMs y lanzar el frontend.",
        )
        base = self._retrobat_root or os.getcwd()
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta RetroBat", base)
        if not path:
            return False

        self._retrobat_root = path
        self.le_retrobat_root.setText(path)
        default_exe = os.path.join(path, "RetroBat.exe")
        if os.path.isfile(default_exe):
            self._retrobat_exe = default_exe
            self.le_retrobat_exe.setText(default_exe)
        self._scan_retrobat_inventory()
        self._save_config()
        return True

    def _choose_retrobat_exe(self) -> None:
        if not self._ensure_retrobat_path_configured(prompt=True):
            return
        base = self._retrobat_root
        exe_path, _ = QFileDialog.getOpenFileName(self, "Seleccionar RetroBat.exe", base, "Ejecutables (*.exe)")
        if exe_path:
            self._retrobat_exe = exe_path
            self.le_retrobat_exe.setText(exe_path)
            self._save_config()

    def _launch_retrobat(self) -> None:
        exe = self.le_retrobat_exe.text().strip() or self._retrobat_exe
        if not exe and self._retrobat_root:
            tentative = os.path.join(self._retrobat_root, "RetroBat.exe")
            if os.path.isfile(tentative):
                exe = tentative
                self.le_retrobat_exe.setText(tentative)
                self._retrobat_exe = tentative
        if not exe:
            QMessageBox.warning(self, "RetroBat", "No se ha configurado el ejecutable de RetroBat.")
            return
        if not os.path.isfile(exe):
            QMessageBox.warning(self, "RetroBat", "La ruta configurada de RetroBat.exe no existe.")
            return
        try:
            if os.name == "nt":
                os.startfile(exe)  # type: ignore[attr-defined]
            else:
                subprocess.Popen([exe], cwd=os.path.dirname(exe))
        except Exception as exc:
            logging.exception("No se pudo lanzar RetroBat")
            QMessageBox.critical(self, "RetroBat", f"No se pudo ejecutar RetroBat: {exc}")

    def _scan_retrobat_inventory(self) -> None:
        if not self._retrobat_root:
            return
        rom_base = Path(self._retrobat_root) / "roms"
        emu_base = Path(self._retrobat_root) / "emulators"
        bios_base = Path(self._retrobat_root) / "bios"
        inventory: List[Dict[str, object]] = []
        for folder, display in self._RETROBAT_ROM_FOLDERS.items():
            rom_dir = rom_base / folder
            rom_count = sum(1 for p in rom_dir.rglob("*") if p.is_file()) if rom_dir.exists() else 0
            has_emulator = (emu_base / folder).exists()
            has_bios = (bios_base / folder).exists()
            inventory.append(
                {
                    "folder": folder,
                    "display": display,
                    "roms": rom_count,
                    "emulator": has_emulator,
                    "bios": has_bios,
                }
            )
        self._retrobat_inventory = inventory
        self._populate_retrobat_table()
        self._refresh_retrobat_summary()

    def _populate_retrobat_table(self) -> None:
        if not hasattr(self, "table_retrobat_systems"):
            return
        self.table_retrobat_systems.setRowCount(0)
        for entry in self._retrobat_inventory:
            row = self.table_retrobat_systems.rowCount()
            self.table_retrobat_systems.insertRow(row)
            self.table_retrobat_systems.setItem(row, 0, QTableWidgetItem(str(entry["folder"])))
            self.table_retrobat_systems.setItem(row, 1, QTableWidgetItem(str(entry["display"])))
            self.table_retrobat_systems.setItem(row, 2, QTableWidgetItem(str(entry["roms"])))
            self.table_retrobat_systems.setItem(row, 3, QTableWidgetItem("Sí" if entry["emulator"] else "No"))
            self.table_retrobat_systems.setItem(row, 4, QTableWidgetItem("Sí" if entry["bios"] else "No"))

        if self.table_retrobat_systems.rowCount() > 0:
            self.table_retrobat_systems.selectRow(0)

    def _refresh_retrobat_summary(self) -> None:
        if not hasattr(self, "lbl_retrobat_summary"):
            return
        if not self._retrobat_root:
            self.lbl_retrobat_summary.setText("Selecciona la carpeta de RetroBat para ver el inventario.")
            return
        total_roms = sum(int(entry.get("roms", 0)) for entry in self._retrobat_inventory)
        total_emus = sum(1 for entry in self._retrobat_inventory if entry.get("emulator"))
        total_bios = sum(1 for entry in self._retrobat_inventory if entry.get("bios"))
        self.lbl_retrobat_summary.setText(
            f"ROMs: {total_roms} · Emuladores localizados: {total_emus} · Carpetas BIOS: {total_bios}"
        )

    def _on_retrobat_system_selected(self) -> None:
        if not self._retrobat_inventory:
            return
        selected = self.table_retrobat_systems.selectedItems()
        if not selected:
            return
        folder = selected[0].text()
        self._update_retrobat_rom_list(folder)

    def _update_retrobat_rom_list(self, folder: str) -> None:
        if not hasattr(self, "list_retrobat_roms"):
            return
        self.list_retrobat_roms.clear()
        if not self._retrobat_root:
            return
        rom_dir = Path(self._retrobat_root) / "roms" / folder
        if not rom_dir.exists():
            self.list_retrobat_roms.addItem("La carpeta de ROMs no existe para este sistema.")
            return
        files = [p for p in rom_dir.iterdir() if p.is_file()]
        if not files:
            self.list_retrobat_roms.addItem("No hay ROMs en esta carpeta.")
            return
        files = sorted(files, key=lambda p: p.name.lower())
        max_items = 500
        for idx, file in enumerate(files):
            if idx >= max_items:
                remaining = len(files) - max_items
                self.list_retrobat_roms.addItem(f"… y {remaining} archivos más")
                break
            self.list_retrobat_roms.addItem(file.name)

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

        self.lbl_emulator_requirements = QLabel("—")
        self.lbl_emulator_requirements.setWordWrap(True)
        form.addRow("Requisitos adicionales:", self.lbl_emulator_requirements)

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
            display_name = self._emulator_display_name(emu)
            self.cmb_emulator.addItem(display_name, emu)
            index = self.cmb_emulator.count() - 1
            tooltip = self._emulator_tooltip(emu)
            if tooltip:
                self.cmb_emulator.setItemData(index, tooltip, Qt.ItemDataRole.ToolTipRole)
        self.cmb_emulator.blockSignals(False)
        has_data = bool(emulators)
        self.cmb_emulator.setEnabled(has_data)
        self.btn_emulator_download.setEnabled(False)
        if has_data:
            self.cmb_emulator.setCurrentIndex(0)
            self._update_emulator_details(emulators[0])
        else:
            self._update_emulator_details(None)

    def _emulator_display_name(self, emulator: EmulatorInfo) -> str:
        if emulator.requires_bios:
            return f"{emulator.name} ⚠"
        if emulator.extras:
            return f"{emulator.name} ★"
        return emulator.name

    def _emulator_tooltip(self, emulator: EmulatorInfo) -> str:
        if emulator.requires_bios:
            return "Requiere BIOS o archivos adicionales para funcionar correctamente."
        if emulator.extras:
            return "Incluye descargas adicionales opcionales."
        return ""

    def _update_emulator_requirements_label(self, emulator: Optional[EmulatorInfo]) -> None:
        if not hasattr(self, "lbl_emulator_requirements"):
            return
        if not emulator:
            self.lbl_emulator_requirements.setText("—")
            return
        if emulator.requires_bios:
            self.lbl_emulator_requirements.setText("⚠ Requiere BIOS o archivos adicionales para funcionar.")
        elif emulator.extras:
            self.lbl_emulator_requirements.setText("★ Archivos extra opcionales disponibles.")
        else:
            self.lbl_emulator_requirements.setText("—")

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
            if hasattr(self, "lbl_emulator_requirements"):
                self.lbl_emulator_requirements.setText("—")
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
        self._update_emulator_requirements_label(emulator)
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
        if hasattr(self, "cmb_lang_arcades"):
            self.cmb_lang_arcades.clear(); [self.cmb_lang_arcades.addItem(c, i) for i,c in self.db.get_languages()]
        if hasattr(self, "cmb_region_arcades"):
            self.cmb_region_arcades.clear(); [self.cmb_region_arcades.addItem(c, i) for i,c in self.db.get_regions()]
        if hasattr(self, "cmb_fmt_arcades"):
            self.cmb_fmt_arcades.clear(); [self.cmb_fmt_arcades.addItem(x) for x in self.db.get_formats()]
        self._refresh_arcades_roms()

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

    def _run_arcades_search(self) -> None:
        """Ejecuta la búsqueda de Arcades fijando el sistema MAME."""
        if not self.db:
            QMessageBox.warning(self, "BD", "Conecta la base de datos primero.")
            return
        text = self.le_search_arcades.text().strip()
        try:
            rows = self.db.search_links(text, self._ARCADE_SYSTEM_ID, None, None, None)
            logging.debug("Arcades search returned %d rows for '%s'.", len(rows), text)
        except Exception as e:
            logging.exception("Error during arcades search: %s", e)
            QMessageBox.critical(self, "Búsqueda Arcades", str(e))
            return
        self.arcades_search_groups = self._build_grouped_links(rows)
        self._display_arcades_grouped_results()

    def _import_rom_list(self) -> None:
        """Importa una lista de ROM desde archivo para el sistema seleccionado."""
        if not self.db:
            QMessageBox.warning(self, "Importar lista", "Conecta la base de datos primero.")
            return
        sys_id = self.cmb_system.currentData()
        if sys_id is None:
            QMessageBox.warning(self, "Importar lista", "Selecciona un sistema específico antes de importar.")
            return
        self._import_list_for_system(int(sys_id), "Importar lista")

    def _import_arcade_rom_list(self) -> None:
        """Importa ROMs para Arcades (MAME)."""
        if not self.db:
            QMessageBox.warning(self, "Arcades", "Conecta la base de datos primero.")
            return
        self._import_list_for_system(self._ARCADE_SYSTEM_ID, "Arcades (MAME)")
        self._refresh_arcades_roms()

    def _paste_rom_list(self) -> None:
        """Permite pegar una lista manual de ROMs para el sistema seleccionado."""
        if not self.db:
            QMessageBox.warning(self, "Pegar lista", "Conecta la base de datos primero.")
            return
        sys_id = self.cmb_system.currentData()
        if sys_id is None:
            QMessageBox.warning(self, "Pegar lista", "Selecciona un sistema específico antes de continuar.")
            return
        self._import_pasted_list_for_system(int(sys_id), "Pegar lista")

    def _paste_arcade_rom_list(self) -> None:
        """Permite pegar manualmente una lista de ROMs de Arcades (MAME)."""
        if not self.db:
            QMessageBox.warning(self, "Arcades", "Conecta la base de datos primero.")
            return
        self._import_pasted_list_for_system(self._ARCADE_SYSTEM_ID, "Arcades (MAME)")
        self._refresh_arcades_roms()

    def _import_list_for_system(self, system_id: int, title: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecciona el archivo de lista",
            "",
            "Listas (*.txt *.csv *.xml);;Todos los archivos (*)",
        )
        if not path:
            return
        try:
            if Path(path).suffix.lower() == ".xml":
                raw_names = self.parse_rom_list_from_xml(path)
            else:
                raw_names = self.parse_rom_list_from_txt(self._read_text_file(path))
            self._process_import_tokens(system_id, title, raw_names, path)
        except Exception as exc:
            logging.exception("Error importing ROM list %s", path)
            QMessageBox.critical(self, title, f"No se pudo procesar el archivo: {exc}")

    def _import_pasted_list_for_system(self, system_id: int, title: str) -> None:
        """Procesa una lista escrita/pegada por el usuario como si fuera un TXT."""
        text = self._ask_manual_list_text(title)
        if text is None:
            return
        self._process_import_tokens(system_id, title, self.parse_rom_list_from_txt(text), "entrada manual")

    def _ask_manual_list_text(self, title: str) -> Optional[str]:
        """Muestra un cuadro de texto multilínea para pegar nombres de ROM."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{title} · Pegar lista")
        dialog.setMinimumWidth(560)
        dialog.setMinimumHeight(380)

        lay = QVBoxLayout(dialog)
        hint = QLabel("Pega aquí tu lista de ROMs (una por línea o separadas por comas).")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        editor = QTextEdit(dialog)
        editor.setPlaceholderText("Ejemplo:\nSuper Mario Bros\nContra\nMetal Slug 3")
        lay.addWidget(editor)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        btn_search_roms = QPushButton("Buscar ROMs")
        btn_search_roms.setDefault(True)
        buttons.addButton(btn_search_roms, QDialogButtonBox.ButtonRole.AcceptRole)
        lay.addWidget(buttons)

        result: Dict[str, Optional[str]] = {"text": None}

        def accept_with_text() -> None:
            entered = editor.toPlainText().strip()
            if not entered:
                QMessageBox.warning(dialog, "Pegar lista", "Escribe o pega al menos un nombre de ROM.")
                return
            result["text"] = entered
            dialog.accept()

        btn_search_roms.clicked.connect(accept_with_text)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            return result["text"]
        return None

    def _process_import_tokens(self, system_id: int, title: str, raw_names: List[str], source: str) -> None:
        """Resuelve y añade ROMs a la cesta desde una lista ya parseada."""
        added_count = 0
        already_count = 0
        not_found: List[str] = []
        error: Optional[Exception] = None
        try:
            logging.info("Import list parsed %d tokens from %s", len(raw_names), source)
            if not raw_names:
                logging.warning("Import list parser returned 0 tokens for %s", source)

            unique_names: List[str] = []
            seen: set[str] = set()
            for raw_name in raw_names:
                token = (raw_name or "").strip()
                if not token:
                    continue
                dedupe_key = token.casefold()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                unique_names.append(token)

            matched = self.fetch_rom_ids_for_names(system_id, unique_names)
            found_ids = [matched[name] for name in unique_names if name in matched]
            not_found = [name for name in unique_names if name not in matched]
            logging.info(
                "Import list DB lookup for system %s: parsed=%d found=%d not_found=%d",
                system_id,
                len(unique_names),
                len(found_ids),
                len(not_found),
            )

            added_count, already_count = self.add_roms_to_download_basket(found_ids)
        except Exception as exc:
            error = exc
            logging.exception("Error importing ROM list from %s", source)
        finally:
            if error is not None:
                QMessageBox.critical(self, title, f"No se pudo procesar la lista: {error}")
            else:
                self._show_import_summary_dialog(title, added_count, not_found, already_count)

    def _show_import_summary_dialog(
        self,
        title: str,
        added_count: int,
        not_found: Sequence[str],
        already_count: int,
    ) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{title} · Resultado de importación")
        dialog.setMinimumWidth(520)
        lay = QVBoxLayout(dialog)
        lay.addWidget(QLabel(f"Añadidos a la cesta: {added_count}"))
        lay.addWidget(QLabel(f"Ya presentes en la cesta: {already_count}"))
        lay.addWidget(QLabel(f"No encontrados: {len(not_found)}"))

        list_widget = QListWidget()
        list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for name in not_found:
            list_widget.addItem(name)
        list_widget.setEnabled(bool(not_found))
        lay.addWidget(list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_copy = QPushButton("Copiar lista")
        btn_copy.setEnabled(bool(not_found))

        def copy_missing() -> None:
            QGuiApplication.clipboard().setText("\n".join(not_found))

        btn_copy.clicked.connect(copy_missing)
        buttons.addButton(btn_copy, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(dialog.reject)
        lay.addWidget(buttons)
        dialog.exec()

    @staticmethod
    def _read_text_file(path: str) -> str:
        try:
            return Path(path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return Path(path).read_text(encoding="latin-1")

    @staticmethod
    def parse_rom_list_from_txt(text: str) -> List[str]:
        """Parsea listas TXT/CSV separadas por comas ignorando vacíos."""
        normalized = text.replace("\n", ",").replace("\r", ",")
        return [token.strip() for token in normalized.split(",") if token.strip()]

    @staticmethod
    def parse_rom_list_from_xml(path: str) -> List[str]:
        """Parsea XML HyperSpin y devuelve el atributo name de cada <game>."""
        root = ET.parse(path).getroot()
        result: List[str] = []
        for game in root.iter("game"):
            name = (game.attrib.get("name") or "").strip()
            if name:
                result.append(name)
        return result

    @staticmethod
    def normalize_rom_name(s: str) -> str:
        """Normaliza el nombre de una ROM para comparaciones tolerantes."""
        text = s.lower()
        normalized = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        text = re.sub(r"\([^)]*\)", " ", text)
        text = re.sub(r"\[[^\]]*\]", " ", text)
        text = text.replace("-", " ").replace("_", " ")
        text = re.sub(r"[^0-9a-z]+", " ", text)
        return " ".join(text.split())

    @staticmethod
    def _normalize_rom_name(name: str) -> str:
        return MainWindow.normalize_rom_name(name)

    def fetch_rom_ids_for_names(self, system_id: int, names: List[str]) -> Dict[str, int]:
        """Busca ids de ROM por nombre en lotes para un sistema."""
        if not self.db:
            return {}
        return self.db.fetch_rom_ids_for_names(system_id, names)

    def add_roms_to_download_basket(self, rom_ids: List[int]) -> tuple[int, int]:
        """Añade ROMs a la cesta reutilizando la lógica existente."""
        if not self.db:
            return (0, 0)
        added = 0
        already = 0
        for rom_id in rom_ids:
            if rom_id in self.basket_items:
                already += 1
                continue
            links = self.db.get_links_by_rom(rom_id)
            if not links:
                continue
            rom_name = links[0]["rom_name"]
            group = self.search_groups.get(rom_id)
            if group is None:
                group = self._create_group_from_links(rom_name, links)
            if self._add_links_to_basket(rom_id, rom_name, links, group):
                added += 1
            else:
                already += 1
        if added:
            self._refresh_basket_table()
        return added, already

    def _refresh_arcades_roms(self) -> None:
        """Refresca Arcades reutilizando la búsqueda visual estilo Consolas."""
        if hasattr(self, "le_search_arcades"):
            self._run_arcades_search()

    @classmethod
    def _extract_rom_names_from_lines(cls, lines: Sequence[str]) -> List[str]:
        return cls.parse_rom_list_from_txt("\n".join(lines))

    @classmethod
    def _remove_known_extensions(cls, filename: str) -> str:
        """Elimina extensiones conocidas de nombres de archivo de ROM."""
        name = filename.strip()
        while True:
            base, ext = os.path.splitext(name)
            if not ext:
                break
            ext_lower = ext.lower()
            if ext_lower in cls._KNOWN_ROM_EXTENSIONS:
                name = base
                continue
            break
        return name.strip().rstrip('.')

    @staticmethod
    def _format_name_list(names: Sequence[str], limit: int = 12) -> str:
        """Formatea una lista de nombres para mostrarlos en un cuadro de diálogo."""
        if not names:
            return ""
        unique: List[str] = []
        seen: set[str] = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            unique.append(name)
        display = [f" • {value}" for value in unique[:limit]]
        extra = len(unique) - limit
        if extra > 0:
            display.append(f" • … y {extra} más")
        return "\n".join(display)

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

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        """
        Intercepta eventos globales de foco y teclado.

        - En modo consola, muestra teclado virtual al enfocar entradas.
        - En la tabla de descargas, maneja Suprimir para borrar filas.
        """
        try:
            if (
                self.console_mode_enabled
                and event.type() == QEvent.Type.FocusIn
                and isinstance(obj, (QLineEdit, QComboBox))
            ):
                self._show_virtual_keyboard()

            table_dl = getattr(self, "table_dl", None)
            if table_dl is not None and obj is table_dl and event.type() == QEvent.Type.KeyPress:
                from PyQt6.QtGui import QKeyEvent
                key_event = event  # type: QKeyEvent
                if key_event.key() == Qt.Key.Key_Delete:
                    logging.debug("Delete key pressed on downloads table.")
                    self._delete_selected_items()
                    return True
        except Exception:
            logging.exception("eventFilter failed")
            return False

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
                'retrobat_root': self._retrobat_root,
                'retrobat_exe': self._retrobat_exe,
                'download_target': self.cmb_download_target.currentData() if hasattr(self, 'cmb_download_target') else 'windows',
                'basket_items': basket_data,
                'no_confirm_cancel': self.no_confirm_cancel,
                'hide_server_warning': self.hide_server_warning,
                'session_file': self.session_file,
                'console_mode_enabled': self.console_mode_enabled,
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
            retrobat_root = str(data.get('retrobat_root', '') or '')
            retrobat_exe = str(data.get('retrobat_exe', '') or '')
            download_target = str(data.get('download_target', 'windows') or 'windows')
            console_mode = bool(data.get('console_mode_enabled', False))

            self.le_db.setText(db_path)
            self.le_dir.setText(download_dir)
            self.spin_conc.setValue(conc)
            self.chk_extract_after.setChecked(chk_extract)
            self.chk_delete_after.setChecked(chk_del)
            self.chk_delete_after.setEnabled(chk_extract)
            self.chk_create_sys_dirs.setChecked(chk_sys)
            self.le_emulator_dir.setText(emulator_dir)
            self.chk_emulator_delete.setChecked(emulator_delete)
            self._retrobat_root = retrobat_root
            self._retrobat_exe = retrobat_exe
            if hasattr(self, 'le_retrobat_root'):
                self.le_retrobat_root.setText(retrobat_root)
            if hasattr(self, 'le_retrobat_exe'):
                self.le_retrobat_exe.setText(retrobat_exe)
            if hasattr(self, 'cmb_download_target'):
                idx = self.cmb_download_target.findData(download_target)
                if idx != -1:
                    self.cmb_download_target.setCurrentIndex(idx)
            self.console_mode_enabled = console_mode
            if hasattr(self, "chk_console_mode"):
                self.chk_console_mode.blockSignals(True)
                self.chk_console_mode.setChecked(console_mode)
                self.chk_console_mode.blockSignals(False)

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
            # Aplicar modo consola en la ventana inicial
            self._apply_console_mode(self.console_mode_enabled, save=False, initial=True)
            if self._retrobat_root:
                self._scan_retrobat_inventory()
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
        tables: List[QTableWidget] = [self.table_basket]
        if hasattr(self, "table_basket_arcades"):
            tables.append(self.table_basket_arcades)
        for table in tables:
            table.setRowCount(0)
        # Cada entrada en basket_items crea una fila
        for rom_id, item in self.basket_items.items():
            for table in tables:
                row = table.rowCount()
                table.insertRow(row)
                # Columna 0: nombre de la ROM (guardar rom_id en UserRole)
                rom_item = QTableWidgetItem(item['name'])
                rom_item.setData(Qt.ItemDataRole.UserRole, rom_id)
                table.setItem(row, 0, rom_item)
                # Columna 1: sistema
                sys_item = QTableWidgetItem(item['group'].get('system_name', '') or '')
                table.setItem(row, 1, sys_item)
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
                table.setCellWidget(row, 2, combo_srv)
                # Columna 3: selector de formato (depende del servidor)
                combo_fmt = QComboBox()
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
                table.setCellWidget(row, 3, combo_fmt)
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
                table.setCellWidget(row, 4, combo_lang)
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
                table.setCellWidget(row, 5, w)

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

    def _display_arcades_grouped_results(self) -> None:
        """Pinta la tabla de resultados agrupados de Arcades."""
        if not hasattr(self, "table_arcades"):
            return
        self.table_arcades.setRowCount(0)
        for rom_id in sorted(self.arcades_search_groups.keys(), key=lambda x: self.arcades_search_groups[x]["name"].lower()):
            group = self.arcades_search_groups[rom_id]
            row = self.table_arcades.rowCount()
            self.table_arcades.insertRow(row)
            rom_item = QTableWidgetItem(group["name"])
            rom_item.setData(Qt.ItemDataRole.UserRole, rom_id)
            self.table_arcades.setItem(row, 0, rom_item)
            sys_item = QTableWidgetItem(group.get("system_name", "") or "")
            self.table_arcades.setItem(row, 1, sys_item)

            combo_srv = QComboBox()
            for srv in group["servers"]:
                combo_srv.addItem(srv or "")
            combo_srv.setCurrentIndex(group.get("selected_server", 0) if group["servers"] else 0)
            combo_srv.setProperty('rom_id', rom_id)
            combo_srv.setProperty('row_idx', row)
            combo_srv.currentIndexChanged.connect(self._arcades_group_server_changed)
            self.table_arcades.setCellWidget(row, 2, combo_srv)

            combo_fmt = QComboBox()
            sel_srv = group.get("selected_server", 0)
            srv_name = group["servers"][sel_srv] if group["servers"] else ""
            fmt_list = group["formats_by_server"].get(srv_name, [])
            for fmt in fmt_list:
                combo_fmt.addItem(fmt or "")
            combo_fmt.setCurrentIndex(group.get("selected_format", 0) if fmt_list else 0)
            combo_fmt.setProperty('rom_id', rom_id)
            combo_fmt.setProperty('row_idx', row)
            combo_fmt.currentIndexChanged.connect(self._arcades_group_format_changed)
            self.table_arcades.setCellWidget(row, 3, combo_fmt)

            combo_lang = QComboBox()
            fmt_sel_index = group.get("selected_format", 0)
            fmt_name = fmt_list[fmt_sel_index] if fmt_list and fmt_sel_index < len(fmt_list) else ""
            lang_list = group["langs_by_server_format"].get((srv_name, fmt_name), [])
            for lang_str in lang_list:
                combo_lang.addItem(lang_str or "")
            combo_lang.setCurrentIndex(group.get("selected_lang", 0) if lang_list else 0)
            combo_lang.setProperty('rom_id', rom_id)
            combo_lang.setProperty('row_idx', row)
            combo_lang.currentIndexChanged.connect(self._arcades_group_language_changed)
            self.table_arcades.setCellWidget(row, 4, combo_lang)

            btn_add = QPushButton("Añadir")
            btn_add.setProperty('rom_id', rom_id)
            btn_add.clicked.connect(self._add_arcades_group_to_basket)
            self.table_arcades.setCellWidget(row, 5, btn_add)

    def _build_grouped_links(self, rows: Sequence[sqlite3.Row]) -> dict[int, dict]:
        groups: dict[int, dict] = {}
        for r in rows:
            rom_id = r["rom_id"]
            group = groups.setdefault(rom_id, {"name": r["rom_name"], "rows": [], "system_name": r["system_name"]})
            group["rows"].append(r)
        for group in groups.values():
            rows_list = group["rows"]
            servers = sorted(set((row["server"] or "") for row in rows_list))
            formats_by_server: dict[str, List[str]] = {}
            for srv in servers:
                fmts = sorted(set((row["fmt"] or "") for row in rows_list if (row["server"] or "") == srv))
                formats_by_server[srv] = fmts
            langs_by_server_format: dict[tuple[str, str], List[str]] = {}
            for r in rows_list:
                srv = r["server"] or ""
                fmt_val = r["fmt"] or ""
                key = (srv, fmt_val)
                lang_str = ','.join([x.strip() for x in (r["langs"] or "").split(',') if x.strip()]) or ""
                lst = langs_by_server_format.setdefault(key, [])
                if lang_str not in lst:
                    lst.append(lang_str)
            for key in langs_by_server_format:
                langs_by_server_format[key].sort()
            link_lookup: dict[tuple[str, str, str], sqlite3.Row] = {}
            for r in rows_list:
                srv = r["server"] or ""
                fmt_val = r["fmt"] or ""
                lang_str = ','.join([x.strip() for x in (r["langs"] or "").split(',') if x.strip()]) or ""
                link_lookup[(srv, fmt_val, lang_str)] = r
            group["servers"] = servers
            group["formats_by_server"] = formats_by_server
            group["langs_by_server_format"] = langs_by_server_format
            group["link_lookup"] = link_lookup
            group["selected_server"] = self._default_server_index(servers)
            group["selected_format"] = 0
            group["selected_lang"] = 0
        return groups

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

    def _arcades_group_server_changed(self, index: int) -> None:
        combo = self.sender()
        if combo is None:
            return
        rom_id = combo.property('rom_id')
        row_idx = combo.property('row_idx')
        if rom_id is None or row_idx is None:
            return
        group = self.arcades_search_groups.get(rom_id)
        if not group:
            return
        group['selected_server'] = combo.currentIndex()
        group['selected_format'] = 0
        group['selected_lang'] = 0
        row_idx = int(row_idx)
        srv_name = group['servers'][group['selected_server']] if group['servers'] else ""
        fmt_combo: QComboBox = self.table_arcades.cellWidget(row_idx, 3)  # type: ignore
        fmt_combo.blockSignals(True)
        fmt_combo.clear()
        fmt_list = group['formats_by_server'].get(srv_name, [])
        for fmt in fmt_list:
            fmt_combo.addItem(fmt or "")
        fmt_combo.setCurrentIndex(0)
        fmt_combo.blockSignals(False)

        lang_combo: QComboBox = self.table_arcades.cellWidget(row_idx, 4)  # type: ignore
        lang_combo.blockSignals(True)
        lang_combo.clear()
        fmt_name = fmt_list[0] if fmt_list else ""
        lang_list = group['langs_by_server_format'].get((srv_name, fmt_name), [])
        for lang_str in lang_list:
            lang_combo.addItem(lang_str or "")
        lang_combo.setCurrentIndex(0)
        lang_combo.blockSignals(False)

    def _arcades_group_format_changed(self, index: int) -> None:
        combo = self.sender()
        if combo is None:
            return
        rom_id = combo.property('rom_id')
        row_idx = combo.property('row_idx')
        if rom_id is None or row_idx is None:
            return
        group = self.arcades_search_groups.get(rom_id)
        if not group:
            return
        group['selected_format'] = combo.currentIndex()
        group['selected_lang'] = 0
        srv_idx = group.get('selected_server', 0)
        srv_name = group['servers'][srv_idx] if group['servers'] else ""
        fmt_list = group['formats_by_server'].get(srv_name, [])
        fmt_name = fmt_list[combo.currentIndex()] if fmt_list and combo.currentIndex() < len(fmt_list) else ""
        row_idx = int(row_idx)
        lang_combo: QComboBox = self.table_arcades.cellWidget(row_idx, 4)  # type: ignore
        lang_combo.blockSignals(True)
        lang_combo.clear()
        lang_list = group['langs_by_server_format'].get((srv_name, fmt_name), [])
        for lang_str in lang_list:
            lang_combo.addItem(lang_str or "")
        lang_combo.setCurrentIndex(0 if lang_list else 0)
        lang_combo.blockSignals(False)

    def _arcades_group_language_changed(self, index: int) -> None:
        combo = self.sender()
        if combo is None:
            return
        rom_id = combo.property('rom_id')
        if rom_id is None:
            return
        group = self.arcades_search_groups.get(rom_id)
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

    def _add_arcades_group_to_basket(self) -> None:
        btn = self.sender()
        if btn is None:
            return
        rom_id = btn.property('rom_id')
        if rom_id is None:
            return
        group = self.arcades_search_groups.get(rom_id)
        if not group:
            return
        srv_idx = group.get('selected_server', 0)
        fmt_idx = group.get('selected_format', 0)
        lang_idx = group.get('selected_lang', 0)
        self.basket_items[rom_id] = {
            'name': group['name'],
            'group': group,
            'selected_server': srv_idx,
            'selected_format': fmt_idx,
            'selected_lang': lang_idx,
        }
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

    def _on_download_target_changed(self, _: int) -> None:
        target = self.cmb_download_target.currentData()
        if hasattr(self, "cmb_download_target_arcades") and self.cmb_download_target_arcades.currentIndex() != self.cmb_download_target.currentIndex():
            self.cmb_download_target_arcades.blockSignals(True)
            self.cmb_download_target_arcades.setCurrentIndex(self.cmb_download_target.currentIndex())
            self.cmb_download_target_arcades.blockSignals(False)
        if target == "retrobat":
            self._ensure_retrobat_path_configured(prompt=True)

    def _on_arcades_download_target_changed(self, _: int) -> None:
        if self.cmb_download_target.currentIndex() != self.cmb_download_target_arcades.currentIndex():
            self.cmb_download_target.blockSignals(True)
            self.cmb_download_target.setCurrentIndex(self.cmb_download_target_arcades.currentIndex())
            self.cmb_download_target.blockSignals(False)
        self._on_download_target_changed(0)

    def _resolve_download_destination(self) -> tuple[str, Optional[str]]:
        target = "windows"
        base_dir: Optional[str] = None
        if hasattr(self, "cmb_download_target"):
            value = self.cmb_download_target.currentData()
            if isinstance(value, str):
                target = value

        if target == "retrobat":
            if not self._ensure_retrobat_path_configured(prompt=True):
                return target, None
            base_dir = os.path.join(self._retrobat_root, "roms")
            if not os.path.isdir(base_dir):
                QMessageBox.warning(
                    self,
                    "Retrobat",
                    "La carpeta de ROMs de RetroBat no existe. Revisa la ruta configurada.",
                )
                return target, None
        else:
            base_dir = self.le_dir.text().strip()
            if not base_dir:
                QMessageBox.warning(self, "Descargas", "Selecciona una carpeta de descargas en la pestaña de Ajustes.")
                return target, None
        return target, base_dir

    def _retrobat_folder_for_system(self, system_name: str) -> str:
        target = system_name.strip().lower()
        for folder, display in self._RETROBAT_ROM_FOLDERS.items():
            if target == display.lower() or target == folder.lower():
                return folder
            if target and target in display.lower():
                return folder
        return safe_filename(system_name) or "roms"

    def _process_basket_item_to_downloads(self, rom_id: int, base_dir: str, target: str = "windows") -> None:
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
        if target == "retrobat":
            folder_name = self._retrobat_folder_for_system(sys_name or group['name']) if sys_name or group.get('name') else ""
            if folder_name:
                final_dir = os.path.join(final_dir, folder_name)
        elif self.chk_create_sys_dirs.isChecked() and sys_name:
            final_dir = os.path.join(final_dir, safe_filename(sys_name))

        Path(final_dir).mkdir(parents=True, exist_ok=True)
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
        target, dest_dir = self._resolve_download_destination()
        if not dest_dir:
            return
        self._process_basket_item_to_downloads(int(rom_id), dest_dir, target)
        self._refresh_basket_table()

    def _basket_add_all_to_downloads(self) -> None:
        """Añade todas las ROM de la cesta a la cola de descargas."""
        target, dest_dir = self._resolve_download_destination()
        if not dest_dir:
            return
        for rom_id in list(self.basket_items.keys()):
            self._process_basket_item_to_downloads(rom_id, dest_dir, target)
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

    def _create_group_from_links(self, rom_name: str, links: Sequence[sqlite3.Row]) -> Optional[dict]:
        """Construye la estructura de agrupación para una ROM a partir de sus enlaces."""
        rows_list = list(links)
        if not rows_list:
            return None
        servers = sorted(set((row["server"] or "") for row in rows_list))
        formats_by_server: dict[str, List[str]] = {}
        for srv in servers:
            fmts = sorted(
                set((row["fmt"] or "") for row in rows_list if (row["server"] or "") == srv)
            )
            formats_by_server[srv] = fmts
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
        for key, lst in langs_by_server_format.items():
            lst.sort()
            langs_by_server_format[key] = lst
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
            "system_name": self._row_get(rows_list[0], "system_name", ""),
        }
        return group

    @staticmethod
    def _row_get(row: object, key: str, default: str = "") -> str:
        try:
            if row is not None and hasattr(row, "keys") and key in row.keys():
                return row[key]
        except Exception:
            pass
        try:
            return row.get(key, default)
        except Exception:
            return default

    def _add_links_to_basket(
        self,
        rom_id: int,
        rom_name: str,
        links: Sequence[sqlite3.Row],
        group: Optional[dict] = None,
    ) -> bool:
        """Inserta una ROM y sus enlaces en la cesta si no estaba presente."""
        if rom_id in self.basket_items:
            return False
        if group is None:
            group = self._create_group_from_links(rom_name, links)
        if not group:
            return False
        if group.get("selected_server") is None:
            servers = group.get("servers", [])
            group["selected_server"] = self._default_server_index(servers)
        group.setdefault("selected_format", 0)
        group.setdefault("selected_lang", 0)
        sel_srv = group.get("selected_server", 0)
        sel_fmt = group.get("selected_format", 0)
        sel_lang = group.get("selected_lang", 0)
        self.basket_items[rom_id] = {
            'name': rom_name,
            'links': list(links),
            'group': group,
            'selected_server': sel_srv,
            'selected_format': sel_fmt,
            'selected_lang': sel_lang,
        }
        return True

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
                group = self._create_group_from_links(rom_name, links)
            if not group:
                continue
            self._add_links_to_basket(int(rom_id), rom_name, links, group)
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
        if self._console_controller:
            self._console_controller.stop()
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
