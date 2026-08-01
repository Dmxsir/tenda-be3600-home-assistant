[CmdletBinding()]
param(
    [string] $ArchivePath,
    [string] $ChecksumPath
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$componentRoot = Join-Path $repoRoot "custom_components\tenda_be3600"
$manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $componentRoot "manifest.json") | ConvertFrom-Json
if (-not $ArchivePath) { $ArchivePath = Join-Path $repoRoot "release\tenda_be3600-$($manifest.version).zip" }
if (-not $ChecksumPath) { $ChecksumPath = "$ArchivePath.sha256" }
$ArchivePath = (Resolve-Path $ArchivePath).Path
$ChecksumPath = (Resolve-Path $ChecksumPath).Path

$expectedHash = ((Get-Content -Raw -Encoding UTF8 $ChecksumPath).Trim() -split "\s+")[0]
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash
if ($expectedHash -ne $actualHash) { throw "SHA-256 mismatch for $ArchivePath" }

$extractRoot = Join-Path ([IO.Path]::GetTempPath()) "tenda-be3600-verify-$([guid]::NewGuid())"
New-Item -ItemType Directory -Path $extractRoot | Out-Null

try {
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $extractRoot
    $rootItems = @(Get-ChildItem -Force $extractRoot)
    if ($rootItems.Count -ne 1 -or $rootItems[0].Name -ne "custom_components") {
        throw "Archive must contain only the top-level custom_components directory"
    }

    $extractedComponent = Join-Path $extractRoot "custom_components\tenda_be3600"
    if (-not (Test-Path -PathType Container $extractedComponent)) {
        throw "Archive is missing custom_components/tenda_be3600"
    }

    $sourceFiles = @{}
    Get-ChildItem -File -Recurse $componentRoot |
        Where-Object { $_.Extension -ne ".pyc" -and $_.FullName -notmatch "[\\/]__pycache__[\\/]" } |
        ForEach-Object {
            $relative = $_.FullName.Substring($componentRoot.Length).TrimStart("\", "/")
            $sourceFiles[$relative] = $_.FullName
        }

    $archiveFiles = @{}
    Get-ChildItem -File -Recurse $extractedComponent | ForEach-Object {
        $relative = $_.FullName.Substring($extractedComponent.Length).TrimStart("\", "/")
        if ($_.Extension -eq ".pyc" -or $_.FullName -match "[\\/]__pycache__[\\/]" -or $_.Extension -in ".har", ".cfg", ".log") {
            throw "Forbidden file in archive: $relative"
        }
        $archiveFiles[$relative] = $_.FullName
    }

    $missing = @($sourceFiles.Keys | Where-Object { -not $archiveFiles.ContainsKey($_) })
    $extra = @($archiveFiles.Keys | Where-Object { -not $sourceFiles.ContainsKey($_) })
    if ($missing.Count -or $extra.Count) {
        throw "Archive file set differs from the integration source (missing: $($missing -join ', '); extra: $($extra -join ', '))"
    }

    foreach ($relative in $sourceFiles.Keys) {
        $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceFiles[$relative]).Hash
        $archiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archiveFiles[$relative]).Hash
        if ($sourceHash -ne $archiveHash) { throw "Archive content differs: $relative" }
    }

    Write-Output "Release verified: $ArchivePath"
    Write-Output "SHA-256: $($actualHash.ToLowerInvariant())"
    Write-Output "Files: $($archiveFiles.Count)"
} finally {
    Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
}
