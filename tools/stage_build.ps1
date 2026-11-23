[CmdletBinding()]
param(
    [string] $Python = (Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe')
)

# Native Windows staging helper.  It mirrors stage_build.sh without requiring
# a POSIX shell and creates the venv layout expected by current StompHacks.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Effect = Join-Path $Root 'embedded\effects\duke'
$Clone = Join-Path $Root 'third_party\stomphacks'
$LedgerLocal = Join-Path $Root 'ids\effect-authors.local.json'
$Venv = Join-Path $Clone '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $Python)) { throw "Python not found: $Python" }
if (-not (Test-Path -LiteralPath $Clone)) {
    throw "StompHacks clone missing: $Clone"
}

$Destination = Join-Path $Clone 'effects\duke'
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
foreach ($name in 'manifest.json', 'duke.c', 'approx.h', 'tables_layout.h', 'duke_fixed.h', 'tables.bin') {
    Copy-Item -LiteralPath (Join-Path $Effect $name) -Destination $Destination -Force
}
Write-Host "staged effect sources -> $Destination"

$mergeLedger = @'
import json, sys
local_path, ledger_path = sys.argv[1:3]
with open(local_path, encoding="utf-8") as f:
    local = json.load(f)
with open(ledger_path, encoding="utf-8") as f:
    ledger = json.load(f)
authors = ledger.setdefault("authors", [])
by_nick = {a.get("nickname", "").lower(): i for i, a in enumerate(authors)}
for item in local.get("authors", []):
    nick = item.get("nickname", "").lower()
    entry = {k: item[k] for k in ("nickname", "name", "low16", "prefix", "status") if k in item}
    if nick in by_nick:
        authors[by_nick[nick]].update(entry)
    else:
        authors.append(entry)
with open(ledger_path, "w", encoding="utf-8") as f:
    json.dump(ledger, f, indent=1)
    f.write("\n")
print(f"merged author '{local['authors'][0]['nickname']}' into {ledger_path}")
'@
& $Python -c $mergeLedger $LedgerLocal (Join-Path $Clone 'ids\effect-authors.json')
if ($LASTEXITCODE -ne 0) { throw 'Could not merge the StompHacks author ledger.' }

$requirements = Join-Path $Clone 'requirements.txt'
if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $Python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the StompHacks virtual environment.' }
}
# Do not contact PyPI merely to rebuild an already-provisioned local toolchain.
# This keeps an offline Windows build deterministic; install only if the import
# probe proves a dependency is missing.
& $VenvPython -c 'import construct, crcmod, elftools, PIL, mido'
if ($LASTEXITCODE -ne 0) {
    & $VenvPython -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'Could not install StompHacks requirements.' }
    & $VenvPython -c 'import construct, crcmod, elftools, PIL, mido'
    if ($LASTEXITCODE -ne 0) { throw 'The StompHacks virtual environment is incomplete.' }
}
Write-Host "StompHacks virtual environment ready -> $VenvPython"
