@echo off
REM Thin wrapper — delegates to start_tracker.ps1 (PowerShell handles UTF-8,
REM menu, Read-Host hold-at-end far more reliably than cmd).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_tracker.ps1" %*
