# 04 - ZD2 port: embedded adaptation, packaging, and handover

The Duke DI kernel targets the Zoom MS-60B+ (C674x floating-point DSP) through
the community **stomphacks** cleanroom ABI (`third_party/stomphacks`). This doc
covers the embedded adaptation choices, how the `.ZD2` is built, and the one
step that cannot run in this build session.

## SAFE-DSP adaptation (what changed for the DSP)

The audio object links **no runtime library** and the C674x has **no divide
instruction**. Every expensive op was moved offline:

| Analog/Tier-A op | Embedded replacement | Error / cost |
|------------------|----------------------|--------------|
| Koren `exp/log` plate map | 513-pt LUT + linear interp (`tube_shape`) | interp error ≪ tube tolerance; A/B magnitude 0.17 dB |
| `pow` drive taper | 33-pt LUT (`drive_of`) | smooth log sweep, imperceptible steps |
| knob-dependent shelf `pow`/divide | 17-step {b0,b1,a1} LUT + interp (`shelf_of`) | identical curve to Tier A |
| `tanh` transformer sat | cubic `x - k*x^3` (`XF_SAT`) | matches first saturating term |
| per-section divide | precomputed reciprocal-step constants (`*_ISTEP`) | compile-time folded, zero runtime divides |

The LUTs ship as a **const_blob**: `tables.bin` (648 words / 2592 bytes) is
injected by the build into the symbol `duke_tables[]`, which the kernel reads
via `extern const unsigned int duke_tables[]`. Regenerate with
`python3 reference/python/bake_tables.py`.

### Real-time safety

- `processBlock`/`SH_AUDIO_FN`: **zero** heap allocation, no `new`/`malloc`,
  no `std::vector`, no `std::string` - all state lives in `instance[2]`.
- No statics; coefficients read into locals once, then range-checked.
- Mandatory **guard prologue** (verifies the init magic at state word
  `state_bytes/4`) and **per-sample output clamp** (`|y|<8` → 0) per the
  stomphacks `SAFETY.md`.
- State budget: kernel uses words 0..26 (108 B); manifest declares
  `state_bytes: 128` (≤ 188 B cleanroom limit), leaving the firmware guard
  word clear.
- Kernel placed in `.text` (`"kernel_section": "text"`) because the model
  exceeds the 1472-byte `.audio` budget; `.text` allows up to ~72 KB.

### UI (fits the MS-60B+ 4-knobs-per-page / short-label limits)

| Slot | Param | Range | Note |
|------|-------|-------|------|
| 5 | Gain  | 0..100 | added drive control |
| 6 | Bass  | 0..100 | +shelf @ 150 Hz |
| 7 | Treble| 0..100 | +shelf @ 3.5 kHz (label truncates to "Trebl") |
| 8 | Level | 0..100 | stock_vol curve, unity at 80 |
| 9 | LoCut | OFF/ON | 90 Hz low-cut |
| 10| XFMR  | OFF/ON | DI-transformer path |

Six params; the pedal pages them. All labels ≤ 5 chars except "Treble"
(cosmetic truncation only).

## Building the `.ZD2`

```
# 1. install TI C6000 Code Generation Tools 8.5.0 (provides cl6x)
#    https://www.ti.com/tool/C6000-CGT  (free, login required)
export ZOOM_TI_CGT=/path/to/ti-cgt-c6000_8.5.0.LTS

# 2. stage the effect where the tool can see it + tables.bin
cp embedded/effects/duke/* third_party/stomphacks/effects/duke/

# 3. build
cd third_party/stomphacks
python3 tools/zd2_make_effect.py effects/duke/manifest.json
#   -> effects/duke/XXDUKE.ZD2
```

The pipeline was run here up to this point: manifest validation **passes**,
`build/sh_params.h` is generated, and the only failure is the missing `cl6x`:

```
FileNotFoundError: .../ti-cgt-c6000_8.5.0.LTS/bin/cl6x
```

### Why the final blob is not in this session

`cl6x` is TI's proprietary C6000 compiler. It is not redistributable, requires
a TI account to download, and the build sandbox has no root to install it.
**Everything up to compilation is done and verified**; the remaining step is
mechanical once `cl6x` is on your `PATH`/`ZOOM_TI_CGT`.

## Effect id and filename

- `id: 05001000` - group byte `05` (bass category on the MS-60B+), low16
  `0x1000` = the **playground** range (own-pedal, never distributed). Requires
  `"allow_any_id": true`, which the manifest sets and documents.
- `filename: XXDUKE` - `XX` is the stomphacks playground prefix.
- If you ever distribute this, request an author range (`low16 ≥ 0x2000`) per
  `third_party/stomphacks/docs/id-scheme.md` and change both fields.

## Install / dry-run validation (after you have a blob)

stomphacks ships a mock-pedal self-test and a DIY classifier:

```
cd third_party/stomphacks
python3 tools-pedal/install_selftest.py effects/duke/XXDUKE.ZD2   # mock install
python3 tools-pedal/pedal_diy.py classify effects/duke/XXDUKE.ZD2 # name/id check
```

These require the built `.ZD2`, so they are part of the same handover. Run them
before copying to the pedal.

## DSP-budget warning (read before flashing)

- `dspload` is declared **60** (deliberately high) - the two LUT tube stages +
  seven TDF2 sections + interpolation are not free. **Measure the real cycle
  count on hardware** and keep a safety margin; the MS-60B+ shares the DSP with
  the rest of the patch.
- If it is too heavy: the cheapest wins are dropping the transformer section
  (selector already gates it) and halving the waveshaper table (513→257).
- 1x oversampling is a size/CPU choice; if hot treble aliases audibly, the
  documented fallback is 2x around the two tube stages (doubles their cost).

> The `.ZD2`/stomphacks formats are community-reverse-engineered. Field layouts
> can change; re-verify against the current stomphacks and `zoom-zt2` tooling
> before flashing, and keep a backup of your pedal's effect set.
