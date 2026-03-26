param(
    [Parameter(Mandatory = $true)]
    [string]$TargetStorageRoot,
    [string]$RepoRoot,
    [string]$EnvFilePath,
    [switch]$SkipNginx
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-AbsolutePath {
    param([string]$PathValue)

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        throw "Path must not be empty"
    }

    $expanded = [Environment]::ExpandEnvironmentVariables($PathValue)
    if ([System.IO.Path]::IsPathRooted($expanded)) {
        return [System.IO.Path]::GetFullPath($expanded)
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $expanded))
}

function To-EnvPath {
    param([string]$PathValue)
    return ($PathValue -replace "\\", "/")
}

function Set-EnvValue {
    param(
        [string]$EnvPath,
        [string]$Key,
        [string]$Value
    )

    $lines = @()
    if (Test-Path $EnvPath) {
        $lines = [System.Collections.Generic.List[string]]::new()
        foreach ($line in [System.IO.File]::ReadAllLines($EnvPath)) {
            [void]$lines.Add($line)
        }
    } else {
        $lines = [System.Collections.Generic.List[string]]::new()
    }

    $prefix = "$Key="
    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            $lines[$i] = "$prefix$Value"
            $updated = $true
            break
        }
    }

    if (-not $updated) {
        [void]$lines.Add("$prefix$Value")
    }

    $lastError = $null
    for ($attempt = 1; $attempt -le 12; $attempt++) {
        try {
            [System.IO.File]::WriteAllLines(
                $EnvPath,
                $lines,
                [System.Text.UTF8Encoding]::new($false)
            )
            return
        } catch {
            $lastError = $_
            Start-Sleep -Milliseconds 150
        }
    }

    throw "Failed to update $EnvPath after multiple retries: $lastError"
}

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

$RepoRoot = Resolve-AbsolutePath -PathValue $RepoRoot
$TargetStorageRoot = Resolve-AbsolutePath -PathValue $TargetStorageRoot
$EnvPath = ""
$resolvedEnvPathInput = ""
$hasEnvPathInput = -not [string]::IsNullOrWhiteSpace($EnvFilePath)
if ($hasEnvPathInput) {
    $resolvedEnvPathInput = Resolve-AbsolutePath -PathValue $EnvFilePath
    $EnvPath = $resolvedEnvPathInput
} else {
    $EnvPath = Join-Path $RepoRoot ".env"
}
$SetupNginxPath = Join-Path $RepoRoot "scripts\setup-nginx-windows.ps1"

if (-not (Test-Path $SetupNginxPath)) {
    throw "setup-nginx-windows.ps1 not found at $SetupNginxPath"
}

$defaultStorageRoot = Join-Path $RepoRoot "src\fanic\storage"
$currentStorageRoot = $defaultStorageRoot

if (Test-Path $EnvPath) {
    $existingDataDir = ""
    foreach ($line in [System.IO.File]::ReadLines($EnvPath)) {
        if ($line.StartsWith("FANIC_DATA_DIR=", [System.StringComparison]::Ordinal)) {
            $existingDataDir = $line.Substring("FANIC_DATA_DIR=".Length).Trim()
            break
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($existingDataDir)) {
        $currentStorageRoot = Resolve-AbsolutePath -PathValue $existingDataDir
    } elseif (Test-Path (Join-Path $RepoRoot "src\storage")) {
        $currentStorageRoot = Resolve-AbsolutePath -PathValue (Join-Path $RepoRoot "src\storage")
    }
}

if (-not (Test-Path $currentStorageRoot) -and (Test-Path (Join-Path $RepoRoot "src\storage"))) {
    $currentStorageRoot = Resolve-AbsolutePath -PathValue (Join-Path $RepoRoot "src\storage")
}

if (-not (Test-Path $TargetStorageRoot)) {
    New-Item -ItemType Directory -Path $TargetStorageRoot -Force | Out-Null
}

$currentResolved = Resolve-AbsolutePath -PathValue $currentStorageRoot
$targetResolved = Resolve-AbsolutePath -PathValue $TargetStorageRoot

if ($currentResolved -ne $targetResolved -and (Test-Path $currentResolved)) {
    $targetEntries = Get-ChildItem -Path $targetResolved -Force -ErrorAction SilentlyContinue
    if ($targetEntries) {
        throw "Target storage directory is not empty: $targetResolved"
    }

    Write-Host "Moving storage from $currentResolved to $targetResolved"
    $parentDir = Split-Path -Parent $targetResolved
    if (-not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }

    if (Test-Path $targetResolved) {
        Remove-Item -Path $targetResolved -Recurse -Force
    }

    Move-Item -Path $currentResolved -Destination $targetResolved
}

foreach ($subdir in @("cbz", "works", "static", "fanart")) {
    $path = Join-Path $targetResolved $subdir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

$envPathValue = To-EnvPath -PathValue $targetResolved
if ($hasEnvPathInput -and -not (Test-Path $resolvedEnvPathInput)) {
    $parentDir = Split-Path -Parent $resolvedEnvPathInput
    if ($parentDir -and -not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }
}

Set-EnvValue -EnvPath $EnvPath -Key "FANIC_DATA_DIR" -Value $envPathValue
Write-Host "Updated FANIC_DATA_DIR in .env to $envPathValue"

if (-not $SkipNginx) {
    Write-Host "Reconfiguring nginx aliases for new storage path"
    powershell -NoLogo -ExecutionPolicy Bypass -File $SetupNginxPath -RepoRoot $RepoRoot -StorageRoot $targetResolved -SkipDownload -NoPrompt
}

Write-Host "Storage relocation complete"
Write-Host "Current storage root: $targetResolved"
