# ROM Manager AB

> 🇬🇧 **Hook:** Turbo-charge your retro library with a PyQt6-powered ROM dashboard that keeps downloads, emulators, and metadata perfectly in sync.
>
> 🇪🇸 **Gancho:** Impulsa tu colección retro con un panel PyQt6 que armoniza descargas, emuladores y metadatos sin perder un solo detalle.

---

## English 🇬🇧

### Overview
ROM Manager AB is a desktop companion app for curating large ROM collections. Built with PyQt6, it mirrors the feature set of the original JavaFX tool while adding a modern download queue, emulator catalog, and persistent configuration folders (`logs/`, `config/`, `sessions/`).【F:rom_manager/main.py†L1-L59】【F:rom_manager/paths.py†L1-L55】

### Feature highlights
- **Smart ROM browser:** Connect to your SQLite catalog and filter by system, language, region, format, or free-text search from a single pane.【F:rom_manager/database.py†L13-L146】【F:rom_manager/gui/main_window.py†L108-L208】
- **Download basket workflow:** Stage multiple ROMs, fine-tune server/format selections, and push them to the queue in one click from the Selector tab.【F:rom_manager/gui/main_window.py†L280-L377】【F:rom_manager/gui/main_window.py†L1989-L2171】
- **Concurrent download manager:** Pause, resume, cancel, and verify checksums while streaming large files with HTTP range support and retry logic.【F:rom_manager/download.py†L1-L210】【F:rom_manager/download.py†L211-L341】
- **Background-friendly:** Switch to a system-tray mode so long downloads keep running even when the main window is hidden.【F:rom_manager/gui/main_window.py†L59-L157】
- **Curated emulator catalog:** Browse a static database of popular emulators, jump to official download links, and grab extras per system.【F:rom_manager/emulators.py†L1-L199】【F:rom_manager/gui/main_window.py†L378-L486】

### Quick start
1. **Clone & setup:** `python -m venv .venv && source .venv/bin/activate` (or `Scripts\activate`) then `pip install -r requirements.txt` to pull PyQt6, requests, and py7zr for automatic .7z extraction.【F:requirements.txt†L1-L3】
2. **Launch:** Run `python -m rom_manager.main` to open the GUI with logging preconfigured and directories created on first launch.【F:rom_manager/main.py†L1-L59】【F:rom_manager/paths.py†L23-L55】
3. **Point to your database:** Use the *Settings → Database* controls to select the SQLite file that contains your ROM metadata.
4. **Choose a download folder:** Configure concurrency (1–5), optional auto-extraction, and session persistence from *Settings → Downloads*.【F:rom_manager/gui/main_window.py†L209-L332】

### Database expectations
The app reads from an SQLite database that matches the schema used by the JavaFX edition: `roms`, `links`, `systems`, `languages`, `regions`, plus bridge tables such as `link_languages` and `rom_regions`. Hash columns are optional but enable post-download integrity checks.【F:rom_manager/database.py†L13-L146】【F:rom_manager/gui/main_window.py†L782-L814】

### Emulator catalog & extras
The *Emulators* tab offers a filtered dropdown per system, notes, and extra download links (e.g., alternate builds). Downloads land in your chosen folder and can be auto-extracted with the same logic as ROMs.【F:rom_manager/emulators.py†L1-L199】【F:rom_manager/gui/main_window.py†L378-L486】

### Download workflow & sessions
Add items from search results or the basket to the queue. The manager enforces concurrency limits, streams to `.part` files, and swaps them atomically once finished. You can persist and restore sessions, enabling long-term batch transfers without losing progress.【F:rom_manager/download.py†L1-L341】【F:rom_manager/gui/main_window.py†L118-L207】【F:rom_manager/gui/main_window.py†L1408-L1546】

### Building a desktop release
Create a standalone executable with PyInstaller using the bundled spec file:
```bash
pyinstaller --noconfirm --clean RomManager.spec
```
The generated binary recreates the same directory layout (`logs/`, `config/`, `sessions/`) alongside the executable when shipped.【F:BUILDING.md†L1-L14】

### Repository layout
```
rom_manager/         # Application package (entrypoint, GUI, downloads, models)
resources/           # Icons bundled into the desktop build
requirements.txt     # Minimal runtime dependencies
BUILDING.md          # PyInstaller packaging instructions
```

### Disclaimer
ROM Manager AB does not distribute ROMs. Ensure you comply with local laws and only download content you own the rights to preserve.

---

## Español 🇪🇸

### Panorama general
ROM Manager AB es una aplicación de escritorio para organizar colecciones extensas de ROMs. Desarrollada con PyQt6, replica la edición original en JavaFX y añade cola de descargas moderna, catálogo de emuladores y carpetas de configuración persistentes (`logs/`, `config/`, `sessions/`).【F:rom_manager/main.py†L1-L59】【F:rom_manager/paths.py†L1-L55】

### Funciones clave
- **Buscador inteligente de ROMs:** Conecta tu catálogo SQLite y filtra por sistema, idioma, región, formato o texto libre desde un único panel.【F:rom_manager/database.py†L13-L146】【F:rom_manager/gui/main_window.py†L108-L208】
- **Flujo con cesta de descargas:** Agrupa varias ROMs, ajusta servidor y formato, y envíalas a la cola con un solo clic desde la pestaña Selector.【F:rom_manager/gui/main_window.py†L280-L377】【F:rom_manager/gui/main_window.py†L1989-L2171】
- **Gestor de descargas concurrentes:** Pausa, reanuda, cancela y verifica hashes mientras transfieres archivos grandes con soporte Range y reintentos.【F:rom_manager/download.py†L1-L210】【F:rom_manager/download.py†L211-L341】
- **Modo en segundo plano:** Oculta la ventana principal y continúa las descargas mediante un icono en la bandeja del sistema.【F:rom_manager/gui/main_window.py†L59-L157】
- **Catálogo curado de emuladores:** Explora una base estática de emuladores populares, abre enlaces oficiales y descarga extras por sistema.【F:rom_manager/emulators.py†L1-L199】【F:rom_manager/gui/main_window.py†L378-L486】

### Puesta en marcha
1. **Clona y prepara el entorno:** `python -m venv .venv && source .venv/bin/activate` (o `Scripts\activate`) y luego `pip install -r requirements.txt` para instalar PyQt6, requests y py7zr para la extracción automática de .7z.【F:requirements.txt†L1-L3】
2. **Inicia la aplicación:** Ejecuta `python -m rom_manager.main`; la GUI se abre con el logging y las carpetas creadas automáticamente.【F:rom_manager/main.py†L1-L59】【F:rom_manager/paths.py†L23-L55】
3. **Selecciona tu base de datos:** Desde *Ajustes → Base de datos* elige el archivo SQLite con los metadatos de tus ROMs.
4. **Configura la carpeta de descargas:** Ajusta concurrencia (1–5), auto-descompresión y sesiones desde *Ajustes → Descargas*.【F:rom_manager/gui/main_window.py†L209-L332】

### Base de datos esperada
La aplicación lee una base SQLite con el mismo esquema que la edición JavaFX: tablas `roms`, `links`, `systems`, `languages`, `regions` y tablas puente como `link_languages` y `rom_regions`. La columna `hash` es opcional, pero habilita verificaciones de integridad tras cada descarga.【F:rom_manager/database.py†L13-L146】【F:rom_manager/gui/main_window.py†L782-L814】

### Catálogo de emuladores y extras
La pestaña *Emuladores* ofrece desplegables filtrados por sistema, notas y enlaces adicionales (p. ej. builds alternativos). Las descargas se guardan en la carpeta elegida y pueden descomprimirse con la misma lógica que las ROMs.【F:rom_manager/emulators.py†L1-L199】【F:rom_manager/gui/main_window.py†L378-L486】

### Flujo de descargas y sesiones
Añade elementos desde los resultados o la cesta a la cola. El gestor respeta el límite de concurrencia, escribe en archivos `.part` y los reemplaza al terminar. Puedes guardar y restaurar sesiones para reanudar lotes largos sin perder progreso.【F:rom_manager/download.py†L1-L341】【F:rom_manager/gui/main_window.py†L118-L207】【F:rom_manager/gui/main_window.py†L1408-L1546】

### Generar un ejecutable de escritorio
Crea un ejecutable independiente con PyInstaller utilizando el spec incluido:
```bash
pyinstaller --noconfirm --clean RomManager.spec
```
El binario generado recrea la misma estructura de carpetas (`logs/`, `config/`, `sessions/`) junto al ejecutable al distribuirlo.【F:BUILDING.md†L1-L14】

### Estructura del repositorio
```
rom_manager/         # Paquete de la aplicación (entrypoint, GUI, descargas, modelos)
resources/           # Iconos incluidos en el ejecutable
requirements.txt     # Dependencias mínimas de ejecución
BUILDING.md          # Guía de empaquetado con PyInstaller
```

### Aviso
ROM Manager AB no distribuye ROMs. Respeta la legislación de tu país y descarga únicamente contenido que tengas derecho a preservar.
