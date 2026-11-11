# 02 - Discretization

Every linear section is discretised with the **bilinear (Tustin) transform**
with prewarping at the section corner. The two tiers share the same corner
frequencies; they differ only in sample rate (Tier A oversamples 8x, Tier B
runs at base 44.1 kHz) and in how the nonlinearities are evaluated.

## Bilinear transform

```
s  <-  (2/T) * (z - 1)/(z + 1)        T = 1/fs
```

With frequency prewarping so the analog corner lands exactly on the digital
corner:

```
wc = (2/T) * tan(pi * fc / fs)
```

### First-order high-pass (DC blocks, low-cut, CF/xfmr splits)

Analog `H(s) = s / (s + wc)`. Bilinear →

```
       1 - z^-1                         k - wc
H(z) = k * ----------- ,  with  a1 = -(---------)  , k = 2*fs
         k + wc - ... (normalised)      k + wc

b0 =  k/(k+wc)      b1 = -k/(k+wc)      a1 = (wc-k)/(k+wc)
```

Realised as one transposed-direct-form-II (TDF2) section:

```
y[n] = b0*x[n] + z[n]
z[n] = b1*x[n] - a1*y[n]
```

The baked coefficients (`embedded/effects/duke/duke_fixed.h`, from
`bake_tables.py`) for the fixed sections:

| Section | fc (Hz) | b0 | a1 |
|---------|---------|----|----|
| DC1  (9.5 Hz)  | 9.5   | 0.9993237 | -0.9986474 |
| DC2  (3.18 Hz) | 3.18  | 0.9997735 | -0.9995470 |
| CFHP (33.9 Hz) | 33.9  | 0.9975908 | -0.9951817 |
| OUTHP (4.02 Hz)| 4.02  | 0.9997137 | -0.9994274 |
| XFHP (18 kHz split) | — | 0.9957439 | -0.9914878 |

(`b1 = -b0` for every high-pass.)

### Interactive FMV tone stack (3rd-order, Bass + Treble)

The tone stack is a passive FMV network (see `01-circuit-analysis.md`), so its
transfer is an exact **(3,3) rational** `H(s)` whose coefficients depend on
*both* knob positions. `reference/python/tonestack.py` solves the network by
nodal analysis (MNA) at a set of frequencies and identifies `H(s)` by
least-squares. A naive wide-frequency sweep is ill-conditioned (huge dynamic
range in the `s^k` columns, and a near-degenerate MHz pole at the pot ends that
turns into a spurious unstable pole after bilinear). The fix: **sample on
circles** `|s| = w0` (w0 = 2*pi*1000) at several complex angles and two radii,
normalise the columns by `w0^k`, solve, then rescale the coefficients by
`w0^k`. This recovers `H(s)` to 1.9e-4 dB and keeps every pole in the LHP.

`H(s)` is discretised with `scipy.signal.bilinear` to a 3rd-order IIR. Because
the coefficients depend on the knobs (and the kernel has no `pow`/divide),
`bake_tables.py` evaluates the 7 coefficients `{b0,b1,b2,b3,a1,a2,a3}` on a
**9x9 (treble,bass) grid** into `duke_tables[]`; the kernel does 2-D bilinear
interpolation (`approx.h: eq_of`) and runs one 3rd-order TDF2 section
(`duke.c: df3`). The fixed `TONE_MAKEUP` is folded into the baked numerator so
noon lands at ~unity.

A stability gate in `bake_tables.py` sweeps every grid node **and** 5x5
bilinearly-interpolated sub-cells (exactly what `eq_of` produces between nodes),
asserting max digital pole radius < 0.9999 (actual 0.99918).

### Low-cut (treble-dependent, baked over 17 steps)

First-order high-pass `H(s) = s/(s+wc)` with `wc = 2*pi*fc`,
`fc = 1/(2*pi*(Zout(T)+220k)*4n7)`. Because `Zout` tracks the TREBLE wiper,
`bake_tables.py` samples `{b0,b1,a1}` at **17 treble steps** into the blob;
the kernel interpolates with `approx.h: lowcut_of`.

### Transformer low-pass (XFLP, HF leakage rolloff)

Analog `H(s) = wc/(s + wc)` at ~18 kHz. Bilinear →
`b0 = b1 = wc/(k+wc)`, `a1 = (wc-k)/(k+wc)`. Baked:
`XFLP_B0 = XFLP_B1 = 0.5618422`, `XFLP_A1 = 0.1236844`.

## Nonlinearities (baked, not solved, in Tier B)

The C674x cannot run the Koren `exp/log` plate map or a per-sample Newton
solve. Each nonlinear transfer is precomputed once on the desktop and shipped
as a LUT:

- **12AU7 waveshaper**: the Koren static plate map, normalised to unity
  small-signal gain, sampled at **513 points** over `[-8, +8]`
  (`tube_shape`, LUT `OFF_WS`). Index `= (u + 8) * WS_ISTEP`, `WS_ISTEP` a
  compile-time constant (no divide).
- **Gain drive taper**: `0.25*(36)^g`, **33 points** (`drive_of`, `OFF_DRV`).
- **EQ coeffs**: 9x9 grid x 7 coeffs (FMV stack, above).
- **Low-cut coeffs**: 17 treble steps x 3 coeffs (above).

Between the baked samples the kernel does linear interpolation only
(multiply + add + float↔int convert). This is the core SAFE-DSP trade: all
transcendental/divide work moves offline into `tables.bin`.

## Sag / compression

Shared-rail droop is a one-pole envelope on `|u|` at **0.48 Hz**
(`SAG_A` from `SAG_FC=0.48`, `y += (1-a)*(|x|-y)`).
- **Tier A** shifts the cathode bias `vk += 0.6*sag` (moves the operating
  point, re-curving the waveshaper).
- **Tier B** applies it as a gentle output compression `w * (1 - 0.15*sag)` -
  cheaper, same perceptual "breathing", validated to preserve even-order
  dominance (`validation/ab_test.py` T3).

## Tier B reductions (vs Tier A), and why they are safe

| Item | Tier A | Tier B | Justification |
|------|--------|--------|---------------|
| Oversampling | 8x | 1x | Aliasing risk measured small for this soft, mostly even-order nonlinearity at bass frequencies; 2x is the documented fallback if a hot treble transient aliases audibly. |
| Tube map | Koren exp/log per sample | 513-pt LUT + lerp | Interp error << device tolerance; A/B magnitude within 0.17 dB. |
| Sag | vk bias shift | compression multiply | Same slow envelope; H2>H3 preserved. |
| VOLUME loading | modeled node | constant `CAL_VOL_NOM=0.64` | Tone-loading effect is 2nd order; folded to a constant. |
| Transformer | tanh LF sat + 18 kHz | cubic soft-sat + 18 kHz | No `tanh`; cubic matches the first saturating term. |

See `03-validation.md` for how each reduction is held to a numeric tolerance.
