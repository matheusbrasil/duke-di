#!/usr/bin/env python3
"""check_safe_dsp.py - source-level SAFE-DSP gate for the Duke DI kernel.

The real guarantee is "the generated C674x object divides nothing, calls
nothing, allocates nothing". That object can only be produced by TI cl6x
(docs/04-zd2-port.md), which is not installable here, so this is a *source*
lint, not an asm audit: it strips comments and string/char literals from
duke.c and approx.h, then fails on any construct that would emit a runtime
divide, a libm/helper call, or an allocation.

What it rejects:
  - the '/' division operator anywhere in live code (compile-time constant
    folds are written with the reciprocal precomputed, so none should remain)
  - libm transcendentals (tanh/exp/pow/sin/cos/log/sqrt, with f/l suffixes)
  - heap or C++ alloc (malloc/calloc/realloc/free/new/delete)
  - non-const static locals (hidden state outside instance[2])

Run from validation/.  Exit 0 = clean.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EFF = os.path.join(HERE, "..", "embedded", "effects", "duke")
FILES = ["duke.c", "approx.h"]

LIBM = (r"\b(?:tanh|sinh|cosh|exp|exp2|expm1|pow|sqrt|cbrt|sin|cos|tan|"
        r"asin|acos|atan|atan2|log|log2|log10|log1p|fmod|hypot)f?l?\b")
ALLOC = r"\b(?:malloc|calloc|realloc|free|aligned_alloc)\b|\b(?:new|delete)\b"
STATIC_LOCAL = r"\bstatic\b(?!\s+inline)(?!\s+const)"


def strip(code):
    """Remove block/line comments and string/char literals, keeping newlines."""
    out = []
    i, n = 0, len(code)
    while i < n:
        c = code[i]
        if c == "/" and i + 1 < n and code[i + 1] == "*":
            j = code.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", code[i:j]))
            i = j
        elif c == "/" and i + 1 < n and code[i + 1] == "/":
            j = code.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif c in "\"'":
            q = c
            j = i + 1
            while j < n and code[j] != q:
                j += 2 if code[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(" " * (j - i))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def main():
    problems = []
    for fn in FILES:
        path = os.path.join(EFF, fn)
        with open(path) as f:
            raw = f.read()
        code = strip(raw)
        for lineno, line in enumerate(code.splitlines(), 1):
            # division: a '/' not part of '/=' pointer math is still a divide;
            # the kernel must contain none.
            for m in re.finditer(r"/", line):
                # '/' only ever appears here as division (comments gone)
                problems.append((fn, lineno, "divide '/'", line.strip()))
                break
            if re.search(LIBM, line):
                problems.append((fn, lineno, "libm call", line.strip()))
            if re.search(ALLOC, line):
                problems.append((fn, lineno, "allocation", line.strip()))
            if re.search(STATIC_LOCAL, line):
                problems.append((fn, lineno, "static (non-const) storage",
                                 line.strip()))

    if problems:
        print(f"SAFE-DSP lint FAILED: {len(problems)} issue(s)")
        for fn, ln, kind, txt in problems:
            print(f"  {fn}:{ln}: {kind}: {txt}")
        return 1
    print(f"SAFE-DSP lint OK: {', '.join(FILES)} - no divide/libm/alloc/"
          "static in live code")
    print("NOTE: source-level only; final asm audit needs cl6x "
          "(docs/04-zd2-port.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
