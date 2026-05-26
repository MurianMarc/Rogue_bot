param(
    [string]$HostAddress = "",
    [switch]$AllowTailscaleFirewall,
    [switch]$Persist
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[laptop-ai] $Message"
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

function Test-OllamaApi {
    param([string]$Url)

    try {
        Invoke-RestMethod -Uri "$Url/api/tags" -Method Get -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-TailscaleIp {
    $tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
    if (-not $tailscale) {
        return ""
    }

    try {
        return ((& tailscale ip -4) | Select-Object -First 1).Trim()
    } catch {
        return ""
    }
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$ollamaPath = Get-OllamaPath
$tailscaleIp = Get-TailscaleIp

if (-not $HostAddress) {
    if ($tailscaleIp) {
        $HostAddress = "$tailscaleIp`:11434"
    } else {
        $HostAddress = "0.0.0.0:11434"
    }
}

$testUrl = if ($HostAddress.StartsWith("0.0.0.0")) {
    "http://127.0.0.1:11434"
} else {
    "http://$HostAddress"
}

if ($Persist) {
    Write-Step "Saving OLLAMA_HOST=$HostAddress for future Ollama launches."
    setx OLLAMA_HOST $HostAddress | Out-Null
}

if ($AllowTailscaleFirewall) {
    if (Test-IsAdmin) {
        $rule = Get-NetFirewallRule -DisplayName "Rogue Bot Ollama Tailscale" -ErrorAction SilentlyContinue
        if (-not $rule) {
            Write-Step "Adding Windows Firewall rule for Tailscale clients on port 11434."
            New-NetFirewallRule `
                -DisplayName "Rogue Bot Ollama Tailscale" `
                -Direction Inbound `
                -Action Allow `
                -Protocol TCP `
                -LocalPort 11434 `
                -RemoteAddress "100.64.0.0/10" | Out-Null
        }
    } else {
        Write-Step "Run as Administrator to add the Tailscale-only firewall rule automatically."
    }
}

Write-Step "Stopping any existing Ollama server."
Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

$env:OLLAMA_HOST = $HostAddress
Write-Step "Starting Ollama with OLLAMA_HOST=$HostAddress."
Start-Process -FilePath $ollamaPath -ArgumentList "serve" -WindowStyle Hidden

for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    if (Test-OllamaApi -Url $testUrl) {
        break
    }
}

if (-not (Test-OllamaApi -Url $testUrl)) {
    throw "Ollama did not become ready at $testUrl."
}

Write-Step "Ollama is ready locally."
if ($tailscaleIp) {
    Write-Step "Use this on the VPS: OLLAMA_URL=http://$tailscaleIp`:11434"
} else {
    Write-Step "Tailscale IP not detected. Install/login to Tailscale, then run: tailscale ip -4"
}
