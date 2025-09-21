"""
Módulo para el acceso a la base de datos SQLite.

La clase Database encapsula la conexión y las consultas necesarias
para cargar filtros y buscar enlaces de descarga. Al separar esta
implementación en un módulo dedicado, se mejora la legibilidad del
código principal de la aplicación y se favorece la reutilización.
"""

import os
import sqlite3
from typing import Optional, List, Tuple


class Database:
    """
    Manejador de conexión SQLite para cargar filtros y buscar enlaces de descarga.
    Se ha extraído a un módulo separado para mejorar la legibilidad y modularidad.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        # Indica si la tabla 'links' contiene la columna opcional 'hash'
        self._has_links_hash = False

    def connect(self) -> None:
        """
        Abre la conexión a la base de datos si existe.
        """
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"No existe la BD: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        # Devolver filas como diccionarios para un acceso más cómodo en la UI
        self.conn.row_factory = sqlite3.Row
        # Detectar columnas disponibles en la tabla 'links'
        cur = self.conn.execute("PRAGMA table_info(links)")
        self._has_links_hash = any(r[1] == "hash" for r in cur.fetchall())

    def close(self) -> None:
        """
        Cierra la conexión a la base de datos.
        """
        if self.conn:
            self.conn.close()
            self.conn = None

    def get_systems(self) -> List[Tuple[Optional[int], str]]:
        """
        Devuelve la lista de sistemas disponibles para el filtro.
        El primer elemento de la lista corresponde a "Todos" (sin filtro).
        """
        assert self.conn
        cur = self.conn.execute("SELECT id, name FROM systems ORDER BY name")
        return [(None, "Todos")] + [(r[0], r[1]) for r in cur.fetchall()]

    def get_languages(self) -> List[Tuple[Optional[int], str]]:
        """
        Devuelve la lista de idiomas disponibles para el filtro.
        El primer elemento de la lista corresponde a "Todos" (sin filtro).
        """
        assert self.conn
        cur = self.conn.execute("SELECT id, code FROM languages ORDER BY code")
        return [(None, "Todos")] + [(r[0], r[1]) for r in cur.fetchall()]

    def get_regions(self) -> List[Tuple[Optional[int], str]]:
        """
        Devuelve la lista de regiones disponibles para el filtro.
        El primer elemento de la lista corresponde a "Todos" (sin filtro).
        """
        assert self.conn
        cur = self.conn.execute("SELECT id, code FROM regions ORDER BY code")
        return [(None, "Todos")] + [(r[0], r[1]) for r in cur.fetchall()]

    def get_formats(self) -> List[str]:
        """
        Devuelve la lista de formatos de archivo distintos disponibles.
        La primera opción es "Todos" para indicar que no se aplica filtro.
        """
        assert self.conn
        cur = self.conn.execute(
            "SELECT DISTINCT fmt FROM links WHERE fmt IS NOT NULL AND TRIM(fmt)<>'' ORDER BY fmt"
        )
        return ["Todos"] + [r[0] for r in cur.fetchall()]

    def get_rom_names_by_system(self, system_id: int) -> List[sqlite3.Row]:
        """
        Obtiene todos los nombres de ROM disponibles para un sistema concreto.

        Se devuelve una lista de filas con ``rom_id`` y ``rom_name`` para
        facilitar la construcción de búsquedas exactas por nombre en la
        interfaz de usuario.
        """
        assert self.conn
        sql = (
            "SELECT roms.id AS rom_id, roms.name AS rom_name "
            "FROM roms WHERE roms.system_id = ? ORDER BY roms.name"
        )
        cur = self.conn.execute(sql, (system_id,))
        return cur.fetchall()

    def search_links(
        self,
        text: str = "",
        system_id: Optional[int] = None,
        language_id: Optional[int] = None,
        region_id: Optional[int] = None,
        fmt: Optional[str] = None,
        limit: int = 1000,
    ) -> List[sqlite3.Row]:
        """
        Realiza una búsqueda de enlaces según el texto y filtros.
        Devuelve filas con información de ROM y link.

        :param text: Texto de búsqueda para coincidir con nombre de ROM, etiqueta o servidor.
        :param system_id: Identificador del sistema seleccionado (None para todos).
        :param language_id: Identificador del idioma seleccionado (None para todos).
        :param region_id: Identificador de la región seleccionada (None para todos).
        :param fmt: Formato de archivo seleccionado (None o "Todos" para todos).
        :param limit: Máximo número de resultados a devolver.
        :return: Lista de filas con información relevante para cada enlace de descarga.
        """
        assert self.conn
        params: List = []
        where = ["1=1"]
        if text:
            where.append("(roms.name LIKE ? OR links.label LIKE ? OR links.server_name LIKE ?)")
            like = f"%{text}%"
            params += [like, like, like]
        if system_id is not None:
            where.append("roms.system_id = ?")
            params.append(system_id)
        if language_id is not None:
            where.append(
                "EXISTS (SELECT 1 FROM link_languages ll WHERE ll.link_id = links.id AND ll.language_id = ?)"
            )
            params.append(language_id)
        if region_id is not None:
            where.append(
                "EXISTS (SELECT 1 FROM rom_regions rr WHERE rr.rom_id = roms.id AND rr.region_id = ?)"
            )
            params.append(region_id)
        if fmt is not None and fmt != "Todos":
            where.append("links.fmt = ?")
            params.append(fmt)
        hash_select = (
            "links.hash          AS hash,"
            if self._has_links_hash
            else "NULL               AS hash,"
        )
        sql = f"""
        SELECT
            links.id            AS link_id,
            roms.id             AS rom_id,
            roms.name           AS rom_name,
            roms.system_id      AS system_id,
            systems.name        AS system_name,
            links.server_name   AS server,
            links.fmt           AS fmt,
            links.size          AS size,
            {hash_select}
            COALESCE(GROUP_CONCAT(languages.code, ','), links.languages) AS langs,
            links.url           AS url,
            links.label         AS label
        FROM links
        JOIN roms    ON roms.id = links.rom_id
        JOIN systems ON systems.id = roms.system_id
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

    def get_links_by_rom(self, rom_id: int) -> List[sqlite3.Row]:
        """Obtiene todos los links asociados a una ROM específica."""
        assert self.conn
        hash_select = (
            "links.hash          AS hash,"
            if self._has_links_hash
            else "NULL               AS hash,"
        )
        sql = f"""
        SELECT
            links.id            AS link_id,
            roms.id             AS rom_id,
            roms.name           AS rom_name,
            roms.system_id      AS system_id,
            systems.name        AS system_name,
            links.server_name   AS server,
            links.fmt           AS fmt,
            links.size          AS size,
            {hash_select}
            COALESCE(GROUP_CONCAT(languages.code, ','), links.languages) AS langs,
            links.url           AS url,
            links.label         AS label
        FROM links
        JOIN roms    ON roms.id = links.rom_id
        JOIN systems ON systems.id = roms.system_id
        LEFT JOIN link_languages ON link_languages.link_id = links.id
        LEFT JOIN languages      ON languages.id = link_languages.language_id
        WHERE roms.id = ?
        GROUP BY links.id
        ORDER BY links.id
        """
        cur = self.conn.execute(sql, (rom_id,))
        return cur.fetchall()
