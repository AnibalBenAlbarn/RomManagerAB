# Construcción y empaquetado

La aplicación crea automáticamente las carpetas `logs/`, `config/` y `sessions/`
en el mismo directorio que el ejecutable cada vez que se inicia. Dentro de
ellas se guardan los registros (`logs/rom_manager.log`), la configuración en
JSON (`config/settings.json`) y las sesiones de descarga (`sessions/*.json`).

Para generar el ejecutable con PyInstaller desde la raíz del repositorio se
incluye el archivo ``RomManager.spec``. Dicho spec fija la ruta del icono y de
los recursos utilizando rutas absolutas, evitando errores cuando el comando se
lanza desde otro directorio. Basta con ejecutar:

```
pyinstaller --noconfirm --clean RomManager.spec
```

PyInstaller leerá el spec y generará el binario ``RomManager/RomManager.exe``
con el icono ``romMan.ico`` incrustado, además de copiar el fichero en la
carpeta ``resources`` del directorio de salida para que la aplicación pueda
referenciarlo.

El ejecutable resultante heredará la misma estructura de carpetas cuando se
publique o distribuya.
