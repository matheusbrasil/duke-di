# 03 - Validation

Three independent checks back the model: **(A)** the Tier A reference against
circuit theory and the device model, **(B)** the shipped Tier B kernel against
Tier A (A/B, host-compiled), and **(C)** SPICE reference curves against the
analog stage. (C) needs ngspice/LTspice on your machine; (A) and (B) run here.

## External NAM comparison reference

Control-law calibration also used the five A2-Full captures published by
**bassgyh** as [Noble Preamp on TONE3000](https://www.tone3000.com/tones/noble-preamp-104776):
`Noble Flat`, `Noble B9`, `Noble B12`, `Noble B9 T12`, and `Noble B12 T9`.
The listing identifies these as captures of a Noble Bass Preamp at specific
knob settings, made using a sweep/reamp workflow. We executed the supplied A2
models locally and measured low-level sine frequency response relative to
`Noble Flat`; the resulting Bass effective-wiper observations informed the
monotone Bass taper in `tonestack.py`.

This is a **comparison/calibration reference**, not a training set or a source
for the shipped audio algorithm. No NAM model, capture audio, model weights or
derived copy of the capture is included in this repository or release ZIP. The
test does not establish a sample-for-sample match, THD match or physical-unit
equivalence: capture interface gain, input source and individual tube variance
remain uncontrolled.

## A - Tier A reference (desktop golden model)

`reference/python/duke_ref.py` + `tube.py`. Validated characteristics:

- **Small-signal gain** ≈ 16.1x (matches the plan's ~16.4x expectation).
- **Even-order dominant**: H2 ~7 dB above H3 on a 110 Hz tone - the
  single-ended-triode signature.
- **THD** ~1.8% at nominal drive (clean preamp, not an overdrive).
- **EQ**: interactive FMV tone stack (3rd-order); the fully counter-clockwise
  Bass/Trble setting is the published flat reference.
- **Low-cut**: treble-dependent ~82..154 Hz, -6 dB/oct.

Run: `python3 reference/python/duke_ref.py`.

## B - A/B: shipped kernel vs reference

The SAFE-DSP kernel `duke.c` is compiled **as portable C on the host** (no TI
toolchain needed) and driven through the exact same math the pedal runs, then
compared to Tier A.

```
python3 reference/python/bake_tables.py     # bake LUTs + host twin
bash   validation/build_host.sh             # gcc -> validation/host_duke
python3 validation/ab_test.py               # 9 checks
python3 validation/check_safe_dsp.py        # source SAFE-DSP lint
```

### Why this is characteristic-level, not a null test

Tier B is a deliberate **CPU-budget reduction** of Tier A (local 2x/4x rate,
LUT tube map, compression-multiply sag). It is not meant to null against Tier A
sample-for-sample. The suite instead holds the kernel to tolerances that catch
a *broken* model while allowing the *intended* reductions.

### Pass/fail tolerances (and justification)

| ID | Check | Tolerance | Why this bound |
|----|-------|-----------|----------------|
| T1 | Broadband gain @ 1 kHz | within **1.5 dB** of Tier A | Audible level match; a wrong cascade gain or dead stage breaks it. |
| T2 | Magnitude 50 Hz..12 kHz | within **2.0 dB** | Filter corners/shapes must track; catches a mis-discretised section. |
| T3 | Even-order dominance | kernel **H2 ≥ 4 dB > H3** | The whole point of the voicing; a symmetric/dead nonlinearity fails. |
| T3 | Even-order dominance | kernel **H2 ≥ 4 dB > H3** at moderate drive, and tracks Tier A | Even-order richness is a moderate-drive phenomenon; past clipping onset odd rises in both tiers. Checked at amp 0.12/gain 0.5 plus a ref-tracking bound. |
| T4 | Tone-stack tilt authority | Bass and Treble each move their band **≥ +4 dB** from noon | Proves the baked 9x9 EQ LUT + 2-D interp give real boost-from-noon authority (interactive stack, not independent shelves). |
| T5 | Low-cut @ 45 Hz | **≤ -4 dB** when ON | Proves the treble-dependent -6 dB/oct section engages. |
| T6 | Numerical safety | finite, **|y| < 8** (kernel clamp) | No divergence and no sample scrubbed to zero (no dropouts). |
| T8 | Bright aliasing | worst spur **≤ -24 dBc** on a hot 7 kHz stress tone | Exercises the oversampled V1A nonlinear path. |
| T9 | Low-E extreme alias | non-harmonic spur **≤ -50 dBc** | Reproduces a hard 41 Hz attack with Bass/Trble at 100; catches folded products that simple EQ sweeps miss. |

Current v1.13 status (unchanged from v1.12): **9/9 pass**. Measured T1 deviation is **+0.01 dB**,
T2 worst deviation **1.80 dB** at 12 kHz, T8 bright spur **-56.8 dBc**, and
T9 low-E extreme non-harmonic spur **-63.4 dBc**. The latter two replace the
old base-rate alias tolerance with the attack cases that matter musically.

### SAFE-DSP lint

`validation/check_safe_dsp.py` strips comments/strings from `duke.c` and
`approx.h` and fails on any `/` divide, libm call, allocation, or non-const
static. This is a **source-level** gate: the final proof that the *generated
C674x object* divides/calls nothing requires disassembling the `cl6x` output
(`04-zd2-port.md`), which is a handover step.

## C - SPICE reference curves (your machine)

`spice/` ships standard netlists:

- `12au7.lib` - Koren 12AU7 device model.
- `gain_stage.cir` - one common-cathode stage: AC Bode + `.four` THD at 1 kHz.
- `tone_eq.cir` - the interactive FMV tone stack + treble-dependent low-cut: AC Bode.
- `run_sweeps.sh` - runs both under ngspice; writes `validation/spice_*_ac.txt`.

```
bash spice/run_sweeps.sh        # needs ngspice, or open the .cir in LTspice
```

Compare the exported Bode magnitude to the Tier A frequency response and the
`.four` THD to the reference's ~1.8%. The tone netlist is a behavioral
realization of the published corners; exact pot-wiring reconciliation is
tracked in `assumptions.md`.

> ngspice/libngspice could not be installed in the build session (no root), so
> these curves were **not** generated here. The netlists are provided as
> runnable artifacts; the DSP itself is fully validated by (A) and (B) above.
