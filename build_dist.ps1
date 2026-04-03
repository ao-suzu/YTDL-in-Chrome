# build_dist.ps1
# originalのソースをビルドし、distに一般向けEXEパッケージとしてコピーするスクリプト
# Usage: .\build_dist.ps1

$ErrorActionPreference = "Stop"

$OriginalDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir     = Join-Path (Split-Path -Parent $OriginalDir) "dist"

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
    # 不要なファイルを削除 (yt-dlp, ffmpeg, host.log は重い/保持するため残す)
    Get-ChildItem $HostDistDir | Where-Object { $_.Name -notmatch "ffmpeg\.exe|yt-dlp\.exe|host\.log" } | Remove-Item -Recurse -Force
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

# --- 3. Copy host.exe ----------------------------------------
Write-Host "[3/4] Copying host.exe..." -ForegroundColor Yellow
Copy-Item -Path "dist_py\host.exe" -Destination (Join-Path $HostDistDir "host.exe") -Force
Write-Host "      OK" -ForegroundColor Green

# --- 4. Copy Installers & README -----------------------------
Write-Host "[4/4] Copying Installer and README..." -ForegroundColor Yellow
$srcInstall = Join-Path $OriginalDir "dist_install.bat"
$dstInstall = Join-Path $DistDir "install.bat"
if (Test-Path $srcInstall) {
    Copy-Item -Path $srcInstall -Destination $dstInstall -Force
    Write-Host "      install.bat OK" -ForegroundColor Green
} else {
    Write-Host "      Warning: dist_install.bat not found in original." -ForegroundColor Magenta
}

$srcReadme = Join-Path $OriginalDir "README.md"
$dstReadme = Join-Path $DistDir "README.md"
if (Test-Path $srcReadme) {
    Copy-Item -Path $srcReadme -Destination $dstReadme -Force
    Write-Host "      README.md OK" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Build complete!" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host ""
