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
| LOWCUT (90 Hz) | 90.0  | 0.9936293 | -0.9872587 |
| DC1  (9.5 Hz)  | 9.5   | 0.9993237 | -0.9986474 |
| DC2  (3.18 Hz) | 3.18  | 0.9997735 | -0.9995470 |
| CFHP (33.9 Hz) | 33.9  | 0.9975908 | -0.9951817 |
| OUTHP (4.02 Hz)| 4.02  | 0.9997137 | -0.9994274 |
| XFHP (18 kHz split) | — | 0.9957439 | -0.9914878 |

(`b1 = -b0` for every high-pass.)

### First-order shelves (Bass 150 Hz, Treble 3.5 kHz)

Boost-only. Low shelf `H(s) = (s + A*wc)/(s + wc)`, high shelf
`H(s) = (A*s + wc)/(s + wc)`, with `A = 10^(gain_dB/20)`. Discretised with
`scipy.signal.bilinear`. Because the gain `A` depends on the knob, these
**cannot** be evaluated in the kernel (no `pow`, no divide). Instead
`bake_tables.py` samples `{b0,b1,a1}` at **17 knob steps** (0..1) into
`duke_tables[]`; the kernel linearly interpolates between steps
(`approx.h: shelf_of`). The two tiers therefore use the identical shelf curve.

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
- **Shelf coeffs**: 17 steps x 3 coeffs x 2 shelves (above).

Between the baked samples the kernel does linear interpolation only
(multiply + add + float↔int convert). This is the core SAFE-DSP trade: all
transcendental/divide work moves offline into `tables.bin`.

## Sag / compression

Shared-rail droop is a one-pole envelope on `|u|` at **2.06 Hz**
(`SAG_A = 0.9997065`, `y += (1-a)*(|x|-y)`).
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
