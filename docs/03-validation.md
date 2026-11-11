# 03 - Validation

Three independent checks back the model: **(A)** the Tier A reference against
circuit theory and the device model, **(B)** the shipped Tier B kernel against
Tier A (A/B, host-compiled), and **(C)** SPICE reference curves against the
analog stage. (C) needs ngspice/LTspice on your machine; (A) and (B) run here.

## A - Tier A reference (desktop golden model)

`reference/python/duke_ref.py` + `tube.py`. Validated characteristics:

- **Small-signal gain** ≈ 16.1x (matches the plan's ~16.4x expectation).
- **Even-order dominant**: H2 ~7 dB above H3 on a 110 Hz tone - the
  single-ended-triode signature.
- **THD** ~1.8% at nominal drive (clean preamp, not an overdrive).
- **EQ**: +12 dB boost-only shelves at exactly 150 Hz / 3.5 kHz.
- **Low-cut**: 90 Hz, -6 dB/oct.

Run: `python3 reference/python/duke_ref.py`.

## B - A/B: shipped kernel vs reference

The SAFE-DSP kernel `duke.c` is compiled **as portable C on the host** (no TI
toolchain needed) and driven through the exact same math the pedal runs, then
compared to Tier A.

```
python3 reference/python/bake_tables.py     # bake LUTs + host twin
bash   validation/build_host.sh             # gcc -> validation/host_duke
python3 validation/ab_test.py               # 7 checks
python3 validation/check_safe_dsp.py        # source SAFE-DSP lint
```

### Why this is characteristic-level, not a null test

Tier B is a deliberate **CPU-budget reduction** of Tier A (1x rate, LUT tube
map, compression-multiply sag). It is not meant to null against Tier A
sample-for-sample. The suite instead holds the kernel to tolerances that catch
a *broken* model while allowing the *intended* reductions.

### Pass/fail tolerances (and justification)

| ID | Check | Tolerance | Why this bound |
|----|-------|-----------|----------------|
| T1 | Broadband gain @ 1 kHz | within **1.5 dB** of Tier A | Audible level match; a wrong cascade gain or dead stage breaks it. |
| T2 | Magnitude 50 Hz..12 kHz | within **2.0 dB** | Filter corners/shapes must track; catches a mis-discretised section. |
| T3 | Even-order dominance | kernel **H2 ≥ 4 dB > H3** | The whole point of the voicing; a symmetric/dead nonlinearity fails. |
| T4 | Bass/Treble shelf | **≥ +4 dB** at the corner | Proves the baked shelf LUT and interp actually boost at 150 Hz / 3.5 kHz. |
| T5 | Low-cut @ 45 Hz | **≤ -4 dB** when ON | Proves the 90 Hz -6 dB/oct section engages. |
| T6 | Numerical safety | finite, **|y| < 8** (kernel clamp) | No divergence and no sample scrubbed to zero (no dropouts). |

Current status: **7/7 pass**. Measured headroom is large - T1 deviation
**+0.01 dB**, T2 worst **0.17 dB**, T3 margin **+13.5 dB** - so the reductions
cost far less than the tolerances allow.

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
- `tone_eq.cir` - the boost-only shelves + 90 Hz low-cut: AC Bode.
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
