#!/usr/bin/env python3
"""probe_decode.py - turn a recording of the cycle probe back into cycles.

usage:
  probe_decode.py recording.wav [--skip SECONDS]
  probe_decode.py raw.f32 --raw [--rate 44100] [--skip SECONDS]

The probe outputs square waves at f = 7e6 / cycles: channel A (left) is the
running mean, channel B (right) the decaying peak.  Frequency is measured from
zero crossings over the analysed span, so level and EQ do not matter.  Record
at least 5 s; the first second is skipped by default while the mean settles.
"""
import argparse
import sys
import wave

import numpy as np

K = 7.0e6


def load(path, raw, rate):
    if raw:
        x = np.fromfile(path, dtype="<f4").reshape(-1, 2)
        return x, rate
    with wave.open(path, "rb") as w:
        rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        data = w.readframes(n)
    if width == 2:
        x = np.frombuffer(data, "<i2").astype(np.float64)
    elif width == 3:
        b = np.frombuffer(data, np.uint8).reshape(-1, 3)
        x = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8)
             | (b[:, 2].astype(np.int8).astype(np.int32) << 16)).astype(np.float64)
    elif width == 4:
        x = np.frombuffer(data, "<i4").astype(np.float64)
    else:
        sys.exit("unsupported sample width %d" % width)
    x = x.reshape(-1, ch)
    if ch == 1:
        x = np.repeat(x, 2, axis=1)
    return x[:, :2], rate


def freq(sig, rate):
    s = sig - np.mean(sig)
    amp = np.percentile(np.abs(s), 95)
    if amp <= 0:
        return 0.0, 0.0
    # hysteresis at +/- 30% of the level, so noise cannot add crossings
    hi, lo = 0.3 * amp, -0.3 * amp
    state, edges = 0, []
    for i, v in enumerate(s):
        if state <= 0 and v > hi:
            if state < 0:
                edges.append(i)
            state = 1
        elif state >= 0 and v < lo:
            state = -1
    if len(edges) < 3:
        return 0.0, amp
    periods = np.diff(edges)
    return rate / periods.mean(), amp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--raw", action="store_true")
    ap.add_argument("--rate", type=int, default=44100)
    ap.add_argument("--skip", type=float, default=1.0)
    a = ap.parse_args()
    x, rate = load(a.path, a.raw, a.rate)
    x = x[int(a.skip * rate):]
    print("analysed %.1f s at %d Hz" % (len(x) / rate, rate))
    fa, aa = freq(x[:, 0], rate)
    fb, ab = freq(x[:, 1], rate)
    if fa and not fb and abs(fa - 1000) < 20:
        print("marker tone only: the DSP cycle counter is not running; no measurement")
        return
    for name, f, amp in (("A mean", fa, aa), ("B peak", fb, ab)):
        if f:
            c = K / f
            print("%s: %8.2f Hz -> %7.0f cycles per 16-sample call (%.1f cycles/sample)"
                  % (name, f, c, c / 16))
        else:
            print("%s: no tone found (level %.3g)" % (name, amp))


if __name__ == "__main__":
    main()
