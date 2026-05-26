$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtime = Join-Path $root ".runtime"
$bin = Join-Path $runtime "bin"
$downloads = Join-Path $runtime "downloads"
$extractRoot = Join-Path $runtime "ffmpeg-extract"
$zipPath = Join-Path $downloads "ffmpeg-release-essentials.zip"
$downloadUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

function Write-Step {
    param([string]$Message)
    Write-Host "[ffmpeg] $Message"
}

function Add-RuntimeBinToPath {
    if ((Test-Path -LiteralPath $bin) -and -not ($env:PATH.Split([IO.Path]::PathSeparator) -contains $bin)) {
        $env:PATH = $bin + [IO.Path]::PathSeparator + $env:PATH
    }
}

function Test-Tool {
    param([string]$Name)

    Add-RuntimeBinToPath
    if (Get-Command $Name -ErrorAction SilentlyContinue) {
        return $true
    }

    $extension = if ($IsWindows -or $env:OS -eq "Windows_NT") { ".exe" } else { "" }
    return Test-Path -LiteralPath (Join-Path $bin "$Name$extension")
}

function Assert-ChildPath {
    param(
        [string]$Parent,
        [string]$Child
    )

    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $childFull = [IO.Path]::GetFullPath($Child)
    $prefix = $parentFull + [IO.Path]::DirectorySeparatorChar

    if (-not $childFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove path outside runtime folder: $childFull"
    }
}

New-Item -ItemType Directory -Path $bin, $downloads -Force | Out-Null
Add-RuntimeBinToPath

if ((Test-Tool "ffmpeg") -and (Test-Tool "ffprobe")) {
    Write-Step "ffmpeg and ffprobe are already available."
    exit 0
}

Write-Step "Downloading FFmpeg essentials package."
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath -UseBasicParsing

Assert-ChildPath -Parent $runtime -Child $extractRoot
if (Test-Path -LiteralPath $extractRoot) {
    Remove-Item -LiteralPath $extractRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $extractRoot | Out-Null

Write-Step "Extracting FFmpeg tools."
Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force

$ffmpeg = Get-ChildItem -Path $extractRoot -Recurse -Filter "ffmpeg.exe" |
    Where-Object { $_.FullName -like "*\bin\ffmpeg.exe" } |
    Select-Object -First 1
$ffprobe = Get-ChildItem -Path $extractRoot -Recurse -Filter "ffprobe.exe" |
    Where-Object { $_.FullName -like "*\bin\ffprobe.exe" } |
    Select-Object -First 1

if (-not $ffmpeg -or -not $ffprobe) {
    throw "Could not find ffmpeg.exe and ffprobe.exe in the downloaded package."
}

Copy-Item -LiteralPath $ffmpeg.FullName -Destination (Join-Path $bin "ffmpeg.exe") -Force
Copy-Item -LiteralPath $ffprobe.FullName -Destination (Join-Path $bin "ffprobe.exe") -Force

Write-Step "Installed ffmpeg and ffprobe to $bin."
