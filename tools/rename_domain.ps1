# One-off helper: rename the production domain across the repository.
#
# Byte-safe: every file is decoded/encoded as UTF-8 without touching the BOM or
# the line endings, so the diff stays limited to the replaced substring.
#
# Only files tracked by Git are processed, and binary files are detected and
# skipped, so build output, local databases, logs and secrets are never
# rewritten. NOTE: the `param` block must be the first statement in a
# PowerShell script - a docstring above it is a parse error.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\rename_domain.ps1 `
#       -Old <current-domain> -New <new-domain>
#
# Example (the 2026-09 migration to the current production domain):
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\rename_domain.ps1 `
#       -Old <previous-domain> -New classroomhelp.pp.ua

param(
    [Parameter(Mandatory = $true)][string]$Old,
    [Parameter(Mandatory = $true)][string]$New
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot) | Out-Null

if (-not $Old -or -not $New) {
    throw 'Both -Old and -New must be non-empty.'
}

# Binary extensions: never decode/re-encode these.
$binaryExt = '^\.(pyc|ico|png|jpg|jpeg|gif|svg|webp|woff|woff2|eot|ttf|otf|sqlite|db|sqlite3|exe|dll|pdb|so|dylib|zip|whl|jar|7z|gz|tar|pdf|mp3|mp4|bin|dat|pkl|npy|mo|woff2|lnk)$'

# Build output, caches and dependency trees are regenerated, never edited.
$skipDirs = '\\(\.git|\.ruff_cache|\.pytest_cache|\.mypy_cache|build|release|\.venv|node_modules|__pycache__|\.agents|data|loadtest|dist)\\'

# `git ls-files -z` is NUL-separated and never applies core.quotePath, so
# non-ASCII filenames (e.g. the em-dash ones under docs/prompt) come through
# verbatim instead of as a quoted, escaped string.
$tracked = @((git ls-files -z) -split "`0" | Where-Object { $_ })
if ($LASTEXITCODE -ne 0 -or $tracked.Count -eq 0) {
    throw 'git ls-files failed - run this from inside the repository.'
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$total = 0
$changed = 0

foreach ($relative in $tracked) {
    if ($relative -match $skipDirs) { continue }
    if ($relative -match $binaryExt) { continue }

    $path = Join-Path $PWD $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }

    $bytes = [System.IO.File]::ReadAllBytes($path)

    # Skip binaries that slipped through the extension list: valid UTF-8 never
    # contains a NUL byte, and neither does any file we care about.
    if ($bytes -contains 0) {
        Write-Host ("skip (binary)  {0}" -f $relative)
        continue
    }

    $text = $utf8.GetString($bytes)
    if (-not $text.Contains($Old)) { continue }

    $count = ([regex]::Matches($text, [regex]::Escape($Old))).Count
    [System.IO.File]::WriteAllBytes($path, $utf8.GetBytes($text.Replace($Old, $New)))
    $total += $count
    $changed++
    Write-Host ("{0,3}  {1}" -f $count, $relative)
}

Write-Host ""
Write-Host "Replaced $total occurrence(s) in $changed file(s): '$Old' -> '$New'."
