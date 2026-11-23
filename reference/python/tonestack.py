"""Nodal (MNA) solver for the Nobelium / Noble-DI passive FMV tone stack.

Topology read from files/sch/audio_full.png (V1B plate -> grid of V1A):

    P  = V1B plate node (stack input, driven through plate Zout Rs)
    M  = R13 bottom = C10 left = C11 left
    A  = C10 right = TREBLE bottom term = BASS top (rheostat)
    B  = C11 right = R21 top = BASS bottom (rheostat)
    T  = TREBLE wiper = stack output
    Tt = TREBLE top term = C6 right

    R13 47k : P - M
    C6  270p: P - Tt
    C10 100n: M - A
    C11 100n: M - B
    TREBLE A250k: Tt -(1-wt)*Rp- T -(wt)*Rp- A      (wt=1 -> bright)
    BASS   A250k: rheostat A - B, value wb*Rp       (wb=1 -> full bass)
    R21 2k7 : B - GND
    Rs      : Vin -> P   (12AU7 plate output impedance rp||R9)
    Rload   : T - GND    (numerical representation of V1A's very-high-Z grid)

The three caps make this an exact 3rd-order rational H(s)=V_T/Vin.  We sample
the MNA transfer on the jw axis and recover num/den polynomials by least
squares (the fit is exact because the true order is known).
"""
import numpy as np
from scipy.interpolate import PchipInterpolator

# --- component values (BOM) -------------------------------------------------
R13 = 47e3
C6  = 270e-12
C10 = 100e-9
C11 = 100e-9
RP  = 250e3          # both pots, A250k
R21 = 2.7e3
PLATE_ZOUT = 7.4e3   # rp(12AU7)~7.7k || R9 220k  (source impedance of V1B plate)
# The audio schematic has R15=1k5 as a series grid stopper, but no 1 Mohm
# V1A grid-leak resistor.  The prior 1 Mohm shunt was invented and changes
# the tone-control loading.  Keep only a numerically finite, electrically
# negligible grid load; grid capacitance/nonlinearity is handled by the tube
# stage rather than by a fictional resistor.
TONE_LOAD  = 1.0e12

EPS = 1.0            # 1 ohm guard so a pot end never divides by zero

# node indices
P, M, A, B, T, Tt = range(6)
N = 6


def _stamp(Y, i, j, y):
    """Stamp an admittance y between nodes i and j (j may be 'gnd')."""
    if j == 'gnd':
        Y[i, i] += y
        return
    Y[i, i] += y
    Y[j, j] += y
    Y[i, j] -= y
    Y[j, i] -= y


def _solve(s, wt, wb, rs=PLATE_ZOUT, rload=TONE_LOAD):
    """Return V_T for a 1V source (through rs) at complex frequency s."""
    Y = np.zeros((N, N), dtype=complex)
    rhs = np.zeros(N, dtype=complex)

    gs = 1.0 / rs
    _stamp(Y, P, 'gnd', gs)        # source resistor to the 1V rail
    rhs[P] += gs * 1.0

    _stamp(Y, P, M, 1.0 / R13)
    _stamp(Y, P, Tt, s * C6)
    _stamp(Y, M, A, s * C10)
    _stamp(Y, M, B, s * C11)

    r_tt = (1.0 - wt) * RP + EPS   # Tt - T
    r_ta = wt * RP + EPS           # T  - A
    _stamp(Y, Tt, T, 1.0 / r_tt)
    _stamp(Y, T, A, 1.0 / r_ta)

    r_ab = wb * RP + EPS           # A - B rheostat
    _stamp(Y, A, B, 1.0 / r_ab)

    _stamp(Y, B, 'gnd', 1.0 / R21)
    _stamp(Y, T, 'gnd', 1.0 / rload)

    v = np.linalg.solve(Y, rhs)
    return v[T]


def transfer(f, wt, wb, **kw):
    """Complex H(jw)=V_T/Vin at frequency f (Hz) or array of f."""
    f = np.atleast_1d(np.asarray(f, dtype=float))
    out = np.array([_solve(2j * np.pi * fi, wt, wb, **kw) for fi in f])
    return out


# --- A-taper (audio/log) pot law: ~15% resistance at mid-rotation -----------
TAPER_K = 3.46   # (exp(k*0.5)-1)/(exp(k)-1) ~= 0.15


def taper(n, k=TAPER_K):
    """Map a normalised knob value n in [0,1] to pot wiper fraction (A-taper)."""
    n = np.clip(n, 0.0, 1.0)
    return (np.exp(k * n) - 1.0) / (np.exp(k) - 1.0)


# The schematic determines the electrical topology, but not the exact travel law
# of the physical BASS A250k pot.  Full-rate NAM A2 measurements of a Noble
# capture set identify the effective wiper resistance at two repeatable clock
# positions: 9 o'clock (0.20 travel) = 0.0217, and noon (0.50) = 0.0588.
# A monotone cubic preserves those measurements, the known endpoints, and a
# smooth boost-only progression.  TREBLE remains on the documented A-taper;
# its measured response already agrees within about 1 dB.
_BASS_TRAVEL = np.array([0.0, 0.20, 0.50, 1.0])
_BASS_WIPER = np.array([0.0, 0.0217, 0.0588, 1.0])
_BASS_TAPER = PchipInterpolator(_BASS_TRAVEL, _BASS_WIPER, extrapolate=False)


def bass_taper(n):
    """Empirical Noble BASS A250k travel law, normalised to 0..1."""
    n = np.clip(n, 0.0, 1.0)
    return _BASS_TAPER(n)


def zout_T(wt, wb, f=1000.0, rs=PLATE_ZOUT, rload=TONE_LOAD):
    """Output impedance looking back into the stack from node T (ohms).

    Injects 1A into T with the source rail grounded (Vin=0); Z = V_T.  Used to
    make the downstream ROLLOFF low-cut corner TREBLE-dependent, since the
    series source resistance of the C8/R18 high-pass is the wiper's Zout.
    """
    s = 2j * np.pi * f
    Y = np.zeros((N, N), dtype=complex)
    gs = 1.0 / rs
    _stamp(Y, P, 'gnd', gs)          # source rail grounded
    _stamp(Y, P, M, 1.0 / R13)
    _stamp(Y, P, Tt, s * C6)
    _stamp(Y, M, A, s * C10)
    _stamp(Y, M, B, s * C11)
    _stamp(Y, Tt, T, 1.0 / ((1.0 - wt) * RP + EPS))
    _stamp(Y, T, A, 1.0 / (wt * RP + EPS))
    _stamp(Y, A, B, 1.0 / (wb * RP + EPS))
    _stamp(Y, B, 'gnd', 1.0 / R21)
    _stamp(Y, T, 'gnd', 1.0 / rload)
    rhs = np.zeros(N, dtype=complex)
    rhs[T] = 1.0
    v = np.linalg.solve(Y, rhs)
    return float(np.abs(v[T]))


def design_digital(wt, wb, fs, **kw):
    """Exact analog H(s) of the stack, bilinear-transformed to digital (b,a)."""
    from scipy import signal as _sig
    num, den = rational(wt, wb, **kw)
    return _sig.bilinear(num, den, fs)


def _solve_rolloff(s, wt, wb, rs=PLATE_ZOUT, rload=TONE_LOAD):
    """Return the post-C8/R18 voltage for a 1 V source.

    This is the literal ROLLOFF-on topology: C8 4n7 from the Treble wiper to
    the V1A grid node and R18 220k from that node to ground.  It must be
    solved together with the stack because the wiper source impedance changes
    with both controls; cascading a fixed 90 Hz HPF is not the circuit.
    """
    out = N
    Y = np.zeros((N + 1, N + 1), dtype=complex)
    rhs = np.zeros(N + 1, dtype=complex)
    gs = 1.0 / rs
    _stamp(Y, P, 'gnd', gs)
    rhs[P] += gs
    _stamp(Y, P, M, 1.0 / R13)
    _stamp(Y, P, Tt, s * C6)
    _stamp(Y, M, A, s * C10)
    _stamp(Y, M, B, s * C11)
    _stamp(Y, Tt, T, 1.0 / ((1.0 - wt) * RP + EPS))
    _stamp(Y, T, A, 1.0 / (wt * RP + EPS))
    _stamp(Y, A, B, 1.0 / (wb * RP + EPS))
    _stamp(Y, B, 'gnd', 1.0 / R21)
    _stamp(Y, T, 'gnd', 1.0 / rload)
    _stamp(Y, T, out, s * 4.7e-9)  # C8
    _stamp(Y, out, 'gnd', 1.0 / 220e3)  # R18
    return np.linalg.solve(Y, rhs)[out]


def rational_rolloff(wt, wb, **kw):
    """Recover the exact fourth-order post-ROLLOFF transfer."""
    w0 = 2.0 * np.pi * 1000.0
    ang = np.linspace(0.12, np.pi - 0.12, 15)
    s = np.concatenate([w0 * np.exp(1j * ang), 8.0 * w0 * np.exp(1j * ang)])
    sn = s / w0
    H = np.array([_solve_rolloff(si, wt, wb, **kw) for si in s])
    # H*(1+a1*s+...+a4*s^4) = b0+...+b4*s^4
    cols = [sn ** k for k in range(5)]
    cols += [-H * sn ** k for k in range(1, 5)]
    amat = np.stack(cols, axis=1)
    x, *_ = np.linalg.lstsq(np.vstack([amat.real, amat.imag]),
                            np.concatenate([H.real, H.imag]), rcond=None)
    scale = w0 ** np.arange(5)
    b = x[:5] / scale
    a = np.concatenate([[1.0], x[5:]]) / scale
    return b[::-1], a[::-1]


def design_rolloff_digital(wt, wb, fs, **kw):
    """Bilinear 4th-order filter for the physical ROLLOFF-on network."""
    from scipy import signal as _sig
    num, den = rational_rolloff(wt, wb, **kw)
    return _sig.bilinear(num, den, fs)


def noon_makeup(n_bass=0.5, n_treble=0.5, f=1000.0):
    """Gain that restores ~unity broadband level at the noon knob setting.

    The passive FMV stack has large insertion loss; at noon (A-taper -> wiper
    ~0.15) the response is nearly flat and heavily attenuated, so a fixed
    makeup of 1/|H(noon)| makes noon ~0 dB and turns the knobs into
    boost-from-noon controls (matching the pedal's 'boost-only' voicing)."""
    wt, wb = taper(n_treble), bass_taper(n_bass)
    return 1.0 / float(np.abs(transfer(f, wt, wb)[0]))


def flat_makeup(f=1000.0):
    """Gain that restores unity at the documented fully-CCW flat setting."""
    wt, wb = taper(0.0), taper(0.0)
    return 1.0 / float(np.abs(transfer(f, wt, wb)[0]))


def rational(wt, wb, **kw):
    """Recover analog num/den polynomials (descending powers) of H(s).

    Order is (3,3); least squares over jw samples is exact for a rational
    of the true order.  Returns (num, den) each length 4, den normalised a0=1.

    The transfer is exactly a (3,3) rational, so it is identified exactly from
    a handful of distinct, well-scaled complex sample points -- no frequency
    sweep needed.  Sampling on circles |s| ~ w0 keeps the Vandermonde-like LS
    perfectly conditioned, which the earlier wide jw sweep did not.
    """
    w0 = 2.0 * np.pi * 1000.0          # frequency scale -> |sn| ~ O(1)
    ang = np.linspace(0.15, np.pi - 0.15, 11)
    s = np.concatenate([w0 * np.exp(1j * ang), 8.0 * w0 * np.exp(1j * ang)])
    sn = s / w0
    H = np.array([_solve(si, wt, wb, **kw) for si in s])
    # H*(a0 + a1 sn + a2 sn^2 + a3 sn^3) = b0 + b1 sn + ... , a0=1
    # unknowns x=[b0,b1,b2,b3,a1,a2,a3]
    cols = []
    for k in range(4):
        cols.append(sn ** k)                # +b_k
    for k in range(1, 4):
        cols.append(-H * sn ** k)           # -a_k
    Amat = np.stack(cols, axis=1)
    rhs = H                                 # = a0 * H
    AA = np.vstack([Amat.real, Amat.imag])
    bb = np.concatenate([rhs.real, rhs.imag])
    x, *_ = np.linalg.lstsq(AA, bb, rcond=None)
    b = x[0:4]
    a = np.concatenate([[1.0], x[4:7]])
    # undo the frequency scaling: coeff of sn^k -> coeff of s^k is /w0^k
    scale = w0 ** np.arange(4)
    b = b / scale
    a = a / scale
    # to descending powers for scipy
    num = b[::-1]
    den = a[::-1]
    return num, den


if __name__ == "__main__":
    import scipy.signal as sig

    def db(x):
        return 20 * np.log10(np.abs(x) + 1e-18)

    freqs = np.array([30, 60, 150, 500, 1000, 3500, 10000])
    print("=== DC / HF insertion & shape sanity (wt,wb wiper fractions) ===")
    for name, wt, wb in [("flat-ish .5/.5", 0.5, 0.5),
                         ("bass max",     0.5, 1.0),
                         ("bass min",     0.5, 0.0),
                         ("treb max",     1.0, 0.5),
                         ("treb min",     0.0, 0.5),
                         ("both max",     1.0, 1.0),
                         ("both min",     0.0, 0.0)]:
        H = transfer(freqs, wt, wb)
        line = "  ".join(f"{f:>6.0f}Hz={db(h):+5.1f}" for f, h in zip(freqs, H))
        print(f"{name:14s} {line}")

    print("\n=== exact rational fit residual + stability ===")
    worst = 0.0
    worst_pr = 0.0
    bad = []
    for wt in np.linspace(0, 1, 9):
        for wb in np.linspace(0, 1, 9):
            num, den = rational(wt, wb)
            f = np.array([50, 500, 5000.])
            s = 2j * np.pi * f
            Hr = np.polyval(num, s) / np.polyval(den, s)
            He = transfer(f, wt, wb)
            err = np.max(np.abs(db(Hr) - db(He)))
            worst = max(worst, err)
            b, a = sig.bilinear(num, den, 44100.0)
            pr = np.max(np.abs(np.roots(a)))
            worst_pr = max(worst_pr, pr)
            if pr >= 1.0 or err > 0.1:
                bad.append((wt, wb, err, pr))
    print(f"max |H_fit - H_mna| (audio pts) over 9x9 grid: {worst:.3e} dB")
    print(f"max digital pole radius over grid: {worst_pr:.6f}")
    if bad:
        print("cells needing attention (wt,wb,err_dB,pole_r):")
        for t in bad:
            print(f"  wt={t[0]:.3f} wb={t[1]:.3f} err={t[2]:.3e} pr={t[3]:.5f}")
    else:
        print("all 81 cells: in-band fit < 0.1 dB and stable")
