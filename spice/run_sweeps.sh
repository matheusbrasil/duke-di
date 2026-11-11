#!/usr/bin/env bash
# run_sweeps.sh - produce the Duke DI SPICE reference curves.
#
# Requires ngspice (free: `apt install ngspice` / `brew install ngspice`, or a
# no-root source build - see docs/05-build-and-flash.md). LTspice users: open
# the .cir files directly, they are standard SPICE netlists, and use the
# .ac/.tran directives shown inside. Verified with ngspice-36 and ngspice-47.
#
# Outputs (consumed by validation/compare_spice.py if you wire it up):
#   validation/spice_gain_ac.txt   - gain-stage Bode (vdb, vp)
#   validation/spice_tone_ac.txt   - tone/EQ Bode (vdb)
# and prints the .four THD table for the gain stage to stdout.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

if ! command -v ngspice >/dev/null 2>&1; then
  echo "ngspice not found. Install it (apt install ngspice / brew install ngspice)"
  echo "or open spice/*.cir in LTspice. Netlists are standard SPICE."
  exit 1
fi

echo "== gain stage (Bode + THD) =="
ngspice -b gain_stage.cir

echo "== tone/EQ (Bode) =="
ngspice -b tone_eq.cir

echo "done. Curves in validation/spice_*_ac.txt"
