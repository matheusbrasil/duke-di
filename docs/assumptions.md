# Assumptions, open questions, and unverified items

Everything the model takes on faith, in one place. Items here are either
engineering choices with a stated rationale or gaps awaiting the schematic
image / a measured unit.

## Component / topology assumptions

- **Max shelf boost = +12 dB** (Bass and Treble). The BOM gives A250k pots and
  the shelf caps but not the exact boost-network gain; +12 dB is a typical
  boost-only shelf depth and is provisional. Confirm against a SPICE sweep of
  the real network or a measured unit, then update `BASS_MAX_DB` /
  `TREBLE_MAX_DB` in `reference/python/duke_ref.py` and re-bake.
- **ROLLOFF switch wiring.** The 90 Hz, -6 dB/oct spec is modeled as a single
  first-order series-C high-pass. The exact switch nodes (what it inserts /
  bypasses) are not fully resolved from the BOM text; the behavior matches the
  published spec. Reconcile with the schematic image in the session `files/`
  folder and `spice/tone_eq.cir`.
- **Shelf corner realization.** 150 Hz / 3.5 kHz are exact from the spec; the
  R/C split used to realize them (10k node reference) is a behavioral choice,
  not a claim about the exact pot taper loading at every rotation.
- **VOLUME pot tone-loading** is folded to a constant (`CAL_VOL_NOM = 0.64`) in
  Tier B. Its rotation-dependent treble loss is a 2nd-order effect, omitted.

## Tube-model assumptions

- **Koren 12AU7 parameters** are the common published set, not a fit to a
  measured tube (`spice/12au7.lib`, `reference/python/tube.py`).
- **Starved-heater derate** `STARVED_KG1_SCALE = 2.6` is an engineering
  estimate of the transconductance loss from running the heaters cold; it was
  chosen so the DC operating point and ~16x gain land where the plan expects.
  A measured starved 12AU7 curve would refine it.
- **Operating point** Vk≈2.41 V, Vp≈73 V, Ip≈0.8 mA is solved from the model,
  not measured.
- **Inter-stage absolute gains** (`CAL_INTERSTAGE`, `CAL_MAKEUP`,
  `CAL_DRIVE_*`) are calibration constants fitted to keep the x16 cascade
  bounded and to match level, *not* derived node voltages. The *character*
  (curvature, asymmetry, even-order content) is exact from the device model;
  only the *level staging* is fitted. `CAL_MAKEUP = 1.14` in `duke.c` was set
  so Tier B matches Tier A's output level (A/B T1 within 0.01 dB).

## Modeling-choice assumptions (Tier B reductions)

- **1x oversampling.** Aliasing was reasoned to be low for this soft,
  even-order, bass-centric nonlinearity but was **not** yet measured with a
  dedicated alias test. 2x around the tube stages is the documented fallback.
- **Sag as compression multiply** (not a bias shift). Preserves the slow 2.06 Hz
  envelope and H2>H3; an exact bias-shift match was traded for cost.
- **Transformer = cubic soft-sat + 18 kHz rolloff.** Models LF core saturation
  and HF leakage; it does not model hysteresis or frequency-dependent core loss.
- **Gain control is an addition** to the real circuit and is a straight input
  scale (gets louder with more drive), intentionally not the unity-compensated
  ÷drive staging.

## Platform / build assumptions

- **Sample rate 44.1 kHz** per the stomphacks ABI note (stock DELAY_C uses
  `samples = ms*441/10`).
- **Effect id `05001000`** assumes group byte `05` = the bass category on the
  MS-60B+ and uses the playground low16 `0x1000` with `allow_any_id`. Verify
  the group byte for your firmware's browser category; change it (and the
  filename prefix) before any distribution.
- **state_bytes 128** assumes the firmware guard sits at `state_bytes/4` just
  past the kernel's region, inside the ≥192-byte scratch - consistent with the
  generated `sh_params.h` (`SH_STATE_GUARD_WORD = 32`).

## Not done in this session (needs external tools)

- **Final `.ZD2` blob**: needs TI `cl6x` (proprietary, no root here). Pipeline
  verified up to the compile step. See `04-zd2-port.md`.
- **C674x asm audit**: the SAFE-DSP guarantee is checked at source level
  (`validation/check_safe_dsp.py`); confirming the *generated* object divides/
  calls nothing needs the `cl6x` listing.
- **SPICE curves**: netlists shipped (`spice/`), but ngspice/libngspice could
  not be installed here (no root). Run `spice/run_sweeps.sh` yourself.
- **Mock-pedal install self-test / DIY classify**: need the built blob.
- **On-hardware DSP cycle measurement**: mandatory before trusting `dspload`.
