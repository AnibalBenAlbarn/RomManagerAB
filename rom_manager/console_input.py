"""Controlador de entrada para el modo consola basado en pygame.

Se integra con :class:`rom_manager.gui.main_window.MainWindow` para manejar
mandos sin bloquear el bucle de eventos de Qt. Cuando el modo consola está
activo se inicializa ``pygame.joystick`` y se leen los eventos mediante un
``QTimer`` que mantiene actualizada la lista de dispositivos y traduce sus
entradas en acciones de navegación.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer

if TYPE_CHECKING:
    from rom_manager.gui.main_window import MainWindow


class PygameConsoleController(QObject):
    """Gestiona mandos a través de pygame para el modo consola."""

    POLL_INTERVAL_MS = 50

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window = window
        self._pygame = None
        self._joysticks: Dict[int, object] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll_events)

    # --- Ciclo de vida ---
    def start(self) -> None:
        """Inicializa pygame y comienza a leer eventos de mando."""
        if not self._initialize():
            return
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        """Detiene la lectura de eventos y libera recursos."""
        try:
            if self._timer.isActive():
                self._timer.stop()
        except Exception:
            logging.exception("No se pudo detener el temporizador de mandos")
        self._shutdown_pygame()

    # --- Inicialización y limpieza ---
    def _initialize(self) -> bool:
        if self._pygame:
            return True
        try:
            import pygame

            os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
            pygame.joystick.init()
            self._pygame = pygame
            self._refresh_devices()
            logging.debug("pygame.joystick inicializado para el modo consola")
            return True
        except Exception:
            logging.exception("No se pudo inicializar pygame para los mandos")
            self._pygame = None
            self._joysticks.clear()
            return False

    def _shutdown_pygame(self) -> None:
        if not self._pygame:
            return
        try:
            self._pygame.joystick.quit()
            self._pygame.quit()
        except Exception:
            logging.exception("Error al cerrar pygame")
        finally:
            self._pygame = None
            self._joysticks.clear()

    def _refresh_devices(self) -> None:
        if not self._pygame:
            return
        self._joysticks.clear()
        try:
            for idx in range(self._pygame.joystick.get_count()):
                joy = self._pygame.joystick.Joystick(idx)
                self._joysticks[joy.get_instance_id()] = joy
        except Exception:
            logging.exception("No se pudo refrescar la lista de mandos")

    # --- Procesamiento de eventos ---
    def _poll_events(self) -> None:
        if not self.window.console_mode_enabled:
            return
        if not self._pygame and not self._initialize():
            return
        if not self._pygame:
            return
        try:
            for event in self._pygame.event.get():
                if event.type == self._pygame.JOYDEVICEADDED:
                    self._refresh_devices()
                elif event.type == self._pygame.JOYDEVICEREMOVED:
                    self._refresh_devices()
                elif event.type == self._pygame.JOYBUTTONDOWN:
                    self._handle_button(event.button)
                elif event.type == self._pygame.JOYHATMOTION:
                    self._handle_hat(event.value)
        except Exception:
            logging.exception("Error al procesar eventos de pygame")

    # --- Traducción de entradas a acciones ---
    _CONFIRM_BUTTONS = {0, 2}
    _BACK_BUTTONS = {1, 6}
    _TAB_LEFT_BUTTONS = {4}
    _TAB_RIGHT_BUTTONS = {5}
    _TOGGLE_MODE_BUTTONS = {7, 9, 10}

    def _handle_button(self, button: int) -> None:
        if button in self._CONFIRM_BUTTONS:
            self.window.trigger_console_activate()
            return
        if button in self._BACK_BUTTONS:
            self.window.trigger_console_back()
            return
        if button in self._TAB_LEFT_BUTTONS:
            self.window.trigger_console_tab_left()
            return
        if button in self._TAB_RIGHT_BUTTONS:
            self.window.trigger_console_tab_right()
            return
        if button in self._TOGGLE_MODE_BUTTONS:
            self.window.trigger_console_toggle()
            return

    def _handle_hat(self, value: tuple[int, int]) -> None:
        x, y = value
        if y > 0:
            self.window.trigger_console_focus_prev()
        elif y < 0:
            self.window.trigger_console_focus_next()
        elif x < 0:
            self.window.trigger_console_focus_prev()
        elif x > 0:
            self.window.trigger_console_focus_next()
