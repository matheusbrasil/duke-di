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
- **The finished-pedal manual, not an inferred pot law, defines the public
  control reference.** It says Bass/Treble are boost-only shelves with flat
  frequency response when both are fully counter-clockwise. The prior
  boost-from-noon interpretation is retired; the reference model applies a
  flat-setting makeup calibration while retaining the actual interactive
  A250k-network response away from that endpoint.
- **ROLLOFF follows C8/R18, not the conflicting commercial shorthand.** C8
  4n7 and R18 220k imply ~154 Hz before source loading. The embedded lookup
  calculates that source loading for every Bass/Trble combination.
- **Sag corner is 0.48 Hz, not 2.06 Hz.** V1A and V1B share one cathode
  network `R24 1k5` bypassed by `C13 1u || C14 220u = 221 uF`, so
  `fc = 1/(2*pi*1k5*221u) = 0.48 Hz`. `SAG_FC = 0.48` in `duke_ref.py`,
  baked into `SAG_A` in `duke_fixed.h`.

## Remaining component / topology assumptions

- **The DSP implements the 1/4" topology only.** V2A/V2B form the White
  cathode follower after V1A. XLR transformer colour was removed because the
  MS-60B+ has no balanced/isolated output and the distinction was inaudible.

- **Pot travel laws.** TREBLE remains the documented A250k exponential audio
  taper (~15% resistance at mid-rotation). BASS uses a separate monotone,
  capture-calibrated law: the [bassgyh Noble Preamp A2 captures on
  TONE3000](https://www.tone3000.com/tones/noble-preamp-104776) put its effective
  rheostat resistance at 2.17% around 9 o'clock and 5.88% at noon. This keeps
  the BOM-derived topology and maximum range while matching the measured
  control feel; it replaces the previous unmeasured shared 15%-at-noon law.
  The NAM captures are external comparison references only and are not stored
  or redistributed by this project.
- **Plate output impedance `PLATE_ZOUT = 7.4k`** (rp of a 12AU7 ~7.7k || R9
  220k) feeds the stack as its source resistance. The schematic has R15 1k5
  as a series grid stopper but no 1 Mohm V1A grid leak; `TONE_LOAD` is thus a
  numerically finite 1 Tohm only, rather than an invented shunt.
- **Low-cut loading needs a branch-aware reference calculation.** It is common
  to both paths, but its published control target is ~90 Hz; passive-wiper
  impedance is retained only as an internal circuit detail.
- **The Volume and XLR-level controls are different physical controls.** The
  panel Volume sets the 1/4" output; the rear XLR trim sets the balanced
  output. A digital `Level` control may map contextually to one or the other,
  but must not be presented as one common physical pot.

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

- **Local oversampling follows where distortion occurs.** V1B uses 2x with a
  compact 20-kHz prefilter because it is clean at nominal Input; V1A uses 4x
  and a 4-section elliptic decimator (18 kHz passband, >=60 dB at 22.05 kHz)
  because it receives the boosted FMV output. The previous 25-kHz decimator
  was above final Nyquist and is retired. V2 is modelled as clean follower
  loss until an isolated 1/4-inch capture constrains its nonlinearity.
- **Interpolated-IIR stability.** Bilinearly interpolating 3rd-order coeffs
  between grid nodes could in principle leave the stable region; `bake_tables.
  py` runs a gate sweeping every node AND 5x5 interpolated sub-cells, asserting
  max pole radius < 0.9999 (actual 0.99918).
- **Shared-cathode bias reduction.** Plate-current deltas from the Koren
  load-line LUT drive one R24/C13/C14 state shared by V1A/V1B. This captures
  the physical slow bias shift; grid current and heater-emission dynamics are
  still outside the embedded reduction.
- **The XLR transformer branch is intentionally absent.** A meaningful
  JT-DB-EPC model would need magnetic measurements and would still not create
  a balanced, isolated XLR output from the MS-60B+. The effect follows the
  complete 1/4-inch path instead.
- **Input control is an addition** to the real circuit and is a straight input
  scale, intentionally not a unity-compensated drive staging.

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
- **state_bytes 184** with the firmware guard at word 46. The additional state
  holds the causal 2x/4x interpolation history and the V1A decimator delays.

## Not done in this session (needs external tools)

- **Final `.ZD2`/`.ZIC` pair**: v1.12 builds with the installed TI CGT 8.5.0
  toolchain and was installed/read-back on an MS-60B+ firmware 1.20. Future
  source changes still require the complete build, audit and safety gates.
- **C674x asm audit**: SAFE-DSP checked at source level
  (`validation/check_safe_dsp.py`); the generated object needs the `cl6x`
  listing to confirm.
- **SPICE curves**: netlists shipped (`spice/`), but ngspice could not be
  installed here (no root). Run `spice/run_sweeps.sh` yourself.
- **Mock-pedal install self-test / DIY classify**: passed for the v1.12 build.
- **On-hardware DSP cycle measurement**: still required before interpreting
  `dspload` as anything more than conservative scheduler metadata.
