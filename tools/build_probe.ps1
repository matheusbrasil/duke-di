[CmdletBinding()]
param(
    [string] $TiRoot = $env:ZOOM_TI_CGT
)

# Builds the cycle probe (MBPROBE.ZD2) the same way build_windows.ps1 builds
# Duke DI: from a temporary copy of the StompHacks clone whose path has no
# spaces (TI lnk6x requirement), then copies the build output back.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $Root 'third_party\stomphacks'
$Duke = Join-Path $Root 'embedded\effects\duke'
$Probe = Join-Path $Root 'embedded\effects\probe'
if (-not $TiRoot) { throw 'Set ZOOM_TI_CGT to the TI CGT 8.5.0.LTS install root first.' }
if (-not (Test-Path -LiteralPath (Join-Path $TiRoot 'bin\cl6x.exe'))) { throw "cl6x.exe not found under $TiRoot" }
$ToolPython = Join-Path $Source '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ToolPython)) { throw "StompHacks interpreter missing: $ToolPython" }

$BuildBase = if ($env:ZOOM_BUILD_TMP) { $env:ZOOM_BUILD_TMP } else { 'C:\tmp' }
$TempStomp = Join-Path (Join-Path $BuildBase ("probe-build-" + [guid]::NewGuid().ToString('N'))) 'stomphacks'
& robocopy.exe $Source $TempStomp /E /XD .venv .git build /NFL /NDL /NJH /NJS
if ($LASTEXITCODE -gt 7) { throw "Could not copy build tree (robocopy exit $LASTEXITCODE)." }
$TempScripts = Join-Path $TempStomp '.venv\Scripts'
New-Item -ItemType Directory -Path $TempScripts -Force | Out-Null
Copy-Item -LiteralPath $ToolPython -Destination $TempScripts -Force
Copy-Item -LiteralPath (Join-Path $Source '.venv\pyvenv.cfg') -Destination (Join-Path $TempStomp '.venv\pyvenv.cfg') -Force
& robocopy.exe (Join-Path $Source '.venv\Lib\site-packages') (Join-Path $TempStomp '.venv\Lib\site-packages') /E /NFL /NDL /NJH /NJS
if ($LASTEXITCODE -gt 7) { throw "Could not copy build dependencies (robocopy exit $LASTEXITCODE)." }

# The probe needs Duke's 188 B of state plus 24 B of its own. StompHacks caps
# state at 192 B ("proven floor"); the MS-60B+ 1.20 firmware actually gives
# every slot a fixed 672-byte state buffer (boot setup FUN_c0231220: six
# buffers at 0x11F01400 + k*0x2A0, zeroed with size 0x2A0). Raise the cap in
# this temporary copy only; the clone and Duke's own build keep 192.
$Maker = Join-Path $TempStomp 'tools\zd2_make_effect.py'
$text = [IO.File]::ReadAllText($Maker)
if (-not $text.Contains('STATE_BYTES_MAX = 192')) { throw 'zd2_make_effect.py: STATE_BYTES_MAX line not found; review before building.' }
[IO.File]::WriteAllText($Maker, $text.Replace('STATE_BYTES_MAX = 192', 'STATE_BYTES_MAX = 672'))

# Stage: the probe kernel and manifest, plus Duke's kernel, headers and tables.
$Stage = Join-Path $TempStomp 'effects\probe'
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $Probe 'probe.c'), (Join-Path $Probe 'manifest.json') -Destination $Stage -Force
foreach ($name in 'duke.c', 'approx.h', 'tables_layout.h', 'duke_fixed.h', 'tables.bin') {
    Copy-Item -LiteralPath (Join-Path $Duke $name) -Destination $Stage -Force
}

$env:ZOOM_TI_CGT = $TiRoot
Push-Location $TempStomp
try {
    & $ToolPython tools\zd2_make_effect.py effects\probe\manifest.json
    if ($LASTEXITCODE -ne 0) { throw "Probe build failed with exit code $LASTEXITCODE. Temporary tree retained: $TempStomp" }
}
finally { Pop-Location }

$Output = Join-Path $Source 'effects\probe\build'
New-Item -ItemType Directory -Path $Output -Force | Out-Null
Copy-Item -Path (Join-Path $Stage 'build\*') -Destination $Output -Recurse -Force
Write-Host "Probe build artifacts copied -> $Output"
