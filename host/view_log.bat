@echo off
REM view_log.bat - Open host.log in Notepad for review
set LOG=%~dp0host.log

if not exist "%LOG%" (
    echo Log file not found: %LOG%
    echo Run the extension first to generate logs.
    pause
    exit /b 1
)

start notepad "%LOG%"
