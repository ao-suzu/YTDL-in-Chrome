# setup_host.ps1
# Called by the MSI custom action after file installation.
# Generates host_manifest_installed.json and host_runner.bat.
# Also installs Python pip dependencies if Python is available.

param(
    [Parameter(Mandatory=$true)]
    [string]$ExtensionId,

    [Parameter(Mandatory=$true)]
    [string]$HostDir
)

$ErrorActionPreference = "Stop"

# Normalize paths (remove trailing backslash for consistency)
$HostDir = $HostDir.TrimEnd('\')

# --- 1. Find Python ---
$PythonPath = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python") {
            $PythonPath = (Get-Command $candidate -ErrorAction SilentlyContinue).Source
            if (-not $PythonPath) { $PythonPath = $candidate }
            break
        }
    } catch {}
}

if (-not $PythonPath) {
    # Python not found - create manifest but skip pip install
    # User will need to install Python manually
    $PythonPath = "python"
}

# --- 2. Generate host_runner.bat ---
$RunnerBat = Join-Path $HostDir "host_runner.bat"
$HostPy = Join-Path $HostDir "host.py"
$RunnerContent = "@echo off`r`n`"$PythonPath`" `"$HostPy`"`r`n"
[System.IO.File]::WriteAllText($RunnerBat, $RunnerContent, [System.Text.Encoding]::Default)

# --- 3. Generate host_manifest_installed.json ---
$ManifestOut = Join-Path $HostDir "host_manifest_installed.json"
$RunnerFwd = $RunnerBat -replace [regex]::Escape("\"), "\\"

# Build the JSON - handle empty extension ID gracefully
if ([string]::IsNullOrWhiteSpace($ExtensionId)) {
    $allowedOrigins = "[]"
} else {
    $allowedOrigins = "[`n    `"chrome-extension://$ExtensionId/`"`n  ]"
}

$json = @"
{
  "name": "com.ytdownloader.host",
  "description": "YT Downloader Native Messaging Host",
  "path": "$RunnerFwd",
  "type": "stdio",
  "allowed_origins": $allowedOrigins
}
"@

[System.IO.File]::WriteAllText($ManifestOut, $json, [System.Text.Encoding]::UTF8)

# --- 4. Register in Windows Registry ---
$RegPath = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.ytdownloader.host"
try {
    New-Item -Path $RegPath -Force | Out-Null
    Set-ItemProperty -Path $RegPath -Name "(default)" -Value $ManifestOut
} catch {
    # Non-fatal: user can register manually
}

# --- 5. Install Python dependencies (best effort) ---
if ($PythonPath -ne "python" -or (Get-Command "python" -ErrorAction SilentlyContinue)) {
    try {
        & $PythonPath -m pip install -U yt-dlp pillow mutagen 2>&1 | Out-Null
    } catch {
        # Non-fatal: user can install dependencies manually
    }
}

exit 0
