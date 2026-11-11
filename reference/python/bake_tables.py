"""bake_tables.py - generate the Duke DI const-blob the embedded kernel reads.

Mirrors embedded/effects/duke/tables_layout.h EXACTLY. The embedded C674x
kernel cannot divide or call libm, so every knob-dependent nonlinear function
is sampled here (on the desktop, where exp/log/division are free) and written
as a flat float32 blob the kernel interpolates.

Writes: embedded/effects/duke/tables.bin  (little-endian float32 words)

Layout (must match tables_layout.h):
  [OFF_WS  .. +WS_N)                 12AU7 quiescent waveshaper over [-8, +8]
  [OFF_DRV .. +DRV_N)               GAIN -> drive taper
  [OFF_EQ  .. +EQ_N*EQ_N*7)         FMV tone stack {b0..b3,a1..a3} 2-D grid
  [OFF_LC  .. +LC_N*3)              ROLLOFF low-cut {b0,b1,a1} vs treble
"""
from __future__ import annotations
import struct
import os
import numpy as np
import duke_ref as d
import tonestack as ts

# ---- mirror of tables_layout.h (keep in sync) -----------------------------
WS_N, WS_RANGE = 513, 8.0
DRV_N = 33
EQ_N = 9
EQ_STRIDE = 7
LC_N = 17
OFF_WS = 0
OFF_DRV = OFF_WS + WS_N
OFF_EQ = OFF_DRV + DRV_N
OFF_LC = OFF_EQ + EQ_N * EQ_N * EQ_STRIDE
TOTAL = OFF_LC + LC_N * 3

# Tier B runs at base rate (no oversampling). Coeffs are baked at FS.
FS = d.FS


def waveshaper_table():
    st = d.stage()
    u = np.linspace(-WS_RANGE, WS_RANGE, WS_N)
    return st.shape(u, st.vk0).astype(np.float32)


def drive_table():
    g = np.linspace(0.0, 1.0, DRV_N)
    return (d.CAL_DRIVE_MIN * (d.CAL_DRIVE_MAX / d.CAL_DRIVE_MIN) ** g).astype(np.float32)


def _eq_cell(n_treble, n_bass):
    """One grid cell: {b0,b1,b2,b3,a1,a2,a3}, makeup folded into numerator."""
    wt = ts.taper(n_treble)
    wb = ts.taper(n_bass)
    b, a = ts.design_digital(wt, wb, FS)          # length 4 each, a0=1
    b = np.asarray(b) * d.TONE_MAKEUP
    a = np.asarray(a)
    return np.concatenate([b, a[1:4]]).astype(np.float64)


def eq_grid_table():
    """3rd-order stack coeffs over an EQ_N x EQ_N (treble,bass) grid.

    Also runs the stability gate the plan requires: every grid node AND every
    bilinearly-interpolated sub-cell (what the kernel actually evaluates
    between nodes) must have all poles strictly inside the unit circle."""
    grid = np.zeros((EQ_N, EQ_N, EQ_STRIDE))
    for ti in range(EQ_N):
        for bj in range(EQ_N):
            grid[ti, bj] = _eq_cell(ti / (EQ_N - 1), bj / (EQ_N - 1))
    _assert_eq_stable(grid)
    return grid.reshape(-1).astype(np.float32)


def _poles_radius(coeffs7):
    a = np.concatenate([[1.0], coeffs7[4:7]])
    return float(np.max(np.abs(np.roots(a))))


def _assert_eq_stable(grid):
    worst = 0.0
    # grid nodes
    for ti in range(EQ_N):
        for bj in range(EQ_N):
            worst = max(worst, _poles_radius(grid[ti, bj]))
    # interpolated sub-cells (bilinear of the 4 surrounding nodes), which is
    # exactly what lut2 in the kernel produces at intermediate knob settings
    subs = np.linspace(0.0, 1.0, 5)
    for ti in range(EQ_N - 1):
        for bj in range(EQ_N - 1):
            c00, c01 = grid[ti, bj], grid[ti, bj + 1]
            c10, c11 = grid[ti + 1, bj], grid[ti + 1, bj + 1]
            for ft in subs:
                for fb in subs:
                    c = ((1 - ft) * ((1 - fb) * c00 + fb * c01)
                         + ft * ((1 - fb) * c10 + fb * c11))
                    worst = max(worst, _poles_radius(c))
    assert worst < 0.9999, f"EQ grid interpolation unstable: max pole r={worst}"
    print(f"  EQ grid stability gate: max pole radius {worst:.5f} (< 1 OK)")


def lowcut_table():
    """ROLLOFF high-pass {b0,b1,a1} vs TREBLE. Corner fc = 1/(2pi(Zout+R18)C8),
    Zout = TREBLE wiper output impedance (bass fixed at noon for the Zout est;
    the dependence is treble-dominated)."""
    rows = []
    wb = ts.taper(0.5)
    for i in range(LC_N):
        wt = ts.taper(i / (LC_N - 1))
        rs = ts.zout_T(wt, wb)
        fc = 1.0 / (2.0 * np.pi * (rs + d.LOWCUT_R18) * d.LOWCUT_C8)
        b, a = d.bilinear_hpf(fc, FS)
        rows += [b[0] / a[0], b[1] / a[0], a[1] / a[0]]
    return np.array(rows, dtype=np.float32)


def _tdf2_hpf(fc):
    b, a = d.bilinear_hpf(fc, FS)
    return b[0], b[1], a[1]


def _tdf2_lpf(fc):
    b, a = d.transformer.__globals__["signal"].bilinear(
        [2 * np.pi * fc], [1.0, 2 * np.pi * fc], FS)
    return b[0] / a[0], b[1] / a[0], a[1] / a[0]


def write_fixed_header():
    """Emit duke_fixed.h: knob-independent first-order section coefficients,
    computed here (division allowed) and shipped as float LITERALS so the
    kernel never divides, not even to constant-fold."""
    secs = {
        "DC1":    _tdf2_hpf(9.5),      # C7 node
        "DC2":    _tdf2_hpf(3.18),     # C9 coupling
        "CFHP":   _tdf2_hpf(33.9),     # White CF lower-tube rolloff
        "OUTHP":  _tdf2_hpf(4.02),     # C12 output
        "XFHP":   _tdf2_hpf(60.0),     # transformer LF/HF split
        "XFLP":   _tdf2_lpf(18000.0),  # transformer HF leakage rolloff
    }
    here = os.path.dirname(__file__)
    out = os.path.normpath(os.path.join(
        here, "..", "..", "embedded", "effects", "duke", "duke_fixed.h"))
    lines = [
        "/* duke_fixed.h - GENERATED by reference/python/bake_tables.py.",
        " * Knob-independent first-order section coefficients (TDF2:",
        " *   y = b0*x + z ;  z = b1*x - a1*y).  Float literals: no runtime",
        " *   divide, nothing to constant-fold.  Do not edit by hand. */",
        "#ifndef DUKE_FIXED_H",
        "#define DUKE_FIXED_H",
        "",
    ]
    for name, (b0, b1, a1) in secs.items():
        lines.append(f"#define {name}_B0 {b0:.9e}f")
        lines.append(f"#define {name}_B1 {b1:.9e}f")
        lines.append(f"#define {name}_A1 {a1:.9e}f")
        lines.append("")
    # shared-cathode sag envelope one-pole LP coefficient.
    # V1A+V1B share R24 1k5 bypassed by C13 1u || C14 220u = 221uF
    #   -> fc = 1/(2*pi*1k5*221u) = 0.48 Hz.
    sag_a = float(np.exp(-2.0 * np.pi * d.SAG_FC / FS))
    lines.append(f"#define SAG_A {sag_a:.9e}f   /* one-pole: y += (1-a)*(|x|-y) */")
    lines.append("")
    lines += ["#endif /* DUKE_FIXED_H */", ""]
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {out}: {len(secs)} fixed sections")


def main():
    write_fixed_header()
    ws = waveshaper_table()
    drv = drive_table()
    eq = eq_grid_table()
    lc = lowcut_table()

    blob = np.concatenate([ws, drv, eq, lc]).astype(np.float32)
    assert len(blob) == TOTAL, (len(blob), TOTAL)

    here = os.path.dirname(__file__)
    out = os.path.join(here, "..", "..", "embedded", "effects", "duke",
                       "tables.bin")
    out = os.path.normpath(out)
    with open(out, "wb") as f:
        f.write(struct.pack(f"<{TOTAL}f", *blob.tolist()))
    print(f"wrote {out}: {TOTAL} words ({TOTAL * 4} bytes)")

    # Host-validation twin of the const_blob: the real .ZD2 build injects
    # tables.bin via the manifest const_blob, but the gcc host harness
    # (validation/) links this C definition of the same symbol instead.
    words = struct.unpack(f"<{TOTAL}I", struct.pack(f"<{TOTAL}f", *blob.tolist()))
    cout = os.path.join(here, "..", "..", "embedded", "effects", "duke",
                        "tables_data.c")
    cout = os.path.normpath(cout)
    with open(cout, "w") as f:
        f.write("/* generated by bake_tables.py; host-harness twin of the\n"
                " * const_blob. NOT compiled into the .ZD2 (the firmware\n"
                " * injects tables.bin via the manifest const_blob). */\n")
        f.write(f"const unsigned int duke_tables[{TOTAL}] = {{\n")
        for j in range(0, TOTAL, 6):
            row = ", ".join(f"0x{w:08x}u" for w in words[j:j + 6])
            f.write("  " + row + ",\n")
        f.write("};\n")
    print(f"wrote {cout}")
    print(f"  WS[{WS_N}]  DRV[{DRV_N}]  EQ[{EQ_N}x{EQ_N}x{EQ_STRIDE}]  LC[{LC_N}x3]"
          f"  total {TOTAL} words")
    print(f"  waveshaper range +/-{WS_RANGE}, "
          f"endpoints {ws[0]:.3f}..{ws[-1]:.3f}")
    print(f"  drive span {drv[0]:.3f}..{drv[-1]:.3f}")


if __name__ == "__main__":
    main()
