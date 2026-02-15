"""Controlador de entrada para el modo consola basado en pygame.

Se integra con :class:`rom_manager.gui.main_window.MainWindow` para manejar
mandos sin bloquear el bucle de eventos de Qt. Los eventos se capturan en un
hilo dedicado y se reenvían a la UI exclusivamente mediante señales de Qt.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    from rom_manager.gui.main_window import MainWindow


class GamepadReader(QObject):
    """Lector de eventos de gamepad en un hilo en segundo plano."""

    buttonPressed = pyqtSignal(int)
    axisMoved = pyqtSignal(int, float)
    hatMoved = pyqtSignal(int, int)

    POLL_INTERVAL_S = 0.04

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._pygame = None
        self._joystick = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Inicia el hilo de lectura del mando si aún no está activo."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="gamepad-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Detiene el hilo y libera recursos de pygame."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        self._shutdown()

    def _initialize(self) -> bool:
        if self._pygame:
            return True
        try:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
            os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"

            import pygame

            pygame.init()
            pygame.display.set_mode((1, 1))
            pygame.joystick.init()

            if pygame.joystick.get_count() > 0:
                joystick = pygame.joystick.Joystick(0)
                joystick.init()
                self._joystick = joystick
            else:
                self._joystick = None

            self._pygame = pygame
            return True
        except Exception:
            logging.exception("No se pudo inicializar pygame para lectura de gamepad")
            self._pygame = None
            self._joystick = None
            return False

    def _shutdown(self) -> None:
        if not self._pygame:
            return
        try:
            if self._joystick is not None:
                self._joystick.quit()
            self._pygame.joystick.quit()
            self._pygame.quit()
        except Exception:
            logging.exception("Error al cerrar pygame/gamepad")
        finally:
            self._pygame = None
            self._joystick = None

    def _run_loop(self) -> None:
        if not self._initialize():
            return
        while not self._stop_event.is_set():
            if not self._pygame:
                break
            try:
                for event in self._pygame.event.get():
                    if event.type == self._pygame.JOYDEVICEADDED:
                        if self._joystick is None and self._pygame.joystick.get_count() > 0:
                            joystick = self._pygame.joystick.Joystick(0)
                            joystick.init()
                            self._joystick = joystick
                    elif event.type == self._pygame.JOYDEVICEREMOVED:
                        if self._pygame.joystick.get_count() <= 0:
                            self._joystick = None
                    elif event.type == self._pygame.JOYBUTTONDOWN:
                        self.buttonPressed.emit(int(event.button))
                    elif event.type == self._pygame.JOYHATMOTION:
                        x, y = event.value
                        self.hatMoved.emit(int(x), int(y))
                    elif event.type == self._pygame.JOYAXISMOTION:
                        self.axisMoved.emit(int(event.axis), float(event.value))
            except Exception:
                logging.exception("Error procesando eventos de gamepad")
            time.sleep(self.POLL_INTERVAL_S)

        self._shutdown()


class PygameConsoleController(QObject):
    """Traduce eventos del mando a acciones de :class:`MainWindow`."""

    _CONFIRM_BUTTONS = {0}
    _BACK_BUTTONS = {1}
    _TAB_LEFT_BUTTONS = {4}
    _TAB_RIGHT_BUTTONS = {5}
    _OPEN_DOWNLOADS_BUTTONS = {6}
    _OPEN_OPTIONS_BUTTONS = {7}

    _AXIS_DEADZONE = 0.55

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window = window
        self.reader = GamepadReader(self)
        self.reader.buttonPressed.connect(self._on_button_pressed)
        self.reader.hatMoved.connect(self._on_hat_moved)
        self.reader.axisMoved.connect(self._on_axis_moved)

    def start(self) -> None:
        self.reader.start()

    def stop(self) -> None:
        self.reader.stop()

    def _on_button_pressed(self, button: int) -> None:
        if not self.window.console_mode_enabled:
            return
        if button in self._CONFIRM_BUTTONS:
            self.window.on_gamepad_button_pressed(button)
            return
        if button in self._BACK_BUTTONS:
            self.window.on_gamepad_button_pressed(button)
            return
        if button in self._TAB_LEFT_BUTTONS:
            self.window.trigger_console_tab_left()
            return
        if button in self._TAB_RIGHT_BUTTONS:
            self.window.trigger_console_tab_right()
            return
        if button in self._OPEN_OPTIONS_BUTTONS:
            self.window.trigger_console_open_options()
            return
        if button in self._OPEN_DOWNLOADS_BUTTONS:
            self.window.trigger_console_open_downloads()

    def _on_hat_moved(self, x: int, y: int) -> None:
        if not self.window.console_mode_enabled:
            return
        if x == 0 and y == 0:
            return
        self.window.on_gamepad_hat_moved(x, y)

    def _on_axis_moved(self, axis: int, value: float) -> None:
        if not self.window.console_mode_enabled:
            return
        if axis not in (0, 1):
            return
        if abs(value) < self._AXIS_DEADZONE:
            return
        dx = -1 if axis == 0 and value < 0 else (1 if axis == 0 and value > 0 else 0)
        dy = -1 if axis == 1 and value < 0 else (1 if axis == 1 and value > 0 else 0)
        if dx == 0 and dy == 0:
            return
        self.window.on_gamepad_axis_moved(axis, value)
