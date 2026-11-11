#!/usr/bin/env python3
"""audit_text_dis.py - SAFE-DSP audit of the compiled kernel's disassembly.

WHY THIS EXISTS
---------------
`validation/check_safe_dsp.py` proves the kernel's *C source* has no divide,
libm call, allocation or non-const static. That is a source-level gate. The
final proof is the *generated* C674x code, which only exists after TI `cl6x`
runs inside `tools/zd2_make_effect.py`.

For effects whose kernel lives in the `.audio` section, that tool already
asserts the SAFE-DSP no-stack rule (`assert "B15" not in body`). Duke DI uses
`"kernel_section": "text"` (the kernel exceeds the 1472-byte `.audio` cap), and
that branch only *dumps* `build/MBDUKE.text.dis` for review - it does NOT run
the B15/stack assertion. So for us the asm-level audit is otherwise a manual
eyeball step. This script makes it a gate.

WHAT IT CHECKS (inside the kernel function Fx_SFX_<sym> only)
------------------------------------------------------------
  - B15 (the stack pointer): any use means a stack frame -> NOT SAFE-DSP.
  - __c6xabi_* helper symbols (push_rts/pop_rts, divide/remainder, etc.):
    a call into the RTS -> a frame and/or a runtime call -> NOT SAFE-DSP.
  - explicit division/remainder helpers (__c6xdiv*, __c6xremi*, __divf, ...).
  - CALL/CALLP to anything other than the effect's own generated symbols.

It reads the ALREADY-DUMPED `*.text.dis` (or `*.audio.dis`) that the build
writes - it does not need `cl6x` itself. Run it straight after the build:

    python3 tools/audit_text_dis.py \
        third_party/stomphacks/effects/duke/build/MBDUKE.text.dis --sym DukeDI

Exit 0 = clean. Non-zero = the count of violations (details printed).

A `--selftest` mode runs built-in good/bad fixtures so the auditor itself is
verifiable on a host with no TI toolchain and no build output yet.
"""
from __future__ import annotations
import argparse
import re
import sys


# Lines dis6x/norm emit are like:  "MVK.L1 2,A0"  or  "Fx_SFX_DukeDI:" (label)
# or a parallel instruction "|| ADD.D1 A3,A4,A5". Labels end in ':' and are a
# bare symbol; instructions carry a unit mnemonic ".Lx/.Dx/.Sx/.Mx".
_LABEL_RE = re.compile(r"^(?:\|\|\s*)?([A-Za-z_$][\w$]*)\s*:\s*$")

# B15 as a register operand (word boundary so A15/B151 etc. do not match; B15
# appears as *B15, B15, SP alias). dis6x prints the stack reg as B15.
_B15_RE = re.compile(r"\bB15\b")

# RTS / runtime helpers the compiler emits for frames and for ops the C674x has
# no instruction for (integer/float divide, remainder, long shifts, etc).
_RTS_RE = re.compile(r"__c6xabi_\w+")
_DIVREM_RE = re.compile(r"__\w*(?:div|rem|fixdfdi|floatdisf)\w*", re.IGNORECASE)

# A call instruction and its target symbol (CALL/CALLP, optionally parallel).
_CALL_RE = re.compile(r"^(?:\|\|\s*)?CALLP?\.\S+\s+(\S+)")


def scope_lines(lines, sym):
    """Return (scoped_lines, label) for the kernel function Fx_SFX_<sym>, or
    the whole file if the symbol is absent (whole-blob audit)."""
    if sym is None:
        return list(lines), "<whole file>"
    want = f"Fx_SFX_{sym}"
    start = None
    for i, l in enumerate(lines):
        m = _LABEL_RE.match(l.strip())
        if m and m.group(1) == want:
            start = i + 1
            break
    if start is None:
        return None, want
    end = len(lines)
    for i in range(start, len(lines)):
        m = _LABEL_RE.match(lines[i].strip())
        if m and m.group(1) != want:
            end = i
            break
    return lines[start:end], want


def audit(lines, sym=None):
    """Return a list of (lineno, kind, text) violations within scope."""
    scoped, label = scope_lines(lines, sym)
    if scoped is None:
        return [(-1, "scope", f"kernel symbol {label} not found in listing")]
    viol = []
    # the effect's own generated symbols are legitimate call targets
    own = {f"Fx_SFX_{sym}", f"Dll_{sym}", "__call_stub"} if sym else set()
    for off, raw in enumerate(scoped):
        l = raw.strip()
        if not l or _LABEL_RE.match(l):
            continue
        if _B15_RE.search(l):
            viol.append((off, "stack", l))
        for m in _RTS_RE.finditer(l):
            viol.append((off, "rts-helper", l))
            break
        if _DIVREM_RE.search(l):
            viol.append((off, "divide", l))
        cm = _CALL_RE.match(l)
        if cm:
            target = cm.group(1).split(",")[0]
            tsym = target.lstrip("#").split("(")[0]
            if (tsym not in own
                    and not tsym.startswith(("Fx_SFX_", "Aw_P", "Dll_"))
                    and tsym not in ("B3", "B31")):   # register-indirect return
                viol.append((off, "call", l))
    return viol


def run_file(path, sym):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError as e:
        print(f"audit_text_dis: cannot read {path}: {e}", file=sys.stderr)
        return 2
    viol = audit(lines, sym)
    scope = f"Fx_SFX_{sym}" if sym else "whole listing"
    if not viol:
        print(f"SAFE-DSP asm audit OK: {path} ({scope}) - "
              "no stack (B15), no RTS helper, no divide, no foreign call.")
        return 0
    print(f"SAFE-DSP asm audit FAILED: {path} ({scope})")
    for off, kind, text in viol:
        where = "?" if off < 0 else f"+{off}"
        print(f"  [{kind}] {where}: {text}")
    print(f"{len(viol)} violation(s). A text-placed kernel that trips these is "
          "NOT real-time safe; see docs/05-build-and-flash.md "
          "(try \"opt_level\": 1).")
    return len(viol)


_GOOD_FIXTURE = """\
Fx_SFX_DukeDI:
           MVK.L1 2,A0
|| LDW.D1T1 *+A4[1],A1
           MPYSP.M1 A1,A2,A3
           ADDSP.L1 A3,A5,A5
           STW.D1T1 A5,*+A4[0]
           BNOP.S2 B3,5
Fx_SFX_DukeDI_init:
           MVK.S2 0x00ac,B4
"""

_BAD_FIXTURE = """\
Fx_SFX_DukeDI:
           ADDK.S2 -264,B15
           STW.D2T2 B3,*B15
           CALLP.S2 __c6xabi_divf,B3
           CALLP.S2 somebody_elses_fn,B3
           LDW.D2T2 *++B15,B3
           BNOP.S2 B3,5
Fx_SFX_DukeDI_init:
           ADDK.S2 -264,B15
"""


def selftest():
    good = audit(_GOOD_FIXTURE.splitlines(), "DukeDI")
    bad = audit(_BAD_FIXTURE.splitlines(), "DukeDI")
    bad_kinds = sorted({k for _, k, _ in bad})
    ok = True
    if good:
        print(f"selftest FAIL: clean fixture flagged {good}"); ok = False
    else:
        print("selftest: clean fixture -> 0 violations OK")
    # the bad fixture's init B15 is out of scope; only the 4 in-function lines
    # (B15 x2, rts-helper/divide, foreign call) must be caught.
    want = {"stack", "rts-helper", "divide", "call"}
    if want <= set(bad_kinds):
        print(f"selftest: bad fixture -> caught {bad_kinds} OK")
    else:
        print(f"selftest FAIL: bad fixture missed {want - set(bad_kinds)}")
        ok = False
    # scope must stop at the next function: the init-only B15 must NOT appear
    # (3 in-function stack hits expected, not 4 counting init).
    nstack = sum(1 for _, k, _ in bad if k == "stack")
    if nstack == 3:
        print("selftest: scoping stops at next function OK")
    else:
        print(f"selftest FAIL: expected 3 in-scope stack hits, got {nstack}")
        ok = False
    print("selftest PASS" if ok else "selftest FAILED")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dis", nargs="?", help="path to *.text.dis / *.audio.dis")
    ap.add_argument("--sym", default=None,
                    help="effect sym (e.g. DukeDI); scopes to Fx_SFX_<sym>. "
                         "Omit to audit the whole listing.")
    ap.add_argument("--selftest", action="store_true",
                    help="run built-in good/bad fixtures (no file needed)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.dis:
        ap.error("give a .dis path, or --selftest")
    return run_file(a.dis, a.sym)


if __name__ == "__main__":
    sys.exit(main())
