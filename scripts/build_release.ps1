[CmdletBinding()]
param(
    [string] $OutputDirectory = "release"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$componentRoot = Join-Path $repoRoot "custom_components\tenda_be3600"
$manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $componentRoot "manifest.json") | ConvertFrom-Json
$outputRoot = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
}
$archiveName = "tenda_be3600-$($manifest.version).zip"
$archivePath = Join-Path $outputRoot $archiveName
$checksumPath = "$archivePath.sha256"
$stagingRoot = Join-Path ([IO.Path]::GetTempPath()) "tenda-be3600-$([guid]::NewGuid())"
$stagingComponent = Join-Path $stagingRoot "custom_components\tenda_be3600"

New-Item -ItemType Directory -Force -Path $outputRoot, $stagingComponent | Out-Null

try {
    Get-ChildItem -File -Recurse $componentRoot |
        Where-Object { $_.Extension -ne ".pyc" -and $_.FullName -notmatch "[\\/]__pycache__[\\/]" } |
        ForEach-Object {
            $relative = $_.FullName.Substring($componentRoot.Length).TrimStart("\", "/")
            $destination = Join-Path $stagingComponent $relative
            New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $destination
        }

    Remove-Item -LiteralPath $archivePath, $checksumPath -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $stagingRoot "custom_components") -DestinationPath $archivePath -CompressionLevel Optimal
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText($checksumPath, "$hash  $archiveName`n", [Text.UTF8Encoding]::new($false))

    Write-Output "Archive: $archivePath"
    Write-Output "SHA-256: $hash"
} finally {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
}
