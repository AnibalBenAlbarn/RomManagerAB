"""
Módulo de utilidades para el gestor de ROMs.

Actualmente contiene funciones auxiliares que se utilizan en distintas
partes de la aplicación, como la sanitización de nombres de archivo.
"""

def safe_filename(name: str) -> str:
    """
    Sanitiza un nombre de archivo sustituyendo caracteres no válidos.
    Se utiliza para crear nombres de archivo seguros en diferentes
    sistemas operativos.

    :param name: Nombre de archivo original.
    :return: Nombre de archivo seguro, con caracteres problemáticos
        reemplazados por guiones bajos.
    """
    bad = '<>:"/\\|?*\n\r\t'
    return ''.join('_' if c in bad else c for c in name).strip()
