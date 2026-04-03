@echo off
setlocal
color 0B
echo ============================================
echo  YT Downloader - Quick Installer
echo ============================================
echo.
echo Please follow the instructions to link the background
echo program to your Chrome extension.
echo.
echo 1. Open your Chrome browser
echo 2. Go to: chrome://extensions/
echo 3. Find "YT Downloader"
echo 4. Copy the "ID" (it is a 32-letter code)
echo.

set /p EXT_ID="Paste the Extension ID here and press Enter: "

if "%EXT_ID%"=="" (
    color 0C
    echo [ERROR] Extension ID is required.
    pause
    exit /b 1
)

:: Use PowerShell to do the heavy lifting: generate JSON and register
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { ^
    $ErrorActionPreference = 'Stop'; ^
    $HostDir = Join-Path $PWD 'host'; ^
    $HostExe = Join-Path $HostDir 'host.exe'; ^
    if (-not (Test-Path $HostExe)) { Write-Error 'host.exe not found in host directory!' }; ^
    $ManifestOut = Join-Path $HostDir 'host_manifest_installed.json'; ^
    $ExeFwd = $HostExe -replace [regex]::Escape('\'), '\\'; ^
    $json = '{`n  \"name\": \"com.ytdownloader.host\",`n  \"description\": \"YT Downloader Native Messaging Host\",`n  \"path\": \"' + $ExeFwd + '\",`n  \"type\": \"stdio\",`n  \"allowed_origins\": [`n    \"chrome-extension://%EXT_ID%/\"`n  ]`n}'; ^
    [System.IO.File]::WriteAllText($ManifestOut, $json, [System.Text.Encoding]::UTF8); ^
    Write-Host '[OK] Generated manifest file.' -ForegroundColor Green; ^
    $RegPath = 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.ytdownloader.host'; ^
    New-Item -Path $RegPath -Force | Out-Null; ^
    Set-ItemProperty -Path $RegPath -Name '(default)' -Value $ManifestOut; ^
    Write-Host '[OK] Registered with Google Chrome!' -ForegroundColor Green; ^
}"

if %errorlevel% neq 0 (
    color 0C
    echo.
    echo [ERROR] Installation failed. Please check the error above.
    pause
    exit /b 1
)

color 0A
echo.
echo ============================================
echo  Installation Complete!
echo ============================================
echo.
echo You can now close this window, restart Chrome, and start downloading!
echo.
pause
