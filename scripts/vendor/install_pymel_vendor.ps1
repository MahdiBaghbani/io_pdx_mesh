$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path
$configFile = Join-Path $scriptDir "vendor.env"
$vendorRoot = Join-Path $repoRoot "vendor"
$installRoot = Join-Path $vendorRoot "pymel_root"
$backupRoot = "$installRoot.tmp"
$wheelPath = Join-Path $vendorRoot "pymel-wheel-download.tmp"
$restoreBackup = $false
$createdInstallRoot = $false

if (-not (Test-Path -LiteralPath $configFile)) {
    throw "Missing config file: $configFile"
}

function Get-VendorConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $fileValues = @{}
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }

        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) {
            continue
        }

        $fileValues[$parts[0].Trim()] = $parts[1].Trim()
    }

    $resolvedValues = @{}
    foreach ($key in @("PYMEL_OWNER", "PYMEL_REPO", "PYMEL_VERSION")) {
        $envValue = [Environment]::GetEnvironmentVariable($key)
        $value = if (-not [string]::IsNullOrWhiteSpace($envValue)) {
            $envValue.Trim()
        }
        elseif ($fileValues.ContainsKey($key)) {
            $fileValues[$key].Trim()
        }
        else {
            ""
        }

        if ([string]::IsNullOrWhiteSpace($value)) {
            throw "Missing required value in environment or vendor.env: $key"
        }

        $resolvedValues[$key] = $value
    }

    return $resolvedValues
}

$config = Get-VendorConfig -Path $configFile
$wheelName = "pymel-$($config.PYMEL_VERSION)-py3-none-any.whl"
$downloadUrl = "https://github.com/$($config.PYMEL_OWNER)/$($config.PYMEL_REPO)/releases/download/$($config.PYMEL_VERSION)/$wheelName"

if (Test-Path -LiteralPath $backupRoot) {
    throw "Backup directory already exists: $backupRoot`nRemove or rename it, then retry."
}

New-Item -ItemType Directory -Force -Path $vendorRoot | Out-Null

try {
    if (Test-Path -LiteralPath $installRoot) {
        Move-Item -LiteralPath $installRoot -Destination $backupRoot
        $restoreBackup = $true
    }

    New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
    $createdInstallRoot = $true
    Invoke-WebRequest -Uri $downloadUrl -OutFile $wheelPath

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($wheelPath, $installRoot)

    if (-not (Test-Path -LiteralPath (Join-Path $installRoot "pymel"))) {
        throw "Install failed: extracted wheel did not contain a pymel package."
    }

    if ($restoreBackup -and (Test-Path -LiteralPath $backupRoot)) {
        Remove-Item -LiteralPath $backupRoot -Recurse -Force
        $restoreBackup = $false
    }
}
catch {
    Write-Error "Install failed. Cleaning partial vendor directory."

    if ($createdInstallRoot -and (Test-Path -LiteralPath $installRoot)) {
        Remove-Item -LiteralPath $installRoot -Recurse -Force
    }

    if ($restoreBackup -and (Test-Path -LiteralPath $backupRoot)) {
        Move-Item -LiteralPath $backupRoot -Destination $installRoot
        Write-Error "Restored previous vendor directory."
    }

    throw
}
finally {
    if (Test-Path -LiteralPath $wheelPath) {
        Remove-Item -LiteralPath $wheelPath -Force
    }
}

Write-Host "Vendored PyMEL installed to $installRoot"
