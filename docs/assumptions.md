# Assumptions, open questions, and unverified items

Everything the model takes on faith, in one place. Items here are either
engineering choices with a stated rationale or gaps awaiting a measured unit.

## Settled from the schematic (previously assumed, now resolved)

These were open questions in Phase 1; reading `files/sch/audio_full.png`
resolved them, and the model now reflects the actual circuit.

- **EQ is ONE interactive passive FMV tone stack, not two independent
  boost-only shelves.** Topology (V1B plate P -> grid of V1A):
  `R13 47k: P-M`, `C6 270p: P-TREBLEtop`, `C10 100n: M-A`, `C11 100n: M-B`,
  TREBLE A250k wiper = output T (top via C6, bottom = A), BASS A250k wired as
  a rheostat A-B, `R21 2k7: B-GND`. Bass and Treble interact; the network has
  a setting-dependent insertion loss and a mid scoop. Modeled exactly by a
  nodal (MNA) solver in `reference/python/tonestack.py`, discretised to a
  3rd-order IIR, baked over a 9x9 (treble,bass) grid. The old
  `BASS_MAX_DB/TREBLE_MAX_DB` independent-shelf model is gone.
- **Noon is NOT flat.** With the A250k **log** pots, noon maps (A-taper, ~15%
  at mid-rotation) to a wiper fraction ~0.15, where the stack is nearly flat
  but heavily attenuated. A fixed makeup gain (`TONE_MAKEUP`, 1/|H(1k,noon)|)
  restores ~unity at noon, so the knobs act as **boost-from-noon** controls -
  which is what the pedal's "boost-only shelving" marketing describes.
- **ROLLOFF low-cut corner is TREBLE-dependent (~82..154 Hz), not a fixed
  90 Hz.** The switch inserts `C8 4n7` into `R18 220k`; the series source
  resistance is the TREBLE wiper's output impedance `Zout(T)`, so
  `fc = 1/(2*pi*(Zout+220k)*4n7)`. Zout rises with treble (0 -> ~154 Hz,
  ~190k at treble max -> ~83 Hz). Baked over a 17-step treble grid.
- **Sag corner is 0.48 Hz, not 2.06 Hz.** V1A and V1B share one cathode
  network `R24 1k5` bypassed by `C13 1u || C14 220u = 221 uF`, so
  `fc = 1/(2*pi*1k5*221u) = 0.48 Hz`. `SAG_FC = 0.48` in `duke_ref.py`,
  baked into `SAG_A` in `duke_fixed.h`.

## Remaining component / topology assumptions

- **A-taper pot law.** The A250k pots are log; the knob->wiper map uses an
  exponential audio taper giving ~15% resistance at mid-rotation
  (`tonestack.TAPER_K`). The exact taper of the specific pots is not measured;
  it affects knob *feel*, not the achievable EQ range.
- **Plate output impedance `PLATE_ZOUT = 7.4k`** (rp of a 12AU7 ~7.7k || R9
  220k) feeds the stack as its source resistance; **`TONE_LOAD = 1M`** models
  the grid-side load on the wiper. Both shift absolute level (folded into
  makeup/CAL), not the EQ shape materially.
- **Low-cut Zout uses bass at noon.** The 1-D low-cut grid is indexed by
  treble; the wiper Zout also depends weakly on bass, fixed at noon for the
  corner estimate. The dependence is treble-dominated.
- **VOLUME pot tone-loading** is folded to a constant (`CAL_VOL_NOM = 0.64`) in
  Tier B. Its rotation-dependent treble loss is a 2nd-order effect, omitted.

## Tube-model assumptions

- **Koren 12AU7 parameters** are the common published set, not a fit to a
  measured tube (`spice/12au7.lib`, `reference/python/tube.py`).
- **Starved-heater derate** `STARVED_KG1_SCALE = 2.6` is an engineering
  estimate of the transconductance loss from running the heaters cold.
- **Operating point** Vk≈2.41 V, Vp≈73 V, Ip≈0.8 mA is solved from the model,
  not measured.
- **Inter-stage absolute gains** (`CAL_INTERSTAGE`, `CAL_MAKEUP`, `TONE_MAKEUP`,
  `CAL_DRIVE_*`) are calibration constants fitted to keep the x16 cascade
  bounded and to match level, *not* derived node voltages. The *character*
  (curvature, asymmetry, even-order content) is exact from the device model;
  only the *level staging* is fitted.

## Modeling-choice assumptions (Tier B reductions)

- **1x oversampling (base rate).** Aliasing is now *measured* (A/B T7): worst
  in-band spur -32 dBc at a hot 7 kHz stress tone. Acceptable for bass-range
  program; 2x around the tube stages remains the documented fallback if a use
  case needs it. The tone stack runs at base rate so its low-frequency poles
  stay well away from z=1 (max digital pole radius 0.999 across the grid).
- **Interpolated-IIR stability.** Bilinearly interpolating 3rd-order coeffs
  between grid nodes could in principle leave the stable region; `bake_tables.
  py` runs a gate sweeping every node AND 5x5 interpolated sub-cells, asserting
  max pole radius < 0.9999 (actual 0.99918).
- **Sag as compression multiply** (not a bias shift). Preserves the slow
  0.48 Hz envelope and H2>H3; an exact bias-shift match was traded for cost.
- **Transformer = cubic soft-sat + 18 kHz rolloff.** Models LF core saturation
  and HF leakage; no hysteresis or frequency-dependent core loss.
- **Gain control is an addition** to the real circuit and is a straight input
  scale, intentionally not the unity-compensated ÷drive staging.

## Platform / build assumptions

- **Sample rate 44.1 kHz** per the stomphacks ABI note.
- **Effect id `0400A001`** uses group byte `04` = PREAMP on the MS-60B+ and
  low16 `0xA001` within the registered author range `0xA000..0xA03F`
  (nickname `matheusbrasil`, prefix `MB`, filename `MBDUKE`). `allow_any_id`
  stays **true**: the tool's id floor is a flat `idv < 0x07000F07`, and any
  MS-60B+ group byte < 07 trips it - this is a legitimate low-group id, not a
  playground id. The author entry lives in `ids/effect-authors.local.json`
  (tracked here) and is merged into the clone's ledger by `tools/stage_build.
  sh`, because the clone is gitignored and clobbered by re-clone.
- **state_bytes 128** with the firmware guard at word 32; the kernel uses 29
  words (two channels x 12-section blocks + 5 shared), 3 words of margin.

## Not done in this session (needs external tools)

- **Final `.ZD2` blob**: needs TI `cl6x` (proprietary, no root here). Pipeline
  verified up to the compile step. See `04-zd2-port.md`.
- **C674x asm audit**: SAFE-DSP checked at source level
  (`validation/check_safe_dsp.py`); the generated object needs the `cl6x`
  listing to confirm.
- **SPICE curves**: netlists shipped (`spice/`), but ngspice could not be
  installed here (no root). Run `spice/run_sweeps.sh` yourself.
- **Mock-pedal install self-test / DIY classify**: need the built blob.
- **On-hardware DSP cycle measurement**: mandatory before trusting `dspload`.
