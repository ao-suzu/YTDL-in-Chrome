$ErrorActionPreference = "Stop"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " YT Downloader - Native Host Installer" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host ""
$HostDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$HostPy  = Join-Path $HostDir "host.py"

# Find Python
$PythonPath = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python") {
            $PythonPath = (Get-Command $candidate -ErrorAction SilentlyContinue).Source
            if (-not $PythonPath) { $PythonPath = $candidate }
            Write-Host "[OK] Python: $PythonPath ($ver)" -ForegroundColor Green
            break
        }
    } catch {}
}
if (-not $PythonPath) {
    Write-Host "[ERROR] Python not found. Please install Python and try again." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Install yt-dlp and pillow via pip
Write-Host ""
Write-Host "Installing Python dependencies (yt-dlp[default], pillow, mutagen)..." -ForegroundColor Yellow
try {
    & $PythonPath -m pip install -U "yt-dlp[default]" pillow mutagen
    Write-Host "[OK] Dependencies installed!" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to install dependencies: $_" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check for JS runtime (Deno or Node.js)
Write-Host ""
Write-Host "Checking for JavaScript runtime (Deno or Node.js)..." -ForegroundColor Yellow
$HasDeno = $false
$HasNode = $false

try {
    $denoVer = & deno --version 2>&1
    if ($denoVer -match "deno") {
        Write-Host "[OK] Deno found!" -ForegroundColor Green
        $HasDeno = $true
    }
} catch {}

if (-not $HasDeno) {
    try {
        $nodeVer = & node --version 2>&1
        if ($nodeVer -match "v") {
            Write-Host "[OK] Node.js found: $nodeVer" -ForegroundColor Green
            $HasNode = $true
        }
    } catch {}
}

if (-not $HasDeno -and -not $HasNode) {
    Write-Host ""
    Write-Host "[WARNING] Node.js or Deno was not found in your PATH." -ForegroundColor Yellow
    Write-Host "Without a JS runtime, YouTube downloads may fail, be extremely slow, or be unstable." -ForegroundColor Yellow
    Write-Host "We highly recommend installing Deno (https://deno.com/) or Node.js (https://nodejs.org/)." -ForegroundColor Yellow
    Write-Host ""
}

# Extension ID
Write-Host ""
Write-Host "-----------------------------------------------"
Write-Host " Open chrome://extensions/"
Write-Host " Enter the Extension ID (32 chars)"
Write-Host "-----------------------------------------------"
$ExtId = Read-Host "Extension ID"
if ([string]::IsNullOrWhiteSpace($ExtId)) {
    Write-Host "[ERROR] Extension ID not entered." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Generate host_runner.bat
$RunnerBat = Join-Path $HostDir "host_runner.bat"
$RunnerContent = "@echo off`r`n" + [char]34 + $PythonPath + [char]34 + " " + [char]34 + $HostPy + [char]34 + "`r`n"
[System.IO.File]::WriteAllText($RunnerBat, $RunnerContent, [System.Text.Encoding]::Default)
Write-Host "[OK] Runner: $RunnerBat" -ForegroundColor Green

# Generate host_manifest_installed.json
$ManifestOut = Join-Path $HostDir "host_manifest_installed.json"
$RunnerFwd = $RunnerBat -replace [regex]::Escape("\"), "\\\\"
$json = "{`n  `"name`": `"com.ytdownloader.host`",`n  `"description`": `"YT Downloader Native Messaging Host`",`n  `"path`": `"$RunnerFwd`",`n  `"type`": `"stdio`",`n  `"allowed_origins`": [`n    `"chrome-extension://$ExtId/`"`n  ]`n}"
[System.IO.File]::WriteAllText($ManifestOut, $json, [System.Text.Encoding]::UTF8)
Write-Host "[OK] Manifest: $ManifestOut" -ForegroundColor Green

# Register in Windows registry
$RegPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.ytdownloader.host"
try {
    New-Item -Path $RegPath -Force | Out-Null
    Set-ItemProperty -Path $RegPath -Name "(default)" -Value $ManifestOut
    Write-Host "[OK] Registry registered!" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Registry failed: $_" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Install complete!" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host "  1. Restart Chrome"
Write-Host "  2. Open YouTube and click the extension icon"
Write-Host ""
Read-Host "Press Enter to exit"