$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "logs"
$envFile = Join-Path $root ".env"
$envExample = Join-Path $root ".env.example"
$runtimeBin = Join-Path $root ".runtime\bin"
$ffmpegInstaller = Join-Path $root "install_ffmpeg.ps1"

if (-not (Test-Path -LiteralPath $logs)) {
    New-Item -ItemType Directory -Path $logs | Out-Null
}

$logFile = Join-Path $logs ("rogue-bot-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

function Write-Log {
    param([string]$Message)
    $line = "[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] " + $Message
    Add-Content -LiteralPath $logFile -Value $line
    Write-Host $line
}

function Test-OllamaApi {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Add-RuntimeBinToPath {
    if ((Test-Path -LiteralPath $runtimeBin) -and -not ($env:PATH.Split([IO.Path]::PathSeparator) -contains $runtimeBin)) {
        $env:PATH = $runtimeBin + [IO.Path]::PathSeparator + $env:PATH
    }
}

function Test-CommandAvailable {
    param([string]$Name)

    Add-RuntimeBinToPath
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Set-Location -LiteralPath $root
Write-Log "Starting Rogue Bot launcher."

if (-not (Test-Path -LiteralPath $python)) {
    Write-Log "Missing virtual environment Python at $python"
    exit 1
}

if (-not (Test-Path -LiteralPath $envFile) -and (Test-Path -LiteralPath $envExample)) {
    Copy-Item -LiteralPath $envExample -Destination $envFile
    Write-Log "Created .env from .env.example."
}

Add-RuntimeBinToPath
if ((-not (Test-CommandAvailable "ffmpeg")) -or (-not (Test-CommandAvailable "ffprobe"))) {
    if (Test-Path -LiteralPath $ffmpegInstaller) {
        try {
            Write-Log "Installing local FFmpeg tools for stickers."
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ffmpegInstaller *>> $logFile
            Add-RuntimeBinToPath
        } catch {
            Write-Log "Could not install FFmpeg tools automatically: $_"
        }
    } else {
        Write-Log "FFmpeg tools are missing; stickers that need conversion may fail."
    }
}

$ollamaPath = $null
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    $ollamaPath = $ollama.Source
} else {
    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path -LiteralPath $candidate) {
        $ollamaPath = $candidate
        $env:PATH = (Split-Path -Parent $candidate) + ";" + $env:PATH
    }
}

if (-not (Test-OllamaApi)) {
    if (-not $ollamaPath) {
        Write-Log "Ollama is not installed or not on PATH."
    } else {
        Write-Log "Starting Ollama server."
        Start-Process -FilePath $ollamaPath -ArgumentList "serve" -WindowStyle Hidden
        for ($i = 0; $i -lt 20; $i++) {
            Start-Sleep -Seconds 1
            if (Test-OllamaApi) {
                Write-Log "Ollama API is ready."
                break
            }
        }
    }
} else {
    Write-Log "Ollama API is already running."
}

Write-Log "Launching bot. Live output will also be written to $logFile"
$env:PYTHONUNBUFFERED = "1"
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    & $python -u -m bot 2>&1 | ForEach-Object {
        $line = $_.ToString()
        Add-Content -LiteralPath $logFile -Value $line
        Write-Host $line
    }
    $exitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
Write-Log "Bot process stopped with exit code $exitCode."
exit $exitCode
