"""
Módulo que gestiona las descargas concurrentes de ROMs.

Incluye las clases DownloadSignals, DownloadTask, DownloadItem y DownloadManager.
Al separar la lógica de descarga de la interfaz de usuario, el código resulta
más limpio y fácil de mantener.
"""

import os
import time
import math
import threading
import hashlib
from typing import Any, Dict, Optional, List
from dataclasses import dataclass

import logging
import requests
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QThreadPool

from .utils import safe_filename, extract_archive


class DownloadSignals(QObject):
    """
    Conjunto de señales para notificar progreso, éxito y fallos durante la descarga.
    """

    # Use 64-bit integers for progress values to support files larger than 2 GiB
    progress = pyqtSignal('qint64', 'qint64', float, float, str)  # done, total, speed, eta, status
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)


class DownloadTask(QRunnable):
    """
    Descargador optimizado usando QRunnable.
    Utiliza cabeceras de navegador, ``requests.Session`` con reintentos y
    reanudación mediante el uso de archivos ``.part`` y la cabecera Range.
    """

    def __init__(self, url: str, dest_dir: str, file_name: str, headers: Optional[dict] = None, expected_hash: Optional[str] = None) -> None:
        super().__init__()
        self.url = url
        self.dest_dir = dest_dir
        self.file_name = file_name
        self.expected_hash = expected_hash
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
        self._pause = threading.Event()
        self._pause.set()
        self._cancel = False

    def pause(self) -> None:
        """
        Pausa la descarga.
        """
        self._pause.clear()

    def resume(self) -> None:
        """
        Reanuda la descarga.
        """
        self._pause.set()

    def cancel(self) -> None:
        """
        Cancela la descarga.
        """
        self._cancel = True
        self._pause.set()

    @staticmethod
    def _detect_algorithm(expected: str) -> str:
        length = len(expected)
        return {32: "md5", 40: "sha1", 64: "sha256"}.get(length, "sha256")

    @staticmethod
    def _file_hash(path: str, algo: str) -> str:
        h = hashlib.new(algo)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

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

            # Preparar cabeceras base y calcular bytes descargados previamente
            base_headers = dict(self.headers)
            downloaded = 0
            if os.path.exists(part_path):
                try:
                    downloaded = os.path.getsize(part_path)
                except OSError:
                    downloaded = 0
            headers = dict(base_headers)
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

            # Intento HEAD para conocer el tamaño total y detectar 416
            total = 0
            try:
                h = session.head(self.url, headers=headers, allow_redirects=True, timeout=(10, 15))
                if h.status_code == 416 and 'Range' in headers:
                    headers.pop('Range', None)
                    downloaded = 0
                    try:
                        os.remove(part_path)
                    except Exception:
                        pass
                    h = session.head(self.url, headers=headers, allow_redirects=True, timeout=(10, 15))
                if h.status_code in (200, 206):
                    total = int(h.headers.get('Content-Length', '0'))
            except Exception:
                pass

            # Iniciar la descarga en streaming con reintentos ante errores de red/SSL
            max_attempts = 4
            attempt = 0
            last_error: Optional[Exception] = None
            while attempt < max_attempts:
                attempt += 1

                # Recalcular bytes descargados (puede haber cambiado tras un fallo)
                if os.path.exists(part_path):
                    try:
                        downloaded = os.path.getsize(part_path)
                    except OSError:
                        downloaded = 0
                else:
                    downloaded = 0

                headers = dict(base_headers)
                if downloaded > 0:
                    headers['Range'] = f'bytes={downloaded}-'

                try:
                    r = session.get(
                        self.url,
                        headers=headers,
                        stream=True,
                        allow_redirects=True,
                        timeout=(10, 60),
                    )
                except requests.exceptions.RequestException as exc:
                    last_error = exc
                    logging.warning(
                        "Intento %s fallido al iniciar descarga de %s: %s",
                        attempt,
                        self.url,
                        exc,
                    )
                    time.sleep(min(2.0, 0.5 * attempt))
                    continue

                try:
                    if r.status_code == 416 and 'Range' in headers:
                        r.close()
                        headers.pop('Range', None)
                        downloaded = 0
                        try:
                            os.remove(part_path)
                        except Exception:
                            pass
                        try:
                            h = session.head(self.url, headers=headers, allow_redirects=True, timeout=(10, 15))
                            if h.status_code in (200, 206):
                                total = int(h.headers.get('Content-Length', '0'))
                        except Exception:
                            pass
                        last_error = RuntimeError('HTTP 416')
                        time.sleep(min(2.0, 0.5 * attempt))
                        continue

                    if r.status_code not in (200, 206):
                        self.signals.failed.emit(f"HTTP {r.status_code}")
                        r.close()
                        return

                    # Si el servidor no soporta Range, reiniciar y sobrescribir el archivo
                    append_mode = downloaded > 0 and r.status_code == 206
                    if not append_mode:
                        downloaded = 0

                    # Ajustar 'total' de bytes según los encabezados
                    cl = r.headers.get('Content-Length')
                    if cl is not None:
                        clen = int(cl)
                        if r.status_code == 206 and 'Range' in headers and append_mode:
                            total = clen + downloaded if total == 0 else total
                        else:
                            total = clen
                    if 'Content-Range' in r.headers and append_mode:
                        try:
                            total_all = int(r.headers['Content-Range'].split('/')[-1])
                            total = total_all
                        except Exception:
                            if total and total < downloaded:
                                total = downloaded

                    # Tamaño del chunk: 512 KB para reducir overhead y mejorar rendimiento
                    chunk_size = 1024 * 512
                    last_t = time.time()
                    last_b = downloaded
                    last_speed = 0.0
                    last_eta = math.inf

                    # Abrir archivo .part y escribir conforme se reciben datos
                    mode = 'ab' if append_mode else 'wb'
                    with open(part_path, mode) as f:
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
                            now = time.time()
                            dt = now - last_t
                            if dt >= 0.5:
                                delta = downloaded - last_b
                                last_speed = delta / dt if dt > 0 else 0.0
                                last_t = now
                                last_b = downloaded
                                if total and downloaded <= total and last_speed > 0:
                                    last_eta = (total - downloaded) / last_speed
                            # Emitir progreso
                            self.signals.progress.emit(
                                downloaded, total, float(last_speed), float(last_eta), 'Descargando'
                            )
                except (requests.exceptions.RequestException, OSError) as exc:
                    last_error = exc
                    logging.warning(
                        "Intento %s interrumpido durante descarga de %s: %s",
                        attempt,
                        self.url,
                        exc,
                    )
                    time.sleep(min(2.0, 0.5 * attempt))
                    continue
                finally:
                    r.close()

                last_error = None
                break

            if last_error is not None:
                raise last_error

            # Renombrar el archivo descargado correctamente
            if os.path.exists(final_path):
                try:
                    os.remove(final_path)
                except Exception:
                    pass
            os.replace(part_path, final_path)
            status = 'Completado'
            if self.expected_hash:
                try:
                    algo = self._detect_algorithm(self.expected_hash)
                    calc = self._file_hash(final_path, algo)
                    status = 'Integridad OK' if calc.lower() == self.expected_hash.lower() else 'Integridad KO'
                except Exception:
                    status = 'Integridad KO'
            # Señalar finalización
            self.signals.progress.emit(downloaded, total, 0.0, 0.0, status)
            self.signals.finished_ok.emit(final_path)
        except Exception as e:
            # Notificar fallo
            self.signals.failed.emit(str(e))


@dataclass
class DownloadItem:
    """
    Estructura que representa un elemento de la cola de descargas.
    """

    name: str
    url: str
    dest_dir: str
    expected_hash: Optional[str] = None
    system_name: str = ""
    task: Optional[DownloadTask] = None
    row: Optional[int] = None
    category: str = ""
    metadata: Optional[Dict[str, Any]] = None
    extract_task: Optional['ExtractionTask'] = None


class DownloadManager(QObject):
    """
    Administra la cola de descargas y controla cuántas están activas
    simultáneamente.
    """

    queue_changed = pyqtSignal()

    def __init__(self, pool: QThreadPool, max_concurrent: int = 3) -> None:
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

    def enqueue(self, item: DownloadItem) -> None:
        """Alias de :meth:`add` para compatibilidad."""
        self.add(item)

    def remove(self, item: DownloadItem) -> None:
        logging.debug(
            "Removing item from manager: %s (active=%s, queued=%s)",
            item.name,
            item in self._active,
            item in self._queue,
        )
        # Cancelar si se encuentra activo
        if item in self._active and item.task:
            logging.debug("Cancelling active task for %s", item.name)
            try:
                item.task.cancel()
            except Exception:
                logging.exception("Error cancelling task for %s", item.name)
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
        task = DownloadTask(it.url, it.dest_dir, it.name, expected_hash=it.expected_hash)
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
            it.task.cancel()


class ExtractionTask(QRunnable):
    """Tarea que ejecuta la extracción de un archivo en segundo plano."""

    def __init__(self, archive_path: str, dest_dir: str) -> None:
        super().__init__()
        self.archive_path = archive_path
        self.dest_dir = dest_dir
        self.signals = DownloadSignals()

    def run(self) -> None:  # pragma: no cover - depende de archivos externos
        try:
            self.signals.progress.emit(0, 1, 0.0, 0.0, 'Preparando extracción')

            def report(done: int, total: int, status: str) -> None:
                self.signals.progress.emit(done, total, 0.0, 0.0, status)

            extract_archive(self.archive_path, self.dest_dir, progress=report)
            self.signals.finished_ok.emit(self.dest_dir)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
