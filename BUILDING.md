# Construcción y empaquetado

La aplicación crea automáticamente las carpetas `logs/`, `config/` y `sessions/`
en el mismo directorio que el ejecutable cada vez que se inicia. Dentro de
ellas se guardan los registros (`logs/rom_manager.log`), la configuración en
JSON (`config/settings.json`) y las sesiones de descarga (`sessions/*.json`).

Para generar el ejecutable con PyInstaller desde la raíz del repositorio se
puede utilizar el siguiente comando en una sola línea:

```
pyinstaller --noconfirm --clean --name "RomManager" --add-data "resources/romMan.ico;resources" --windowed rom_manager/main.py
```

El ejecutable resultante heredará la misma estructura de carpetas cuando se
publique o distribuya.
