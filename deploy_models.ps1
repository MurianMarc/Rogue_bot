param(
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$runBot = Join-Path $root "run_bot.ps1"
$optimizer = Join-Path $root "scripts\optimize_models.py"

function Write-Step {
    param([string]$Message)
    Write-Host "[deploy] $Message"
}

function Stop-Bot {
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*python.exe* -m bot*" -or
        $_.CommandLine -like "*python3.13.exe* -m bot*"
    }

    foreach ($process in $processes) {
        Write-Step "Stopping bot process $($process.ProcessId)."
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Start-Bot {
    if (-not (Test-Path -LiteralPath $runBot)) {
        throw "Missing run_bot.ps1."
    }

    Write-Step "Starting Rogue Bot."
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ('"' + $runBot + '"')
    ) -WorkingDirectory $root
}

Set-Location -LiteralPath $root

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing virtual environment Python at $python"
}

if (-not (Test-Path -LiteralPath $optimizer)) {
    throw "Missing optimizer script at $optimizer"
}

& $python $optimizer --pull --warm

if (-not $NoRestart) {
    Stop-Bot
    Start-Bot
}

Write-Step "Deployment complete."
