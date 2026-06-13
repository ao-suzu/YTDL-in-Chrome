# build_dist.ps1
# originalのソースをビルドし、distに一般向けEXEパッケージとしてコピーするスクリプト
# Usage: .\build_dist.ps1

$ErrorActionPreference = "Stop"

$OriginalDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir     = Join-Path $OriginalDir "dist"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " YT Downloader - Build Dist (EXE Version)" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host "  From : $OriginalDir"
Write-Host "  To   : $DistDir"
Write-Host ""

# --- 0. Compile host.exe using PyInstaller -------------------
Write-Host "[0/4] Compiling host.exe using PyInstaller..." -ForegroundColor Yellow
$HostSrcDir = Join-Path $OriginalDir "host"
Set-Location $HostSrcDir
try {
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist_py") { Remove-Item -Recurse -Force "dist_py" }
    
    # 既存の "dist" サブディレクトリとかぶらないよう PyInstallerの出力先を変更
    python -m PyInstaller host.spec --distpath dist_py
} catch {
    Write-Host "[ERROR] PyInstaller failed." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "dist_py\host.exe")) {
    Write-Host "[ERROR] host.exe was not created!" -ForegroundColor Red
    exit 1
}
Write-Host "      OK" -ForegroundColor Green

# --- 1. Clean Dist ------------------------------------------
Write-Host "[1/4] Cleaning Dist directory..." -ForegroundColor Yellow
$HostDistDir = Join-Path $DistDir "host"
if (-not (Test-Path $HostDistDir)) {
    New-Item -ItemType Directory -Path $HostDistDir -Force | Out-Null
} else {
    # 不要なファイルを削除 (yt-dlp, ffmpeg, host.log, node.exe は重い/保持するため残す)
    Get-ChildItem $HostDistDir | Where-Object { $_.Name -notmatch "ffmpeg\.exe|yt-dlp\.exe|host\.log|node\.exe" } | Remove-Item -Recurse -Force
}

$DistExtDir = Join-Path $DistDir "extension"
if (Test-Path $DistExtDir) {
    Remove-Item -Recurse -Force $DistExtDir
}

# dist直下の不要バッチやPythonファイルを削除
Get-ChildItem $DistDir -Filter "*.bat" | Remove-Item -Force
Get-ChildItem $DistDir -Filter "*.py" -ErrorAction SilentlyContinue | Remove-Item -Force
Write-Host "      OK" -ForegroundColor Green

# --- 2. Copy extension ---------------------------------------
Write-Host "[2/4] Copying extension..." -ForegroundColor Yellow
$srcExt = Join-Path $OriginalDir "extension"
Copy-Item -Path "$srcExt" -Destination $DistExtDir -Recurse -Force
Write-Host "      OK" -ForegroundColor Green

# --- 3. Copy host.exe and dependencies ------------------------
Write-Host "[3/4] Copying host.exe and dependencies..." -ForegroundColor Yellow
Copy-Item -Path "dist_py\host.exe" -Destination (Join-Path $HostDistDir "host.exe") -Force

# Copy ffmpeg.exe and yt-dlp.exe from original/host
foreach ($bin in @("ffmpeg.exe", "yt-dlp.exe")) {
    $srcBin = Join-Path $OriginalDir "host\$bin"
    if (Test-Path $srcBin) {
        Copy-Item -Path $srcBin -Destination (Join-Path $HostDistDir $bin) -Force
    }
}

# Copy node.exe (Portable Node.js)
$NodePath = "C:\Program Files\nodejs\node.exe"
if (Test-Path $NodePath) {
    Copy-Item -Path $NodePath -Destination (Join-Path $HostDistDir "node.exe") -Force
    Write-Host "      node.exe OK" -ForegroundColor Green
} else {
    $NodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if ($NodeCmd) {
        Copy-Item -Path $NodeCmd.Source -Destination (Join-Path $HostDistDir "node.exe") -Force
        Write-Host "      node.exe OK (from PATH)" -ForegroundColor Green
    } else {
        Write-Host "      Warning: node.exe not found. Portable Node.js was not bundled." -ForegroundColor Magenta
    }
}
Write-Host "      OK" -ForegroundColor Green

# --- 4. Copy Installers & README -----------------------------
Write-Host "[4/4] Copying Installer and README..." -ForegroundColor Yellow
$dstInstall = Join-Path $DistDir "install.bat"
$installBatContent = @"
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
    `$ErrorActionPreference = 'Stop'; ^
    `$HostDir = Join-Path `$PWD 'host'; ^
    `$HostExe = Join-Path `$HostDir 'host.exe'; ^
    if (-not (Test-Path `$HostExe)) { Write-Error 'host.exe not found in host directory!' }; ^
    `$ManifestOut = Join-Path `$HostDir 'host_manifest_installed.json'; ^
    `$ExeFwd = `$HostExe -replace [regex]::Escape('\'), '\\'; ^
    `$json = '{``n  \"name\": \"com.ytdownloader.host\",``n  \"description\": \"YT Downloader Native Messaging Host\",``n  \"path\": \"' + `$ExeFwd + '\",``n  \"type\": \"stdio\",``n  \"allowed_origins\": [``n    \"chrome-extension://%EXT_ID%/\"``n  ]``n}'; ^
    [System.IO.File]::WriteAllText(`$ManifestOut, `$json, [System.Text.Encoding]::UTF8); ^
    Write-Host '[OK] Generated manifest file.' -ForegroundColor Green; ^
    `$RegPath = 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.ytdownloader.host'; ^
    New-Item -Path `$RegPath -Force | Out-Null; ^
    Set-ItemProperty -Path `$RegPath -Name '(default)' -Value `$ManifestOut; ^
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
"@

[System.IO.File]::WriteAllText($dstInstall, $installBatContent, [System.Text.Encoding]::Default)
Write-Host "      install.bat OK (Generated)" -ForegroundColor Green

$srcReadme = Join-Path $OriginalDir "README.md"
$dstReadme = Join-Path $DistDir "README.md"
if (Test-Path $srcReadme) {
    Copy-Item -Path $srcReadme -Destination $dstReadme -Force
    Write-Host "      README.md OK" -ForegroundColor Green
}

# --- 5. Clean Temporary Build Files ---------------------------
Write-Host "Cleaning temporary PyInstaller folders..." -ForegroundColor Yellow
$HostSrcDir = Join-Path $OriginalDir "host"
Set-Location $HostSrcDir
# プロセスがファイルハンドルを解放するのを少し待つよ
Start-Sleep -Seconds 2
if (Test-Path "build") { Remove-Item -Recurse -Force "build" -ErrorAction SilentlyContinue }
if (Test-Path "dist_py") { Remove-Item -Recurse -Force "dist_py" -ErrorAction SilentlyContinue }
Write-Host "      OK" -ForegroundColor Green

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Build complete!" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host ""

Write-Host "Creating ZIP file for distribution..." -ForegroundColor Yellow
$ZipPath = Join-Path $OriginalDir "YTDownloader.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path "$DistDir\*" -DestinationPath $ZipPath -Force
Write-Host "      ZIP created: YTDownloader.zip" -ForegroundColor Green
Write-Host ""
