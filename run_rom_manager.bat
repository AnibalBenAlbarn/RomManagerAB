@echo off
setlocal EnableExtensions

rem =========================================
rem ROM Manager — Launcher (Windows, v3)
rem Crea/usa .venv, instala deps y ejecuta app.
rem =========================================

set "PROJECT_DIR=%~dp0"
pushd "%PROJECT_DIR%"

rem Limpiar variables que pueden romper stdlib
set "PYTHONHOME="
set "PYTHONPATH="

rem Venv paths
set "VENV_DIR=%PROJECT_DIR%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PYW=%VENV_DIR%\Scripts\pythonw.exe"

rem Python del sistema
where py >NUL 2>&1 && (set "PY_BOOT=py -3") || (set "PY_BOOT=python")

rem Crear venv si no existe
if not exist "%VENV_PY%" (
  echo [SETUP] Creando entorno virtual .venv ...
  %PY_BOOT% -m venv "%VENV_DIR%" --upgrade-deps >NUL 2>&1
  if errorlevel 1 (
    %PY_BOOT% -m venv "%VENV_DIR%"
  )
)

rem Asegurar pip
call :ensure_pip || goto pip_fail

rem Actualizar pip
"%VENV_PY%" -m pip install --upgrade pip >NUL 2>&1

rem Instalar dependencias
if exist "%PROJECT_DIR%requirements.txt" (
  echo [SETUP] Instalando dependencias ...
  "%VENV_PY%" -m pip install -r "%PROJECT_DIR%requirements.txt" || goto pip_fail
) else (
  echo [SETUP] Instalando PyQt6 y requests ...
  "%VENV_PY%" -m pip install PyQt6 requests || goto pip_fail
)

rem Elegir entrypoint
set "ENTRY="
if exist "%PROJECT_DIR%rom_manager\main.py" (
  set "ENTRY=-m rom_manager.main"
) else (
  if exist "%PROJECT_DIR%main.py" (
    set "ENTRY=%PROJECT_DIR%main.py"
  ) else (
    echo [ERROR] No encuentro rom_manager\main.py ni main.py
    exit /b 1
  )
)

rem Ejecutar (por defecto GUI sin consola; usa --console para ver logs)
if /i "%~1"=="--console" goto RUN_CONSOLE
goto RUN_GUI

:RUN_CONSOLE
echo [RUN] Lanzando en consola...
"%VENV_PY%" %ENTRY% %*
goto END

:RUN_GUI
echo [RUN] Lanzando ROM Manager...
"%VENV_PYW%" %ENTRY% %*
goto END

:ensure_pip
"%VENV_PY%" -m pip --version >NUL 2>&1 && exit /b 0
echo [SETUP] Bootstrapping pip con ensurepip ...
"%VENV_PY%" -m ensurepip --upgrade >NUL 2>&1
"%VENV_PY%" -m pip --version >NUL 2>&1 && exit /b 0
echo [SETUP] Descargando get-pip.py ...
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing https://bootstrap.pypa.io/get-pip.py -OutFile \"%TEMP%\\get-pip.py\"" || exit /b 1
"%VENV_PY%" "%TEMP%\get-pip.py" || exit /b 1
exit /b 0

:pip_fail
echo [ERROR] Fallo instalando dependencias. Revisa conexion o permisos.
exit /b 1

:END
popd
endlocal
