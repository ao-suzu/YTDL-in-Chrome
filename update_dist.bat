@echo off
setlocal
color 0B
echo ============================================
echo  YT Downloader - Update dist folder
echo ============================================
echo.
echo Please select an option:
echo [1] Update All (Rebuild host.exe + Copy all files)
echo [2] Fast Update (Copy non-executable files only)
echo.

set /p CHOICE="Enter your choice (1 or 2): "

if "%CHOICE%"=="2" goto fast_update
goto update_all

:fast_update
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $ErrorActionPreference='Stop'; $OriginalDir='%~dp0'; $DistDir=Join-Path $OriginalDir 'dist'; Write-Host '[2/4] Copying extension...' -ForegroundColor Yellow; $srcExt=Join-Path $OriginalDir 'extension'; $DistExtDir=Join-Path $DistDir 'extension'; if(Test-Path $DistExtDir){Remove-Item -Recurse -Force $DistExtDir}; Copy-Item -Path $srcExt -Destination $DistExtDir -Recurse -Force; Write-Host '      OK' -ForegroundColor Green; Write-Host '[4/4] Copying README...' -ForegroundColor Yellow; $srcReadme=Join-Path $OriginalDir 'README.md'; $dstReadme=Join-Path $DistDir 'README.md'; if(Test-Path $srcReadme){Copy-Item -Path $srcReadme -Destination $dstReadme -Force}; Write-Host '      OK' -ForegroundColor Green; Write-Host ''; Write-Host '============================================' -ForegroundColor Cyan; Write-Host ' Update complete! (Fast Mode)' -ForegroundColor Cyan; Write-Host '============================================' -ForegroundColor Cyan; Write-Host ''; Write-Host 'Creating ZIP file for distribution...' -ForegroundColor Yellow; $ZipPath=Join-Path $OriginalDir 'YTDownloader.zip'; if(Test-Path $ZipPath){Remove-Item -Force $ZipPath}; Compress-Archive -Path \"$DistDir\*\" -DestinationPath $ZipPath -Force; Write-Host '      ZIP created: YTDownloader.zip' -ForegroundColor Green; Write-Host ''; }"
goto end

:update_all
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_dist.ps1"
goto end

:end
echo.
pause
