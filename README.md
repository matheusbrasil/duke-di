# Duke DI

A white-box digital model of the **Noble Preamp DI** (an all-tube, clean bass
preamp/DI), packaged as a Zoom **MS-60B+** `.ZD2` effect. Built from the
user-supplied **Conspiracy to Commit Electronics "Nobelium"** DIY clone
schematic and BOM.

*"Duke"* is a nobility-pun homage - no trademark, fits the pedal's short
display.

## What it models

Two **12AU7** triode stages on a high internal rail, a passive **boost-only
shelving EQ** (bass 150 Hz, treble 3.5 kHz), a switchable **90 Hz low-cut**
(-6 dB/oct), a **White cathode follower**, and an optional **JT-DB-EPC DI
transformer** path. Clean, high-headroom, **even-order** voiced - the Noble's
"harmonic warmth and natural compression without heavy overdrive".

Controls: **Gain** (added), **Bass**, **Treble**, **Level**, **LoCut**
(OFF/ON), **XFMR** (OFF/ON).

## Two-tier design

- **Tier A - golden reference** (`reference/python/`): oversampled, full Koren
  tube model, division/`exp`/`log` allowed. The yardstick. Emits the LUTs.
- **Tier B - embedded kernel** (`embedded/effects/duke/duke.c`): SAFE-DSP C for
  the C674x - **no divide, no libm, no allocation**. Every nonlinearity is a
  precomputed LUT (`tables.bin`) the kernel interpolates.

Tier B is validated against Tier A: **7/7** characteristic checks pass (gain
match **0.01 dB**, response within **0.17 dB**, even-order margin **+13.5 dB**).

## Layout

```
reference/python/   duke_ref.py (Tier A), tube.py (12AU7), bake_tables.py (LUTs)
embedded/effects/duke/
    duke.c          the SAFE-DSP kernel
    approx.h        divide/call-free LUT helpers
    duke_fixed.h    generated fixed-section coeffs
    tables_layout.h const-blob layout (single source of truth)
    tables.bin      baked LUTs (const_blob)  |  tables_data.c  host twin
    manifest.json   stomphacks build manifest
validation/         host harness (host_main.c, build_host.sh), ab_test.py,
                    check_safe_dsp.py
spice/              12au7.lib, gain_stage.cir, tone_eq.cir, run_sweeps.sh
docs/               01 circuit, 02 discretization, 03 validation, 04 zd2 port,
                    assumptions
tools/              check_env.py (toolchain gate)
```

## Reproduce the validation (no special toolchain)

```
pip install numpy scipy            # if not present
python3 reference/python/bake_tables.py     # bake LUTs + host twin
bash    validation/build_host.sh            # gcc -> validation/host_duke
python3 validation/ab_test.py               # 7/7 expected
python3 validation/check_safe_dsp.py        # SAFE-DSP source lint
python3 reference/python/duke_ref.py        # Tier A character report
```

## Build the flashable `.ZD2` (needs TI cl6x)

The one step this repo cannot run itself: the final blob needs TI's proprietary
**C6000 CGT 8.5.0** (`cl6x`). Everything up to it is done and verified
(manifest validates, `sh_params.h` generates). See
[`docs/04-zd2-port.md`](docs/04-zd2-port.md):

```
export ZOOM_TI_CGT=/path/to/ti-cgt-c6000_8.5.0.LTS
cp embedded/effects/duke/* third_party/stomphacks/effects/duke/
cd third_party/stomphacks && python3 tools/zd2_make_effect.py effects/duke/manifest.json
```

## Status

| Deliverable | State |
|-------------|-------|
| Tier A reference + tube model | done, validated |
| LUT baking (`tables.bin`) | done |
| Tier B SAFE-DSP kernel | done, host-compiled, 7/7 A/B pass |
| SAFE-DSP source lint | passing |
| Build manifest | validates against stomphacks |
| SPICE netlists | shipped (run on your ngspice/LTspice) |
| Docs (circuit → port) | done |
| Final `.ZD2` blob | **handover**: needs `cl6x` |
| On-hardware cycle check | **handover**: measure before flashing |

## Safety

The real pedal contains a **~250 V** HV rail (boost converter). This project
models **only the audio path**. Do not probe the live HV section. See
[`docs/assumptions.md`](docs/assumptions.md).

Community-reverse-engineered `.ZD2`/stomphacks formats: re-verify against
current tooling and back up your pedal before flashing.

---
Built on the [stomphacks](https://github.com/thammer) cleanroom ABI. MIT.
