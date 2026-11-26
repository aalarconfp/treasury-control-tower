@echo off
REM Cierre trimestral: refresh + informes PDF + refresh (cronograma) + validacion.
REM Uso:  scripts\cierre_trimestral.bat 2026 4
cd /d "%~dp0.."
if "%~2"=="" ( echo Uso: scripts\cierre_trimestral.bat ANO TRIMESTRE & pause & exit /b 1 )
python scripts\refresh_dashboard.py || goto :err
python scripts\build_quarterly_reports.py --year %1 --quarter %2 || goto :err
python scripts\refresh_dashboard.py || goto :err
python scripts\validate_system.py
echo.
echo Cierre Q%2-%1 terminado. Revise validation\ y deliverables\%1\.
pause
exit /b 0
:err
echo.
echo Error: se conservaron los datos anteriores. Revise los mensajes.
pause
exit /b 1
