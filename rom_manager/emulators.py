import logging
from typing import List, Dict

import requests

EMULATORS_URL = "https://raw.githubusercontent.com/RetroBatTeam/RetroBat/master/emulators.json"


def fetch_emulators(url: str = EMULATORS_URL) -> List[Dict[str, str]]:
    """Descarga la lista de emuladores disponibles.

    Parameters
    ----------
    url: str
        URL del catálogo de emuladores en formato JSON.

    Returns
    -------
    list of dict
        Lista con entradas que contienen los campos ``name``, ``system``,
        ``version`` y ``url``. Devuelve una lista vacía si la descarga falla
        o la respuesta no tiene el formato esperado.
    """
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            emus = data.get("emulators") or data.get("items") or []
        else:
            emus = data
        result: List[Dict[str, str]] = []
        for it in emus:
            result.append(
                {
                    "name": it.get("name", ""),
                    "system": it.get("system", ""),
                    "version": it.get("version", ""),
                    "url": it.get("url", ""),
                }
            )
        return result
    except Exception:
        logging.exception("Failed to fetch emulators list")
        return []


def search_emulators(query: str, catalog: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Filtra el catálogo de emuladores por nombre o sistema."""
    if not query:
        return catalog
    q = query.lower()
    return [e for e in catalog if q in e.get("name", "").lower() or q in e.get("system", "").lower()]
