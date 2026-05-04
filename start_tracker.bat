@echo off
chcp 65001 >nul
setlocal

REM JoyTalk Item Tracker launcher
REM   Double-click           -> menu
REM   start_tracker.bat <preset_name>          -> run preset directly
REM   start_tracker.bat custom "<args>"        -> pass raw args

cd /d "%~dp0tools"

if not "%~1"=="" goto direct

echo.
echo ============================
echo   JoyTalk Item Tracker
echo ============================
echo.
echo   1. default       (notify only + web UI)
echo   2. flower_farm   (auto pickup flowers)
echo   3. wander        (auto pickup + idle patrol)
echo   4. map_rotate    (auto pickup + map cycling)
echo   5. custom        (enter args manually)
echo.
set /p choice="Select [1-5]: "

if "%choice%"=="1" set PRESET=default
if "%choice%"=="2" set PRESET=flower_farm
if "%choice%"=="3" set PRESET=wander
if "%choice%"=="4" set PRESET=map_rotate
if "%choice%"=="5" goto custom

if not defined PRESET (
    echo Invalid choice.
    pause
    exit /b 1
)

py -3.11 -m item_tracker --preset %PRESET%
pause
exit /b

:custom
set /p extra="Args (e.g. --filter flower --pickup --web): "
py -3.11 -m item_tracker %extra%
pause
exit /b

:direct
if "%~1"=="custom" (
    py -3.11 -m item_tracker %~2
) else (
    py -3.11 -m item_tracker --preset %~1
)
pause
exit /b
