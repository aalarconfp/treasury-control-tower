@echo off
REM Actualiza los datos del dashboard desde los libros Excel (solo lectura).
cd /d "%~dp0.."
python scripts\refresh_dashboard.py %*
if errorlevel 1 (
  echo.
  echo Refresh FALLIDO - revise los mensajes. Se conservaron los datos anteriores.
) else (
  echo.
  echo Listo. Abra index.html para ver el dashboard.
)
pause
