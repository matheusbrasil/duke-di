#!/usr/bin/env python3
"""check_env.py - verify the Duke DI build/validation toolchain.

Reports what is present and what each missing piece blocks. Exit code is the
number of *hard* blockers for the in-scope work (desktop prototype + kernel
source + dry validation). The TI C6000 compiler is reported separately: it is
required only for the final on-target .ZD2 blob, which is out of this scope's
executable reach and documented as a handover step.
"""
from __future__ import annotations
import importlib
import os
import shutil
import sys

GREEN, RED, YEL, DIM, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def have_mod(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def main() -> int:
    print("Duke DI toolchain check\n" + "=" * 40)

    # (label, present, blocks, hard)
    rows = []

    # Desktop / validation
    rows.append(("python3", True, "everything", True))
    for m in ("numpy", "scipy", "matplotlib"):
        rows.append((f"py:{m}", have_mod(m), "Tier A reference + validation math", True))
    rows.append(("g++", shutil.which("g++") is not None,
                 "host harness (gcc-compiled kernel A/B test)", True))
    rows.append(("cmake", shutil.which("cmake") is not None
                 or have_mod("cmake"),
                 "optional C++ Tier A build", False))

    # ZD2 tooling (runs without the compiler, up to the compile step)
    sh = os.environ.get("STOMPHACKS",
                        os.path.join(os.path.dirname(__file__), "..",
                                     "third_party", "stomphacks"))
    rows.append(("stomphacks checkout", os.path.isdir(sh),
                 "manifest validation, container pack, roundtrip, mock pedal", True))
    rows.append(("zoom-zt2 checkout", os.path.isdir(os.path.join(sh, "zoom-zt2")),
                 "ZD2/ZIC container assembly", True))
    for m in ("construct", "crcmod", "elftools", "PIL", "mido"):
        rows.append((f"py:{m}", have_mod(m),
                     "stomphacks build/pack tooling", True))

    # SPICE reference (netlists are shipped as artifacts regardless)
    ng = shutil.which("ngspice") is not None
    rows.append(("ngspice", ng,
                 "running the SPICE netlists locally (artifacts ship either way)",
                 False))

    # Out-of-scope-to-run: the final on-target blob
    ti = os.environ.get("ZOOM_TI_CGT",
                        "/Applications/ti/ti-cgt-c6000_8.5.0.LTS")
    cl6x = os.path.isfile(os.path.join(ti, "bin", "cl6x"))
    rows.append(("TI C6000 cl6x", cl6x,
                 "compiling the final .ZD2 blob (HANDOVER step, see docs/04)",
                 False))

    hard_fail = 0
    for label, ok, blocks, hard in rows:
        mark = f"{GREEN}OK {OFF}" if ok else (f"{RED}MISS{OFF}" if hard
                                              else f"{YEL}MISS{OFF}")
        tag = "" if ok else f"  {DIM}-> blocks: {blocks}{OFF}"
        print(f"  [{mark}] {label}{tag}")
        if hard and not ok:
            hard_fail += 1

    print("=" * 40)
    if hard_fail == 0:
        print(f"{GREEN}In-scope toolchain complete.{OFF} "
              "Tier A, kernel source, dry validation all runnable.")
    else:
        print(f"{RED}{hard_fail} hard blocker(s).{OFF} "
              "Install the missing pieces above.")
    if not cl6x:
        print(f"{DIM}Note: TI cl6x absent -> the final .ZD2 blob is a documented "
              f"handover step, not produced here. See docs/04-zd2-port.md.{OFF}")
    return hard_fail


if __name__ == "__main__":
    sys.exit(main())
