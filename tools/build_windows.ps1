[CmdletBinding()]
param(
    [string] $Python = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'),
    [string] $TiRoot = $env:ZOOM_TI_CGT
)

# TI lnk6x 8.5.0 does not reliably preserve a quoted path containing spaces.
# Build from a fresh temporary copy whose physical path contains no spaces,
# then copy only generated artifacts back to the working checkout. A junction
# or SUBST drive is insufficient: pathlib.resolve() restores the original
# long path before lnk6x is called.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Root 'third_party\stomphacks'
$IconSource = Join-Path $Root 'embedded\effects\duke\icon\MBDUKE.ZIC'
if (-not $TiRoot) { throw 'Set ZOOM_TI_CGT to the TI CGT 8.5.0.LTS install root first.' }
if (-not (Test-Path -LiteralPath (Join-Path $TiRoot 'bin\cl6x.exe'))) {
    throw "cl6x.exe not found under $TiRoot"
}
if (-not (Test-Path -LiteralPath $Python)) { throw "Python not found: $Python" }
if (-not (Test-Path -LiteralPath $Source)) { throw "StompHacks clone missing: $Source" }
if (-not (Test-Path -LiteralPath $IconSource)) { throw "Duke icon missing: $IconSource" }

# The App-container TEMP path can deny a child Python process permission to
# remove its own build/ directory.  Use a conventional, overrideable short
# path instead; it also avoids TI's fragile handling of spaces in paths.
$BuildBase = if ($env:ZOOM_BUILD_TMP) { $env:ZOOM_BUILD_TMP } else { 'C:\tmp' }
New-Item -ItemType Directory -Path $BuildBase -Force | Out-Null
$TempRoot = Join-Path $BuildBase ("duke-di-build-" + [guid]::NewGuid().ToString('N'))
$TempStomp = Join-Path $TempRoot 'stomphacks'
New-Item -ItemType Directory -Path $TempRoot | Out-Null
Write-Host "Copying isolated build tree -> $TempStomp"
# The tool virtual environment is large and contains no linker input. Keep it
# at its original path and run the copied source tree with that interpreter;
# this avoids a lengthy recursive copy on every offline Windows build.
& robocopy.exe $Source $TempStomp /E /XD .venv .git build /NFL /NDL /NJH /NJS
$copyExit = $LASTEXITCODE
if ($copyExit -gt 7) { throw "Could not copy isolated build tree (robocopy exit $copyExit)." }
$ToolPython = Join-Path $Source '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ToolPython)) { throw "StompHacks interpreter missing: $ToolPython" }
# The Bash packer detects a Windows venv at ROOT/.venv/Scripts/python.exe.
# Copy its launcher, metadata and lightweight tool dependencies, but not the
# full interpreter/headers, so the copied packer can import construct et al.
$TempScripts = Join-Path $TempStomp '.venv\Scripts'
New-Item -ItemType Directory -Path $TempScripts -Force | Out-Null
Copy-Item -LiteralPath $ToolPython -Destination $TempScripts -Force
Copy-Item -LiteralPath (Join-Path $Source '.venv\pyvenv.cfg') -Destination (Join-Path $TempStomp '.venv\pyvenv.cfg') -Force
$SourcePackages = Join-Path $Source '.venv\Lib\site-packages'
$TempPackages = Join-Path $TempStomp '.venv\Lib\site-packages'
& robocopy.exe $SourcePackages $TempPackages /E /NFL /NDL /NJH /NJS
$packageCopyExit = $LASTEXITCODE
if ($packageCopyExit -gt 7) { throw "Could not copy build dependencies (robocopy exit $packageCopyExit)." }

try {
    $env:ZOOM_TI_CGT = $TiRoot
    Push-Location $TempStomp
    & $ToolPython tools\zd2_make_effect.py effects\duke\manifest.json
    if ($LASTEXITCODE -ne 0) { throw "ZD2 build failed with exit code $LASTEXITCODE. Temporary tree retained: $TempRoot" }
    Pop-Location

    $Output = Join-Path $Source 'effects\duke\build'
    New-Item -ItemType Directory -Path $Output -Force | Out-Null
    Copy-Item -Path (Join-Path $TempStomp 'effects\duke\build\*') -Destination $Output -Recurse -Force
    # The upstream packer produces a generic icon from the manifest.  Keep the
    # audio container it built, but replace the external companion icon with
    # Duke DI's validated 1-bit ZIC artwork.
    Copy-Item -LiteralPath $IconSource -Destination (Join-Path $Output 'MBDUKE.ZIC') -Force
    Write-Host "Build artifacts copied -> $Output"
    Write-Host "Temporary build tree retained for inspection: $TempRoot"
}
finally {
    if ((Get-Location).Path -eq $TempStomp) { Pop-Location }
}
