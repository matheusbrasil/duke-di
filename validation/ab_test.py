#!/usr/bin/env python3
"""Tier-A/Tier-B regression gate for the revised Nobelium topology.

Contract: INPUT is virtual source level (50 is nominal); BASS/TREBLE are flat
at 0 and boost from there; LOCUT is the physical C8/R18 network; the model
uses only the complete 1/4-inch V2 White-follower output path.
"""
import math
import os
import struct
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reference", "python"))
import duke_ref as ref  # noqa: E402

HOST = os.path.join(HERE, "host_duke.exe" if os.name == "nt" else "host_duke")
FS = 44100.0


def run_kernel(x, input_level, bass, treble, level, lowcut):
    raw = struct.pack(f"<{len(x)}d", *np.asarray(x, dtype=np.float64))
    args = [HOST, f"{input_level}", f"{bass}", f"{treble}", f"{level}",
            f"{1 if lowcut else 0}"]
    # File handles avoid a Windows anonymous-pipe deadlock for longer renders:
    # the harness emits one double for every input double.
    with tempfile.TemporaryFile() as fin, tempfile.TemporaryFile() as fout:
        fin.write(raw)
        fin.seek(0)
        p = subprocess.run(args, stdin=fin, stdout=fout, stderr=subprocess.PIPE)
        fout.seek(0)
        output = fout.read()
    if p.returncode != 0:
        raise RuntimeError(f"host_duke failed: {p.stderr.decode()}")
    y = np.frombuffer(output, dtype=np.float64)
    if len(y) != len(x):
        raise RuntimeError(f"host_duke emitted {len(y)} samples for {len(x)} input samples")
    return y


def run_ref(x, input_level, bass, treble, level, lowcut):
    return ref.process(x, input=input_level, bass=bass, treble=treble,
                       level=level, lowcut=lowcut, output="quarter")


def db(x):
    return 20.0 * math.log10(max(float(x), 1e-12))


def rms(x):
    return float(np.sqrt(np.mean(np.asarray(x) ** 2)))


def mag_at(y, f, fs=FS):
    seg = np.asarray(y)[len(y) // 4:] * np.hanning(len(y) - len(y) // 4)
    Y = np.abs(np.fft.rfft(seg))
    fr = np.fft.rfftfreq(len(seg), 1.0 / fs)
    k = int(np.argmin(np.abs(fr - f)))
    return float(Y[max(0, k - 2):k + 3].max())


def sine(f, n=8192, amp=0.1):
    return amp * np.sin(2.0 * np.pi * f * np.arange(n) / FS)


def settled(y, keep=0.5):
    return y[int(len(y) * (1.0 - keep)):]


def main():
    if not os.path.exists(HOST):
        build_cmd = ".\\validation\\build_host.ps1" if os.name == "nt" else "bash validation/build_host.sh"
        print(f"ERROR: build the host harness first: {build_cmd}")
        return 1

    results = []

    def check(name, ok, detail):
        results.append((name, bool(ok), detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # Finished-manual baseline: 0/0 is flat, nominal INPUT, 1/4 path.
    base = dict(input_level=0.5, bass=0.0, treble=0.0, level=0.8,
                lowcut=False)

    # T1: small-signal level at the documented flat setting.
    x = sine(1000.0, amp=0.02)
    yk, yr = run_kernel(x, **base), run_ref(x, **base)
    gk, gr = rms(settled(yk)) / rms(settled(x)), rms(settled(yr)) / rms(settled(x))
    check("T1 1/4 gain@1k", abs(db(gk) - db(gr)) <= 1.5,
          f"kernel {db(gk):+.2f} dB vs ref {db(gr):+.2f} dB (dev {db(gk)-db(gr):+.2f})")

    # T2: broadband response of the complete 1/4 path.
    worst, worst_f = 0.0, 0
    for f in (50, 90, 110, 250, 500, 1000, 2000, 4000, 8000, 12000):
        x = sine(f, amp=0.02)
        delta = abs(db(mag_at(run_kernel(x, **base), f)) - db(mag_at(run_ref(x, **base), f)))
        if delta > worst:
            worst, worst_f = delta, f
    check("T2 1/4 magnitude", worst <= 2.0, f"worst dev {worst:.2f} dB at {worst_f} Hz")

    # T3: V1B/V1A must retain even-order character at nominal INPUT.
    x = sine(110.0, amp=0.12)
    yk, yr = run_kernel(x, **base), run_ref(x, **base)
    h1, h2, h3 = (mag_at(yk, 110), mag_at(yk, 220), mag_at(yk, 330))
    even_margin = db(h2) - db(h3)
    ref_margin = db(mag_at(yr, 220)) - db(mag_at(yr, 330))
    check("T3 even-order", even_margin >= 4.0 and abs(even_margin - ref_margin) <= 3.0,
          f"H2 {db(h2/h1):+.1f} dBc, H2-H3 {even_margin:+.1f} dB (ref {ref_margin:+.1f})")

    # T4: boost-only Bass/Treble, relative to the documented 0/0 flat state.
    def tilt(freq, mid, bass, treble):
        yy = run_kernel(sine(freq, amp=0.02), 0.5, bass, treble, 0.8, False)
        mm = run_kernel(sine(mid, amp=0.02), 0.5, bass, treble, 0.8, False)
        return db(mag_at(yy, freq)) - db(mag_at(mm, mid))

    bass_boost = tilt(80, 700, 1.0, 0.0) - tilt(80, 700, 0.0, 0.0)
    treb_boost = tilt(3500, 700, 0.0, 1.0) - tilt(3500, 700, 0.0, 0.0)
    check("T4 Bass boost from 0", bass_boost >= 4.0, f"{bass_boost:+.1f} dB low-vs-mid from flat")
    check("T4 Treble boost from 0", treb_boost >= 4.0, f"{treb_boost:+.1f} dB high-vs-mid from flat")

    # T5: physical C8/R18 ROLLOFF must materially clean the low E fundamental.
    x = sine(45.0, amp=0.02)
    off = db(mag_at(run_kernel(x, 0.5, 0.0, 0.0, 0.8, False), 45))
    on = db(mag_at(run_kernel(x, 0.5, 0.0, 0.0, 0.8, True), 45))
    check("T5 physical LoCut", on - off <= -6.0, f"{on-off:.1f} dB at 45 Hz when enabled")

    # T7: exact silence plus extreme-control settling catches self-noise/ringing.
    quiet_ok, worst_tail = True, 0.0
    attack = np.concatenate([sine(110, n=4096, amp=0.8), np.zeros(44100)])
    silence = np.zeros(8192)
    for bass, treble in ((0.0, 1.0), (1.0, 1.0), (1.0, 0.0)):
            args = (0.5, bass, treble, 0.5, False)
            yz, ya = run_kernel(silence, *args), run_kernel(attack, *args)
            tail = rms(ya[-8192:])
            worst_tail = max(worst_tail, tail)
            if (not np.all(np.isfinite(yz)) or not np.all(np.isfinite(ya)) or
                    np.max(np.abs(yz)) > 1e-9 or np.max(np.abs(ya)) >= 8.0 or tail > 2e-5):
                quiet_ok = False
    check("T7 silence + settling", quiet_ok, f"worst post-attack tail RMS {worst_tail:.2e}")

    # T8: bright nonlinear stress for the dedicated 4x nonlinear path.
    x = sine(7000.0, amp=0.3)
    y = run_kernel(x, 0.8, 0.0, 1.0, 0.8, False)
    seg = y[len(y) // 4:] * np.hanning(len(y) - len(y) // 4)
    Y, fr = np.abs(np.fft.rfft(seg)), np.fft.rfftfreq(len(seg), 1.0 / FS)
    fund = Y[int(np.argmin(np.abs(fr - 7000)))]
    alias_dbc = db(float(Y[fr < 6000].max())) - db(fund)
    check("T8 aliasing", alias_dbc <= -24.0, f"worst in-band spur {alias_dbc:.1f} dBc @7k bright stress")

    # T9: the reported failure mode is a hard open low-E with both boosts at
    # maximum.  Ignore true integer harmonics and look for folded/non-harmonic
    # products in the audible band.  A full one-second FFT keeps 41 Hz bin
    # aligned and lets the slow shared-cathode state settle.
    f0, n0 = 41.0, 88200
    x = 0.75 * np.sin(2.0 * np.pi * f0 * np.arange(n0) / FS)
    y = run_kernel(x, 0.5, 1.0, 1.0, 0.5, False)[-44100:]
    Y = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    fr = np.fft.rfftfreq(len(y), 1.0 / FS)
    fund = Y[int(np.argmin(np.abs(fr - f0)))]
    nonharmonic = np.ones_like(Y, dtype=bool)
    nonharmonic[:3] = False
    for harmonic in range(1, int(20000.0 / f0) + 1):
        k = int(np.argmin(np.abs(fr - harmonic * f0)))
        nonharmonic[max(0, k - 2):k + 3] = False
    spur = float(Y[nonharmonic].max())
    check("T9 low-E extreme alias", db(spur) - db(fund) <= -50.0,
          f"worst non-harmonic spur {db(spur) - db(fund):.1f} dBc @ Bass/Trble 100")

    npass = sum(ok for _, ok, _ in results)
    print(f"\n{npass}/{len(results)} checks passed")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
