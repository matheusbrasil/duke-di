#!/usr/bin/env python3
"""Fast safety checks for the Nobelium control/output topology corners."""
from __future__ import annotations

import os
import struct
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.path.join(HERE, "host_duke.exe" if os.name == "nt" else "host_duke")
FS = 44100.0


def render(x, input_, bass, treble, level, lowcut):
    raw = struct.pack(f"<{len(x)}d", *np.asarray(x, dtype=np.float64))
    with tempfile.TemporaryFile() as fin, tempfile.TemporaryFile() as fout:
        fin.write(raw)
        fin.seek(0)
        subprocess.run(
            [HOST, str(input_), str(bass), str(treble), str(level),
             str(int(lowcut))],
            stdin=fin, stdout=fout, stderr=subprocess.PIPE, check=True,
        )
        fout.seek(0)
        return np.frombuffer(fout.read(), dtype=np.float64)


def main():
    if not os.path.exists(HOST):
        print("FAIL: build validation host harness first")
        return 1

    failures = []
    silent = np.zeros(4096)
    attack = np.concatenate([
        0.8 * np.sin(2 * np.pi * 110 * np.arange(4096) / FS),
        # R24*(C13+C14) is ~0.33 s. Assess settling after a full second so
        # the physical shared-cathode recovery is not misclassified as DSP
        # ringing or self-noise.
        np.zeros(44100),
    ])

    # Every control corner must remain finite, quiet on digital silence and
    # settle after a strong low-note attack. These are the failure modes seen
    # in the original pedal audition.
    for input_ in (0.0, 0.5, 1.0):
        for bass in (0.0, 1.0):
            for treble in (0.0, 1.0):
                for lowcut in (0, 1):
                    for _ in (0,):
                        label = f"in={input_} bass={bass} treb={treble} lc={lowcut}"
                        y0 = render(silent, input_, bass, treble, 0.8, lowcut)
                        y1 = render(attack, input_, bass, treble, 0.8, lowcut)
                        tail = y1[-4096:]
                        ok = (np.all(np.isfinite(y0)) and np.all(np.isfinite(y1))
                              and np.max(np.abs(y0)) < 1e-10
                              and np.max(np.abs(y1)) < 8.0
                              and np.sqrt(np.mean(tail * tail)) < 2e-5)
                        if not ok:
                            failures.append(label)

    if failures:
        print("corner test FAIL:")
        for failure in failures:
            print("  " + failure)
        return 1
    print("corner test PASS: 24 component-model control corners")
    return 0


if __name__ == "__main__":
    sys.exit(main())
