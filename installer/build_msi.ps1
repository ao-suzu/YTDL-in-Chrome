# build_msi.ps1
# Builds the YT Downloader MSI installer using WiX SDK Project.
# Usage: .\build_msi.ps1
#
# Prerequisites:
#   - .NET SDK 9.0+

$ErrorActionPreference = "Stop"

$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutputDir = Join-Path $InstallerDir "output"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " YT Downloader - MSI Build (SDK version)" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host ""

# Ensure output directory exists
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Check that source files exist
$requiredFiles = @(
    "..\host\host.py",
    "..\host\host_manifest.json",
    "..\host\yt-dlp.exe",
    "..\host\ffmpeg.exe",
    "..\extension\manifest.json",
    "..\extension\background.js",
    "..\extension\content.js",
    "..\extension\panel.html",
    "..\extension\panel.js",
    "..\extension\icons\icon16.png",
    "..\extension\icons\icon48.png",
    "..\extension\icons\icon128.png"
)

Write-Host "[1/3] Checking source files..." -ForegroundColor Yellow
Set-Location $InstallerDir
foreach ($file in $requiredFiles) {
    $fullPath = Join-Path $InstallerDir $file
    if (-not (Test-Path $fullPath)) {
        Write-Host "[ERROR] Missing: $file" -ForegroundColor Red
        exit 1
    }
}
Write-Host "      All source files found." -ForegroundColor Green

# Build MSI using dotnet build
Write-Host "[2/3] Building MSI..." -ForegroundColor Yellow

try {
    # Clean output first
    dotnet clean -c Release

    # Build project
    dotnet build -c Release -o output

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] dotnet build failed with exit code $LASTEXITCODE" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "[ERROR] dotnet build failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host "      MSI created successfully!" -ForegroundColor Green

# Verify output
Write-Host "[3/3] Verifying output..." -ForegroundColor Yellow
$msiOutput = Join-Path $OutputDir "YTDownloader_Setup.msi"
if (Test-Path $msiOutput) {
    $size = (Get-Item $msiOutput).Length / 1MB
    Write-Host "      Output: $msiOutput" -ForegroundColor Green
    Write-Host "      Size: $([math]::Round($size, 1)) MB" -ForegroundColor Green
} else {
    # Sometimes output is placed in bin\Release\package/ or similar. Check bin output too.
    $binMsi = Get-ChildItem -Path $InstallerDir -Filter "YTDownloader_Setup.msi" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($binMsi) {
        Copy-Item -Path $binMsi.FullName -Destination $msiOutput -Force
        $size = (Get-Item $msiOutput).Length / 1MB
        Write-Host "      Output: $msiOutput" -ForegroundColor Green
        Write-Host "      Size: $([math]::Round($size, 1)) MB" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] MSI file was not created!" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Build complete!" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host ""
