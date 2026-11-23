"""duke_ref.py - Tier A "golden" reference model of the Nobelium / Noble DI.

A white-box, oversampled, per-sample model of the audio chain in
docs/01-circuit-analysis.md. It models the two real output paths: the 1/4"
output uses V2's White cathode follower, while the XLR DI path leaves V2 out
and is transformer-coupled after V1A.

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

# INPUT is virtual source level, not a Nobelium-panel gain control.  Its
# bounded -6..+6 dB range has unity at 50, avoiding fuzz-like overdrive.
INPUT_MIN = 0.5
INPUT_MAX = 2.0
CAL_INTERSTAGE = 2.2
CAL_MAKEUP = 0.9

# passive FMV tone stack (tonestack.py) replaces the old independent shelves.
# SAG_FC: V1A+V1B share R24 1k5 bypassed by C13 1u || C14 220u = 221uF
#   -> fc = 1/(2*pi*1k5*221u) = 0.48 Hz (was modelled at 2.06 Hz).
SAG_FC = 0.48
CATH_SCALE = R_K / V_SENS
# Finished-pedal manual: -6 dB/oct below 90 Hz on both outputs.
LOWCUT_HZ = 90.0
LOWCUT_C8 = 4.7e-9
LOWCUT_R18 = 220e3
TONE_MAKEUP = tonestack.flat_makeup()
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
        self.i0 = float(tube.plate_current(
            np.array([-self.vk0]), np.array([self.vp0 - self.vk0]))[0])

    def shape(self, u, vk=None):
        vk = self.vk0 if vk is None else vk
        vgrid = u * V_SENS
        if np.isscalar(vk):
            vp = tube.solve_plate_voltage(vgrid, float(vk), B_PLUS, R_LOAD)
            return -(vp - self.vp0) / self.norm
        return self._shape_vk_array(vgrid, vk)

    def current_delta(self, u, vk=None):
        """Plate-current change from quiescence, in amperes.

        This is sampled into the embedded LUT so the R24/C13/C14 shared
        cathode state is driven by actual Koren plate-current demand rather
        than by the old absolute-signal compression heuristic.
        """
        vk = self.vk0 if vk is None else vk
        vgrid = np.asarray(u, dtype=np.float64) * V_SENS
        vp = tube.solve_plate_voltage(vgrid, float(vk), B_PLUS, R_LOAD)
        ip = tube.plate_current(vgrid - float(vk), vp - float(vk))
        return ip - self.i0

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
def input_drive(value):
    """Map INPUT 0..1 to a bounded virtual instrument source level."""
    value = float(np.clip(value, 0.0, 1.0))
    return INPUT_MIN * (INPUT_MAX / INPUT_MIN) ** value


def _output_mode(output, xfmr):
    """Normalise output mode; retain the old xfmr selector as an API shim."""
    if xfmr is not None:
        return "xlr" if xfmr else "quarter"
    aliases = {"xlr": "xlr", "di": "xlr", "1/4": "quarter",
               "1/4\"": "quarter", "quarter": "quarter", "inst": "quarter"}
    try:
        return aliases[str(output).lower()]
    except KeyError as exc:
        raise ValueError("output must be 'xlr' or 'quarter'") from exc


def process(x, *, input=0.5, bass=0.0, treble=0.0, level=0.8,
            lowcut=False, output="xlr", gain=None, xfmr=None, fs=FS,
            os_factor=OS):
    """Render a Nobelium output path.

    ``input`` replaces the old artificial ``gain`` name. ``gain`` and
    ``xfmr`` remain accepted only for old callers: gain aliases input and
    xfmr False/True selects quarter/XLR respectively.
    """
    x = np.asarray(x, dtype=np.float64)
    st = stage()
    if gain is not None:
        input = gain
    mode = _output_mode(output, xfmr)

    u = signal.resample_poly(x, os_factor, 1) if os_factor > 1 else x.copy()
    fso = fs * os_factor

    u = u * input_drive(input)

    # First estimate of V1B/V1A currents, then the physical shared-cathode
    # response. R24 sees the sum of the two triodes; C13||C14 makes this a
    # slow 0.48 Hz bias shift, not the old independent |signal| compressor.
    v1b_in = u
    v1b_probe = st.shape(v1b_in)
    wt = tonestack.taper(treble)
    wb = tonestack.bass_taper(bass)
    bp, ap = tonestack.design_digital(wt, wb, fso)
    v1a_probe = signal.lfilter(bp, ap, v1b_probe) * TONE_MAKEUP * CAL_INTERSTAGE
    icath = st.current_delta(v1b_in) + st.current_delta(v1a_probe)
    a_cath = np.exp(-2.0 * np.pi * SAG_FC / fso)
    cath = signal.lfilter([1.0 - a_cath], [1.0, -a_cath], CATH_SCALE * icath)
    cath = np.clip(cath, -4.0, 4.0)
    u = st.shape(v1b_in - cath)

    # Passive interactive FMV stack. ROLLOFF is part of the same loaded
    # network, not a generic post-EQ shelf.
    if lowcut:
        be, ae = tonestack.design_rolloff_digital(wt, wb, fso)
    else:
        be, ae = tonestack.design_digital(wt, wb, fso)
    u = signal.lfilter(be, ae, u) * TONE_MAKEUP

    # V1A sees the same cathode-bias state as V1B.
    u = u * CAL_INTERSTAGE
    u = st.shape(u - cath)

    # V1A loading + C7 DC block
    bh, ah = bilinear_hpf(9.5, fso)
    u = signal.lfilter(bh, ah, u)

    # The physical paths diverge here. V2 (the second 12AU7) buffers only
    # the 1/4" output. XLR leaves V2 out and is transformer-coupled.
    if mode == "quarter":
        u = u * audio_pot(level)
        bh, ah = bilinear_hpf(3.18, fso)  # C9 coupling to V2
        u = signal.lfilter(bh, ah, u)
        u = white_cf(u, fso)
        bh, ah = bilinear_hpf(4.02, fso)  # C12/R22 1/4" HPF
        u = signal.lfilter(bh, ah, u)
    else:
        u = jensen_jtdb_epc(u, fso)
        u = u * xlr_trim(level)

    if os_factor > 1:
        u = signal.resample_poly(u, 1, os_factor)
    return u * CAL_MAKEUP


def white_cf(u, fs):
    """Measured clean V2 follower loss; nonlinear V2 awaits isolated 1/4 data."""
    del fs
    return 0.92 * u


def audio_pot(level):
    """A250k audio-taper approximation for the 1/4-inch VOLUME pot."""
    level = float(np.clip(level, 0.0, 1.0))
    return level * level


def xlr_trim(level):
    """500k XLR trim, intentionally after the transformer branch."""
    level = float(np.clip(level, 0.0, 1.0))
    return level * level


def jensen_jtdb_epc(u, fs):
    """First-pass JT-DB-EPC DI branch approximation.

    It isolates the known core soft-saturation and HF leakage behaviour so a
    later datasheet fit can replace it without touching either valve path.
    """
    bl, al = bilinear_hpf(60.0, fs)
    hf = signal.lfilter(bl, al, u)
    lf = u - hf
    lf = np.tanh(lf * 2.5) / 2.5
    b, a = signal.bilinear([2 * np.pi * 18000.0],
                           [1.0, 2 * np.pi * 18000.0], fs)
    return signal.lfilter(b, a, lf + hf)


# Compatibility alias for older analysis callers.
transformer = jensen_jtdb_epc


def stock_vol_gain(level):
    v = level * 100.0
    return v / 80.0 if v <= 80.0 else 1.0 + (v - 80.0) / 40.0


if __name__ == "__main__":
    fs = FS
    t = np.arange(int(0.2 * fs)) / fs
    for g in (0.2, 0.5, 0.9):
        x = 0.3 * np.sin(2 * np.pi * 110.0 * t)
        y = process(x, input=g, bass=0.0, treble=0.0, level=0.8,
                    lowcut=True, output="xlr")
        print("input=%.1f  in rms=%.3f  out rms=%.3f peak=%.3f"
              % (g, np.sqrt(np.mean(x ** 2)), np.sqrt(np.mean(y ** 2)),
                 np.max(np.abs(y))))
