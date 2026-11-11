#!/usr/bin/env python3
"""ab_test.py - A/B validation: Tier B kernel (duke.c, host-compiled) vs the
Tier A golden reference (duke_ref.py).

The two tiers are deliberately different reductions (Tier A oversamples and
shifts the cathode bias for sag; Tier B runs at base rate with compression-
multiply sag, and bakes every nonlinearity into LUTs the C674x can afford).
So this is NOT a sample-exact null test. It checks that the shipped kernel
preserves the *character* of the reference within stated engineering
tolerances, and that it is numerically safe.

Pass/fail tolerances (justification in docs/03-validation.md):
  T1 broadband gain (1 kHz, small signal)   : within 1.5 dB of Tier A
  T2 magnitude response 50 Hz..12 kHz       : within 2.0 dB of Tier A
  T3 even-order dominance (H2 > H3)          : kernel H2 at least 4 dB > H3
  T4 EQ shelf action (Bass/Treble boost)     : >= +4 dB at shelf vs flat
  T5 low-cut at 45 Hz when engaged           : <= -4 dB vs low-cut off
  T6 numerical safety                        : finite, |y| < 8 (kernel clamp)

Tolerances are loose on purpose: Tier B is a CPU-budget reduction, not a
clone of Tier A. They are tight enough to catch a broken filter, a dead
nonlinearity, a wrong EQ corner, or an unstable section. T6's bound is the
kernel's own output clamp (SAFETY.md): staying strictly inside it means no
sample was scrubbed to zero (no dropouts) and nothing diverged. Output can
exceed unity at extreme settings - that is a hot preamp clipping, expected.
"""
import os
import sys
import struct
import subprocess
import math
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reference", "python"))
import duke_ref as ref  # noqa: E402

HOST = os.path.join(HERE, "host_duke")
FS = 44100.0


def run_kernel(x, gain, bass, treble, level, lowcut, xfmr):
    raw = struct.pack(f"<{len(x)}d", *np.asarray(x, dtype=np.float64))
    args = [HOST, f"{gain}", f"{bass}", f"{treble}",
            f"{level}", f"{1 if lowcut else 0}", f"{1 if xfmr else 0}"]
    p = subprocess.run(args, input=raw, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"host_duke failed: {p.stderr.decode()}")
    return np.frombuffer(p.stdout, dtype=np.float64)


def db(x):
    return 20.0 * math.log10(max(x, 1e-12))


def mag_at(y, f, fs=FS):
    seg = y[len(y) // 4:]
    seg = seg * np.hanning(len(seg))
    Y = np.abs(np.fft.rfft(seg))
    fr = np.fft.rfftfreq(len(seg), 1.0 / fs)
    k = int(np.argmin(np.abs(fr - f)))
    return float(Y[max(0, k - 2):k + 3].max())


def sine(f, n=8192, amp=0.1):
    t = np.arange(n) / FS
    return amp * np.sin(2.0 * np.pi * f * t)


def settle(y, keep=0.5):
    return y[int(len(y) * (1.0 - keep)):]


def main():
    if not os.path.exists(HOST):
        print("ERROR: build the host harness first: bash build_host.sh")
        return 1

    results = []

    def check(name, ok, detail):
        results.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # ---- T1 broadband gain at 1 kHz, small signal -----------------------
    x = sine(1000.0, amp=0.02)
    yk = run_kernel(x, 0.5, 0.5, 0.5, 0.8, False, False)
    yr = ref.process(x, gain=0.5, bass=0.5, treble=0.5, level=0.8)
    gk = np.sqrt(np.mean(settle(yk) ** 2)) / np.sqrt(np.mean(settle(x) ** 2))
    gr = np.sqrt(np.mean(settle(yr) ** 2)) / np.sqrt(np.mean(settle(x) ** 2))
    check("T1 gain@1k", abs(db(gk) - db(gr)) <= 1.5,
          f"kernel {db(gk):+.2f} dB vs ref {db(gr):+.2f} dB "
          f"(dev {db(gk)-db(gr):+.2f})")

    # ---- T2 magnitude response 50 Hz .. 12 kHz --------------------------
    freqs = [50, 110, 250, 500, 1000, 2000, 4000, 8000, 12000]
    worst = 0.0
    worst_f = 0
    for f in freqs:
        x = sine(f, amp=0.02)
        yk = run_kernel(x, 0.5, 0.5, 0.5, 0.8, False, False)
        yr = ref.process(x, gain=0.5, bass=0.5, treble=0.5, level=0.8)
        mk = db(mag_at(yk, f))
        mr = db(mag_at(yr, f))
        d = abs(mk - mr)
        if d > worst:
            worst, worst_f = d, f
    check("T2 magresp", worst <= 2.0,
          f"worst dev {worst:.2f} dB at {worst_f} Hz")

    # ---- T3 even-order dominance ----------------------------------------
    x = sine(110.0, amp=0.25)
    yk = run_kernel(x, 0.7, 0.5, 0.5, 0.8, False, False)
    h1, h2, h3 = (mag_at(yk, 110), mag_at(yk, 220), mag_at(yk, 330))
    even_margin = db(h2) - db(h3)
    check("T3 even>odd", even_margin >= 4.0,
          f"H2 {db(h2/h1):+.1f} dBc, H3 {db(h3/h1):+.1f} dBc, "
          f"H2-H3 {even_margin:+.1f} dB")

    # ---- T4 EQ shelf action ---------------------------------------------
    xb = sine(150.0, amp=0.02)
    flat = db(mag_at(run_kernel(xb, 0.5, 0.5, 0.5, 0.8, False, False), 150))
    boost = db(mag_at(run_kernel(xb, 0.5, 1.0, 0.5, 0.8, False, False), 150))
    xt = sine(3500.0, amp=0.02)
    flatt = db(mag_at(run_kernel(xt, 0.5, 0.5, 0.5, 0.8, False, False), 3500))
    boostt = db(mag_at(run_kernel(xt, 0.5, 0.5, 1.0, 0.8, False, False), 3500))
    check("T4 bass shelf", boost - flat >= 4.0,
          f"+{boost-flat:.1f} dB at 150 Hz")
    check("T4 treble shelf", boostt - flatt >= 4.0,
          f"+{boostt-flatt:.1f} dB at 3.5 kHz")

    # ---- T5 low-cut ------------------------------------------------------
    xl = sine(45.0, amp=0.02)
    off = db(mag_at(run_kernel(xl, 0.5, 0.5, 0.5, 0.8, False, False), 45))
    on = db(mag_at(run_kernel(xl, 0.5, 0.5, 0.5, 0.8, True, False), 45))
    check("T5 lowcut@45", on - off <= -4.0,
          f"{on-off:.1f} dB at 45 Hz when engaged")

    # ---- T6 numerical safety (incl. hard drive + transformer) -----------
    x = np.concatenate([sine(110, amp=0.9), sine(2000, amp=0.9),
                        np.zeros(256)])
    safe = True
    for g in (0.0, 0.5, 1.0):
        for xf in (False, True):
            y = run_kernel(x, g, 1.0, 1.0, 1.0, True, xf)
            if not np.all(np.isfinite(y)) or np.max(np.abs(y)) >= 8.0:
                safe = False
    check("T6 safety", safe, "finite and inside the kernel clamp (|y|<8)")

    npass = sum(1 for _, ok, _ in results if ok)
    print(f"\n{npass}/{len(results)} checks passed")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
