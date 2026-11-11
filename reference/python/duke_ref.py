"""duke_ref.py - Tier A "golden" reference model of the Nobelium / Noble DI.

A white-box, oversampled, per-sample model of the audio chain in
docs/01-circuit-analysis.md. Linear sections use exact bilinear-discretised
transfer functions derived from the BOM component values; the two 12AU7 gain
stages and the V2 White cathode follower use the Koren device model in tube.py.

This is the DESKTOP reference. It is allowed everything the embedded kernel is
not (division, exp/log, per-sample Newton, 8x oversampling). Its job is to be
correct, to be the yardstick the embedded tier is measured against, and to emit
the static transfer LUTs the kernel reads (see bake_tables.py).

Modelling convention (documented in docs/assumptions.md):
 * Signal stays in a single normalised domain approx [-1, 1].
 * Each 12AU7 stage is rendered as a *unity small-signal gain* waveshaper: the
   Koren static plate map, scaled so tiny inputs pass at unity but the genuine
   starved-12AU7 curvature, asymmetry and soft clipping appear as drive grows.
   This separates "character" (exact, from the device model) from "level
   staging" (explicit CAL_* constants), the honest way to keep a two-stage x16
   cascade numerically bounded.
 * Linear corner frequencies are EXACT from the BOM; absolute inter-stage
   gains are fitted calibration constants.
"""
from __future__ import annotations
import numpy as np
from scipy import signal
import tube
import tonestack

FS = 44100.0
OS = 8

B_PLUS = 250.0
R_LOAD = 220e3
R_K = 1.5e3
V_SENS = 0.35

CAL_DRIVE_MIN = 0.25
CAL_DRIVE_MAX = 9.0
CAL_INTERSTAGE = 2.2
CAL_VOL_NODE = 1.0
CAL_MAKEUP = 0.9

# passive FMV tone stack (tonestack.py) replaces the old independent shelves.
# SAG_FC: V1A+V1B share R24 1k5 bypassed by C13 1u || C14 220u = 221uF
#   -> fc = 1/(2*pi*1k5*221u) = 0.48 Hz (was modelled at 2.06 Hz).
SAG_FC = 0.48
# ROLLOFF low-cut: C8 4n7 into R18 220k, source = TREBLE wiper Zout.
LOWCUT_C8 = 4.7e-9
LOWCUT_R18 = 220e3
TONE_MAKEUP = tonestack.noon_makeup()   # ~unity broadband at noon knobs
GRID_CLAMP_V = 0.6


# ---- linear building blocks (exact corners from the BOM) ------------------
def bilinear_hpf(fc, fs):
    k = 2.0 * fs
    wc = 2.0 * fs * np.tan(2.0 * np.pi * fc / (2.0 * fs))
    b = np.array([k, -k]) / (k + wc)
    a = np.array([1.0, (wc - k) / (k + wc)])
    return b, a


def low_shelf(fc, gain_db, fs):
    A = 10.0 ** (gain_db / 20.0)
    wa = 2.0 * fs * np.tan(2.0 * np.pi * fc / (2.0 * fs))
    return signal.bilinear([1.0, A * wa], [1.0, wa], fs)


def high_shelf(fc, gain_db, fs):
    A = 10.0 ** (gain_db / 20.0)
    wa = 2.0 * fs * np.tan(2.0 * np.pi * fc / (2.0 * fs))
    return signal.bilinear([A, wa], [1.0, wa], fs)


def one_pole_env(x, fc, fs):
    a = np.exp(-2.0 * np.pi * fc / fs)
    return signal.lfilter([1.0 - a], [1.0, -a], np.abs(x))


# ---- 12AU7 stage waveshaper (unity small-signal gain, true curvature) -----
class TubeStage:
    def __init__(self):
        self.vk0, self.vp0 = tube.cathode_voltage_dc(
            B_PLUS, R_LOAD, R_K, n_tubes=2)
        d = 1e-3
        vp = tube.solve_plate_voltage(np.array([-d, d]), self.vk0,
                                      B_PLUS, R_LOAD)
        self.A0 = float(-(vp[1] - vp[0]) / (2 * d))
        self.norm = self.A0 * V_SENS

    def shape(self, u, vk=None):
        vk = self.vk0 if vk is None else vk
        vgrid = u * V_SENS
        if np.isscalar(vk):
            vp = tube.solve_plate_voltage(vgrid, float(vk), B_PLUS, R_LOAD)
            return -(vp - self.vp0) / self.norm
        return self._shape_vk_array(vgrid, vk)

    def _shape_vk_array(self, vgrid, vk):
        lo, hi = float(vk.min()), float(vk.max())
        if hi - lo < 1e-4:
            vp = tube.solve_plate_voltage(vgrid, (lo + hi) / 2, B_PLUS, R_LOAD)
            return -(vp - self.vp0) / self.norm
        levels = np.linspace(lo, hi, 8)
        maps = np.stack(
            [-(tube.solve_plate_voltage(vgrid, float(lv), B_PLUS, R_LOAD)
               - self.vp0) / self.norm for lv in levels], axis=0)
        idx = np.clip((vk - lo) / (hi - lo) * 7.0, 0, 7)
        i0 = np.floor(idx).astype(int)
        i1 = np.minimum(i0 + 1, 7)
        fr = idx - i0
        n = np.arange(len(vgrid))
        return (1 - fr) * maps[i0, n] + fr * maps[i1, n]


_STAGE = None
def stage():
    global _STAGE
    if _STAGE is None:
        _STAGE = TubeStage()
    return _STAGE


# ---- full chain -----------------------------------------------------------
def process(x, *, gain=0.5, bass=0.5, treble=0.5, level=0.8,
            lowcut=False, xfmr=False, fs=FS, os_factor=OS):
    x = np.asarray(x, dtype=np.float64)
    st = stage()

    u = signal.resample_poly(x, os_factor, 1) if os_factor > 1 else x.copy()
    fso = fs * os_factor

    drive = CAL_DRIVE_MIN * (CAL_DRIVE_MAX / CAL_DRIVE_MIN) ** gain
    u = u * drive

    # V1B with shared-rail sag (shared cathode 221uF -> 0.48 Hz)
    sag = one_pole_env(u, SAG_FC, fso)
    u = st.shape(u, st.vk0 + 0.6 * sag)

    # passive interactive FMV tone stack (exact nodal model) + noon makeup
    wt = tonestack.taper(treble)
    wb = tonestack.taper(bass)
    be, ae = tonestack.design_digital(wt, wb, fso)
    u = signal.lfilter(be, ae, u) * TONE_MAKEUP

    # ROLLOFF low-cut: corner is TREBLE-dependent (wiper Zout in series)
    if lowcut:
        rs = tonestack.zout_T(wt, wb)
        fc = 1.0 / (2.0 * np.pi * (rs + LOWCUT_R18) * LOWCUT_C8)
        bh, ah = bilinear_hpf(fc, fso)
        u = signal.lfilter(bh, ah, u)

    # V1A (shared cathode sag, 0.48 Hz)
    u = u * CAL_INTERSTAGE
    sag2 = one_pole_env(u, SAG_FC, fso)
    u = st.shape(u, st.vk0 + 0.6 * sag2)

    # V1A loading + C7 DC block
    bh, ah = bilinear_hpf(9.5, fso)
    u = signal.lfilter(bh, ah, u)

    # VOLUME pot (A250k log) + C9 DC block
    u = u * CAL_VOL_NODE * (level ** 2)
    bh, ah = bilinear_hpf(3.18, fso)
    u = signal.lfilter(bh, ah, u)

    # V2 White cathode follower + grid clamp
    u = white_cf(u, fso)

    # output HPF
    bh, ah = bilinear_hpf(4.02, fso)
    u = signal.lfilter(bh, ah, u)

    if xfmr:
        u = transformer(u, fso)

    if os_factor > 1:
        u = signal.resample_poly(u, 1, os_factor)
    return u * CAL_MAKEUP * stock_vol_gain(level)


def white_cf(u, fs):
    u_cl = np.where(u > GRID_CLAMP_V / V_SENS, GRID_CLAMP_V / V_SENS, u)
    bh, ah = bilinear_hpf(33.9, fs)
    hi = signal.lfilter(bh, ah, u_cl)
    lo = u_cl - hi
    sym = 0.92 * hi
    asym = 0.92 * (lo + 0.15 * lo * np.abs(lo))
    return sym + asym


def transformer(u, fs):
    bl, al = bilinear_hpf(60.0, fs)
    hf = signal.lfilter(bl, al, u)
    lf = u - hf
    lf = np.tanh(lf * 2.5) / 2.5
    b, a = signal.bilinear([2 * np.pi * 18000.0],
                           [1.0, 2 * np.pi * 18000.0], fs)
    return signal.lfilter(b, a, lf + hf)


def stock_vol_gain(level):
    v = level * 100.0
    return v / 80.0 if v <= 80.0 else 1.0 + (v - 80.0) / 40.0


if __name__ == "__main__":
    fs = FS
    t = np.arange(int(0.2 * fs)) / fs
    for g in (0.2, 0.5, 0.9):
        x = 0.3 * np.sin(2 * np.pi * 110.0 * t)
        y = process(x, gain=g, bass=0.6, treble=0.5, level=0.8, lowcut=True)
        print("gain=%.1f  in rms=%.3f  out rms=%.3f peak=%.3f"
              % (g, np.sqrt(np.mean(x ** 2)), np.sqrt(np.mean(y ** 2)),
                 np.max(np.abs(y))))
