"""Catálogo estático de emuladores y utilidades de filtrado."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class EmulatorInfo:
    """Representa un emulador disponible para descargar."""

    name: str
    systems: Tuple[str, ...]
    url: str
    notes: str = ""
    extras: Tuple[Dict[str, str], ...] = field(default_factory=tuple)

    def supports(self, system: str) -> bool:
        target = system.strip().lower()
        return any(s.lower() == target for s in self.systems)

    def to_record(self) -> Dict[str, str]:
        """Convierte la entrada a un ``dict`` plano para compatibilidad antigua."""
        data = {
            "name": self.name,
            "system": ", ".join(self.systems),
            "url": self.url,
            "version": "",
            "notes": self.notes,
        }
        return data


EMULATOR_CATALOG: Tuple[EmulatorInfo, ...] = (
    EmulatorInfo(
        name="Mesen",
        systems=(
            "NES",
            "SNES",
            "Game Boy",
            "Game Boy Color",
            "Game Boy Advance",
            "PC Engine",
            "Master System",
            "Game Gear",
            "WonderSwan",
        ),
        url="https://github.com/SourMesen/Mesen2/releases/download/2.1.1/Mesen_2.1.1_Windows.zip",
        notes=(
            "Emulador multi-sistema de alta precisión para NES, SNES, Game Boy/Color/Advance, "
            "PC Engine y sistemas de 8 bits de SEGA, además de WonderSwan."
        ),
    ),
    EmulatorInfo(
        name="Nestopia UE",
        systems=("NES",),
        url="https://dl.emulator-zone.com/download.php/emulators/nes/nestopia/nestopia_1.52.0-win32.zip",
        notes="Emulador clásico y de código abierto para Nintendo NES.",
    ),
    EmulatorInfo(
        name="FCEUX",
        systems=("NES",),
        url="https://github.com/TASEmulators/fceux/releases/download/v2.6.6/fceux-2.6.6-win32.zip",
        notes="Incluye herramientas TAS y depuración para NES.",
    ),
    EmulatorInfo(
        name="Snes9x",
        systems=("SNES",),
        url="https://www.s9x-w32.de/dl/snes9x-1.63-win32-x64.zip",
        notes="Emulador consolidado de Super Nintendo con gran compatibilidad.",
    ),
    EmulatorInfo(
        name="bsnes",
        systems=("SNES",),
        url="https://github.com/bsnes-emu/bsnes/releases/download/nightly/bsnes-windows.zip",
        notes="Enfoque en precisión para el catálogo completo de SNES.",
    ),
    EmulatorInfo(
        name="BGB",
        systems=("Game Boy", "Game Boy Color"),
        url="https://bgb.bircd.org/bgbw64.zip",
        notes="Emulador ligero con depurador para Game Boy y Game Boy Color.",
    ),
    EmulatorInfo(
        name="SameBoy",
        systems=("Game Boy", "Game Boy Color"),
        url="https://github.com/LIJI32/SameBoy/releases/download/v1.0.2/sameboy_winsdl_v1.0.2.zip",
        notes="Alta precisión para la familia Game Boy con compatibilidad con paletas personalizadas.",
    ),
    EmulatorInfo(
        name="mGBA",
        systems=("Game Boy Advance", "Game Boy", "Game Boy Color"),
        url="https://s3.amazonaws.com/mgba/mGBA-build-latest-win32.7z",
        notes="Versión portátil de mGBA para Windows (32-bit). También ejecuta juegos de GB y GBC.",
        extras=(
            {
                "label": "Versión Windows 64-bit",
                "url": "https://s3.amazonaws.com/mgba/mGBA-build-latest-win64.7z",
            },
        ),
    ),
    EmulatorInfo(
        name="VisualBoyAdvance-M",
        systems=("Game Boy Advance", "Game Boy", "Game Boy Color"),
        url="https://github.com/visualboyadvance-m/visualboyadvance-m/releases/download/v2.2.0/visualboyadvance-m-Win-x86_64.zip",
        notes="Fork actualizado de VBA con soporte para filtros y emulación de GB/GBC/GBA.",
    ),
    EmulatorInfo(
        name="DuckStation",
        systems=("PlayStation",),
        url="https://github.com/stenzek/duckstation/releases/download/latest/duckstation-windows-x64-release.zip",
        notes="Emulador moderno de PlayStation (PS1) con interfaz amigable y recompilador rápido.",
    ),
    EmulatorInfo(
        name="PPSSPP",
        systems=("PSP",),
        url="https://www.ppsspp.org/files/1_19_3/ppsspp_win.zip",
        notes="Proyecto de código abierto para PlayStation Portable con soporte para escalado en alta definición.",
    ),
    EmulatorInfo(
        name="RPCS3",
        systems=("PlayStation 3",),
        url="https://github.com/RPCS3/rpcs3-binaries-win/releases/download/build-9c93ec0bc31bbc94ca4dce2a76ceea80da6f6554/rpcs3-v0.0.37-18022-9c93ec0b_win64_msvc.7z",
        notes="Emulador de PS3 que requiere firmware oficial para funcionar.",
    ),
    EmulatorInfo(
        name="Dolphin",
        systems=("Wii", "GameCube"),
        url="https://dl.dolphin-emu.org/releases/2509/dolphin-2509-x64.7z",
        notes="Emulador conjunto para Nintendo Wii y GameCube con soporte para mejoras visuales.",
    ),
    EmulatorInfo(
        name="mupen64plus",
        systems=("Nintendo 64",),
        url="https://github.com/mupen64plus/mupen64plus-core/releases/download/2.6.0/mupen64plus-bundle-win64-2.6.0.zip",
        notes="Paquete oficial con front-ends y plugins para Nintendo 64.",
    ),
    EmulatorInfo(
        name="Project64",
        systems=("Nintendo 64", "Nintendo 64DD"),
        url="https://www.pj64-emu.com/download/project64-3-0-1-zip",
        notes="Emulador veterano de Nintendo 64 con soporte para la unidad 64DD.",
    ),
    EmulatorInfo(
        name="simple64",
        systems=("Nintendo 64", "Nintendo 64DD"),
        url="https://github.com/simple64/simple64/releases/latest/download/simple64-win64.zip",
        notes="Distribución lista para usar basada en mupen64plus-Next.",
    ),
    EmulatorInfo(
        name="Mednafen",
        systems=(
            "Apple II",
            "Atari Lynx",
            "Game Boy",
            "Game Boy Color",
            "Neo Geo Pocket",
            "WonderSwan",
            "Virtual Boy",
            "PC Engine",
            "PC Engine CD",
            "PC-FX",
            "SNES",
            "Master System",
            "Mega Drive / Genesis",
            "Mega-CD / Sega CD",
            "32X",
            "PlayStation",
        ),
        url="https://mednafen.github.io/releases/files/mednafen-1.32.1-win64.zip",
        notes="Emulador multipropósito que utiliza módulos (cores) para cada sistema soportado.",
    ),
    EmulatorInfo(
        name="melonDS",
        systems=("Nintendo DS", "Nintendo DSi"),
        url="https://melonds.kuribo64.net/downloads/melonDS-windows-x86_64(1).zip",
        notes="Enfoque en precisión para Nintendo DS/DSi con soporte local de red."
    ),
    EmulatorInfo(
        name="DeSmuME",
        systems=("Nintendo DS",),
        url="https://github.com/TASEmulators/desmume/releases/download/release_0_9_13/desmume-0.9.13-win64.zip",
        notes="Emulador veterano de Nintendo DS con herramientas de grabación."
    ),
    EmulatorInfo(
        name="Azahar",
        systems=("Nintendo 3DS",),
        url="https://github.com/azahar-emu/azahar/releases/download/2123.1/azahar-2123.1-windows-msys2.zip",
        notes="Proyecto alternativo para Nintendo 3DS basado en renderizado moderno.",
    ),
    EmulatorInfo(
        name="Citra",
        systems=("Nintendo 3DS",),
        url="https://archive.org/download/citra-emu_202403/citra-windows-msvc-20240303-0ff3440_nightly.zip",
        notes="Emulador consolidado de Nintendo 3DS con versiones nightly y canary.",
    ),
    EmulatorInfo(
        name="Cemu",
        systems=("Wii U",),
        url="https://github.com/cemu-project/Cemu/releases/download/v2.6/cemu-2.6-windows-x64.zip",
        notes="Emulador de Wii U optimizado para hardware moderno.",
    ),
    EmulatorInfo(
        name="PCSX2",
        systems=("PlayStation 2",),
        url="https://github.com/PCSX2/pcsx2/releases/download/v2.4.0/pcsx2-v2.4.0-windows-x64-Qt.7z",
        notes="Nueva interfaz Qt oficial para el emulador de PlayStation 2.",
    ),
    EmulatorInfo(
        name="Vita3K",
        systems=("PS Vita",),
        url="https://github.com/Vita3K/Vita3K/releases/download/continuous/windows-latest.zip?time=1758020577592",
        notes="Proyecto experimental de PlayStation Vita, requiere archivos de firmware."
    ),
    EmulatorInfo(
        name="Cxbx-Reloaded",
        systems=("Xbox",),
        url="https://github.com/Cxbx-Reloaded/Cxbx-Reloaded/releases/download/CI-1c65ab4/CxbxReloaded-Release.zip",
        notes="Emulador y depurador para la Xbox original.",
    ),
    EmulatorInfo(
        name="Xemu",
        systems=("Xbox",),
        url="https://github.com/xemu-project/xemu/releases/latest/download/xemu-win-x86_64-release.zip",
        notes="Emulador de Xbox enfocado en compatibilidad. Requiere BIOS y HDD dumpeados.",
        extras=(
            {
                "label": "BIOS y disco duro requeridos",
                "url": "https://github.com/K3V1991/Xbox-Emulator-Files/releases/download/v1/Xbox-Emulator-Files.zip",
            },
        ),
    ),
    EmulatorInfo(
        name="Xenia (master)",
        systems=("Xbox 360",),
        url="https://github.com/xenia-project/release-builds-windows/releases/latest/download/xenia_master.zip",
        notes="Canal principal del emulador de Xbox 360.",
    ),
    EmulatorInfo(
        name="Xenia (canary)",
        systems=("Xbox 360",),
        url="https://github.com/xenia-canary/xenia-canary-releases/releases/latest/download/xenia_canary_windows.zip",
        notes="Compilación canary con mejoras experimentales para Xbox 360.",
    ),
    EmulatorInfo(
        name="Xenia Manager",
        systems=("Xbox 360",),
        url="https://github.com/xenia-manager/xenia-manager/releases/download/3.1.3/xenia_manager.zip",
        notes="Utilidad para gestionar builds y configuraciones de Xenia.",
    ),
    EmulatorInfo(
        name="Kega Fusion",
        systems=(
            "Master System",
            "Game Gear",
            "Mega Drive / Genesis",
            "Mega-CD / Sega CD",
            "32X",
        ),
        url="https://retrocdn.net/images/6/6c/Fusion364.7z",
        notes="Colección clásica para sistemas de SEGA de 8 y 16 bits, Mega-CD y 32X.",
    ),
    EmulatorInfo(
        name="Emulicious",
        systems=("Game Boy", "Game Boy Color", "Master System", "Game Gear", "MSX"),
        url="https://emulicious.net/download/emulicious/?wpdmdl=205&refresh=68c94602632ae1758021122",
        notes="Incluye emuladores de Game Boy, Game Gear/Master System y MSX.",
    ),
    EmulatorInfo(
        name="Ymir",
        systems=("Saturn",),
        url="https://github.com/StrikerX3/Ymir/releases/download/v0.1.8/ymir-windows-x86_64-AVX2-v0.1.8.zip",
        notes="Emulador moderno de Sega Saturn con renderizado Vulkan.",
    ),
    EmulatorInfo(
        name="YabaSanshiro",
        systems=("Saturn",),
        url="https://d1t36rsydvwkyk.cloudfront.net/yabasanshiro-1.16.7-153d01.zip",
        notes="Port actualizado del emulador Yabause para Sega Saturn.",
    ),
    EmulatorInfo(
        name="SSF",
        systems=("Saturn",),
        url="https://github.com/shimazzz/SEGASaturnEmulator-SSF/releases/download/PreviewVer/SSF_PreviewVer_R36.zip",
        notes="Emulador histórico de Sega Saturn. Requiere BIOS para compatibilidad completa.",
    ),
    EmulatorInfo(
        name="Redream",
        systems=("Dreamcast",),
        url="https://redream.io/download/redream.x86_64-windows-v1.5.0-1133-g03c2ae9.zip",
        notes="Emulador comercial de Dreamcast con soporte para renderizado en alta definición.",
    ),
    EmulatorInfo(
        name="Flycast",
        systems=("Dreamcast",),
        url="https://github.com/flyinghead/flycast/releases/download/v2.5/flycast-win64-2.5.zip",
        notes="Proyecto de código abierto para Dreamcast con soporte para NetLink y Naomi."
    ),
)


def get_emulator_catalog() -> List[EmulatorInfo]:
    """Devuelve el catálogo completo ordenado alfabéticamente."""

    return sorted(EMULATOR_CATALOG, key=lambda e: e.name.lower())


def get_all_systems() -> List[str]:
    """Lista todos los sistemas soportados ordenados alfabéticamente."""

    systems = {system for emu in EMULATOR_CATALOG for system in emu.systems}
    return sorted(systems, key=lambda s: s.lower())


def get_emulators_for_system(system: str) -> List[EmulatorInfo]:
    """Filtra el catálogo por sistema. Si ``system`` está vacío, devuelve todos."""

    normalized = system.strip()
    if not normalized:
        return get_emulator_catalog()
    normalized_lower = normalized.lower()
    filtered = [
        emu for emu in EMULATOR_CATALOG if any(s.lower() == normalized_lower for s in emu.systems)
    ]
    return sorted(filtered, key=lambda e: e.name.lower())


def find_emulator(name: str) -> Optional[EmulatorInfo]:
    """Busca un emulador por nombre exacto (ignorando mayúsculas/minúsculas)."""

    target = name.strip().lower()
    for emu in EMULATOR_CATALOG:
        if emu.name.lower() == target:
            return emu
    return None


def fetch_emulators() -> List[Dict[str, str]]:
    """Compatibilidad retro: devuelve el catálogo en formato de diccionarios simples."""

    return [emu.to_record() for emu in get_emulator_catalog()]


def search_emulators(query: str, catalog: Optional[Sequence[Dict[str, str]]] = None) -> List[Dict[str, str]]:
    """Compatibilidad retro: filtra un catálogo simple por nombre o sistema."""

    data = catalog if catalog is not None else fetch_emulators()
    if not query:
        return list(data)
    q = query.lower()
    return [e for e in data if q in e.get("name", "").lower() or q in e.get("system", "").lower()]
