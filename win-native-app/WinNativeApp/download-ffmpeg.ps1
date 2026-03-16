param(
    [string]$OutDir = "resources\ffmpeg"
)

$ErrorActionPreference = "Stop"

$ffmpegExe = Join-Path $OutDir "ffmpeg.exe"
if (Test-Path $ffmpegExe) {
    Write-Host "FFmpeg already exists: $ffmpegExe"
    exit 0
}

$zipName = "ffmpeg-n7.1-latest-win64-gpl-7.1"
$url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/${zipName}.zip"
$tempDir = Join-Path $env:TEMP "ffmpeg-download"
$zipPath = Join-Path $tempDir "${zipName}.zip"

Write-Host "Downloading FFmpeg..."
Write-Host "URL: $url"

New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile $zipPath -UseBasicParsing

Write-Host "Extracting..."
Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

# Copy only ffmpeg.exe (ffprobe/ffplay not needed)
$extractedExe = Join-Path $tempDir "${zipName}\bin\ffmpeg.exe"
if (!(Test-Path $extractedExe)) {
    $extractedExe = Get-ChildItem -Path $tempDir -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1 -ExpandProperty FullName
}

if (!(Test-Path $extractedExe)) {
    Write-Error "ffmpeg.exe not found in archive"
    exit 1
}

Copy-Item $extractedExe $ffmpegExe -Force
Write-Host "FFmpeg installed: $ffmpegExe"

Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue

Write-Host "Done."
