param(
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $root ".env"
$envExample = Join-Path $root ".env.example"
$runBot = Join-Path $root "run_bot.ps1"

function Write-Step {
    param([string]$Message)
    Write-Host "[deploy] $Message"
}

function Test-OllamaApi {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -Method Get -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-OllamaPath {
    $command = Get-Command ollama -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidate = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path -LiteralPath $candidate) {
        $env:PATH = (Split-Path -Parent $candidate) + ";" + $env:PATH
        return $candidate
    }

    throw "Ollama is not installed."
}

function Ensure-OllamaRunning {
    param([string]$OllamaPath)

    if (Test-OllamaApi) {
        Write-Step "Ollama API is already running."
        return
    }

    Write-Step "Starting Ollama server."
    Start-Process -FilePath $OllamaPath -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-OllamaApi) {
            Write-Step "Ollama API is ready."
            return
        }
    }

    throw "Ollama API did not become ready."
}

function Get-TotalVramMiB {
    $nvidia = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if (-not $nvidia) {
        return 0
    }

    $raw = & nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | Select-Object -First 1
    if (-not $raw) {
        return 0
    }

    return [int]($raw.Trim())
}

function Get-CpuCoreCount {
    $cores = (Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum
    if (-not $cores -or $cores -lt 1) {
        return 8
    }
    return [int]$cores
}

function Select-SmartModel {
    param([int]$VramMiB)

    if ($VramMiB -ge 24000) {
        return "qwen3:32b"
    }
    if ($VramMiB -ge 12000) {
        return "qwen3:14b"
    }
    if ($VramMiB -ge 7000) {
        return "qwen3:8b"
    }
    if ($VramMiB -ge 4000) {
        return "qwen3:4b"
    }
    return "qwen3:1.7b"
}

function Set-DotEnvValue {
    param(
        [string]$Name,
        [string]$Value
    )

    if (-not (Test-Path -LiteralPath $envFile)) {
        Copy-Item -LiteralPath $envExample -Destination $envFile
    }

    $lines = @(Get-Content -LiteralPath $envFile)
    $replacement = "$Name=$Value"
    $found = $false

    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^$([regex]::Escape($Name))=") {
            $lines[$i] = $replacement
            $found = $true
        }
    }

    if (-not $found) {
        $lines += $replacement
    }

    [System.IO.File]::WriteAllLines($envFile, $lines)
}

function Warm-Model {
    param(
        [string]$Model,
        [int]$Threads,
        [Nullable[int]]$NumGpu
    )

    $options = @{
        num_predict = 1
        num_thread = $Threads
    }

    if ($null -ne $NumGpu) {
        $options.num_gpu = $NumGpu
    }

    $body = @{
        model = $Model
        stream = $false
        keep_alive = "45m"
        think = $false
        messages = @(@{ role = "user"; content = "Say ok." })
        options = $options
    } | ConvertTo-Json -Depth 8

    Write-Step "Warming $Model."
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/chat" -Method Post -ContentType "application/json" -Body $body | Out-Null
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
    $quotedRunBot = '"' + $runBot + '"'
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $quotedRunBot
    ) -WorkingDirectory $root
}

Set-Location -LiteralPath $root
$ollamaPath = Get-OllamaPath
Ensure-OllamaRunning -OllamaPath $ollamaPath

$vram = Get-TotalVramMiB
$threads = Get-CpuCoreCount
$smartModel = Select-SmartModel -VramMiB $vram
$cpuModel = "qwen3:1.7b"
if ($smartModel -eq $cpuModel) {
    $cpuModel = "qwen3:0.6b"
}

Write-Step "GPU VRAM: $vram MiB."
Write-Step "CPU cores: $threads."
Write-Step "Smart GPU model: $smartModel."
Write-Step "Fast CPU model: $cpuModel."

& $ollamaPath pull $smartModel
& $ollamaPath pull $cpuModel

Set-DotEnvValue -Name "OLLAMA_MODEL" -Value $smartModel
Set-DotEnvValue -Name "OLLAMA_FAST_MODEL" -Value $cpuModel
Set-DotEnvValue -Name "OLLAMA_KEEP_ALIVE" -Value "45m"
Set-DotEnvValue -Name "OLLAMA_NUM_PREDICT" -Value "260"
Set-DotEnvValue -Name "OLLAMA_FAST_NUM_PREDICT" -Value "160"
Set-DotEnvValue -Name "OLLAMA_THINK" -Value "false"
Set-DotEnvValue -Name "OLLAMA_FAST_THINK" -Value "false"
Set-DotEnvValue -Name "OLLAMA_NUM_THREAD" -Value ([string]$threads)
Set-DotEnvValue -Name "OLLAMA_NUM_GPU" -Value ""
Set-DotEnvValue -Name "OLLAMA_FAST_NUM_GPU" -Value "0"

Warm-Model -Model $smartModel -Threads $threads -NumGpu $null
Warm-Model -Model $cpuModel -Threads $threads -NumGpu 0

Write-Step "Current Ollama model placement:"
& $ollamaPath ps

if (-not $NoRestart) {
    Stop-Bot
    Start-Bot
}

Write-Step "Deployment complete."
