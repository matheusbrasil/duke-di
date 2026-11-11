#!/usr/bin/env bash
# stage_build.sh - stage the Duke DI effect into the stomphacks clone and make
# the build reproducible after a fresh clone.
#
# The stomphacks clone is a gitignored vendored upstream: `git pull` or a
# re-clone wipes any local edits, including the author ledger. This script:
#   1. copies the effect sources + baked const_blob into effects/duke/
#   2. merges ids/effect-authors.local.json (OUR tracked file) into the
#      clone's ids/effect-authors.json, so the build tool can resolve our
#      registered nickname->prefix (matheusbrasil -> MB).
#
# After staging, build with:
#   export ZOOM_TI_CGT=/path/to/ti-cgt-c6000_8.5.0.LTS
#   cd third_party/stomphacks
#   python3 tools/zd2_make_effect.py effects/duke/manifest.json
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/.." && pwd)"
eff="$root/embedded/effects/duke"
clone="$root/third_party/stomphacks"
ledger_local="$root/ids/effect-authors.local.json"

if [ ! -d "$clone" ]; then
  echo "stomphacks clone missing: $clone"
  echo "clone it first:  git clone https://github.com/thammer/stomphacks third_party/stomphacks"
  exit 1
fi

# 1. stage the effect
mkdir -p "$clone/effects/duke"
cp "$eff/manifest.json" "$eff/duke.c" "$eff/approx.h" \
   "$eff/tables_layout.h" "$eff/duke_fixed.h" "$eff/tables.bin" \
   "$clone/effects/duke/"
echo "staged effect sources -> $clone/effects/duke/"

# 2. merge our author entry into the clone's ledger
python3 - "$ledger_local" "$clone/ids/effect-authors.json" <<'PY'
import json, sys
local_path, ledger_path = sys.argv[1], sys.argv[2]
local = json.load(open(local_path))
try:
    ledger = json.load(open(ledger_path))
except Exception:
    ledger = {"authors": []}
authors = ledger.setdefault("authors", [])
by_nick = {a.get("nickname", "").lower(): i for i, a in enumerate(authors)}
for a in local.get("authors", []):
    nick = a.get("nickname", "").lower()
    entry = {k: a[k] for k in ("nickname", "name", "low16", "prefix", "status")
             if k in a}
    if nick in by_nick:
        authors[by_nick[nick]].update(entry)
    else:
        authors.append(entry)
json.dump(ledger, open(ledger_path, "w"), indent=1)
print(f"merged author '{local['authors'][0]['nickname']}' "
      f"(prefix {local['authors'][0]['prefix']}) into {ledger_path}")
PY

echo "done. now run zd2_make_effect.py (see header)."
