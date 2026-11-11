# 01 - Circuit analysis (Noble DI / Nobelium)

White-box decomposition of the **Conspiracy to Commit Electronics "Nobelium"**
(a DIY clone of the **Noble Preamp DI**), from the user-supplied schematic and
BOM. The pedal is an all-tube, clean-focused bass preamp/DI: two 12AU7 triode
stages on a high internal rail, a passive boost-only shelving EQ, a switchable
low-cut, and a transformer-balanced XLR output.

The high-voltage rail (MOSFET-regulated ~250 V from a boost converter: M1
IRF740, U1 NE555, L1 100 uH, D1-D3) and the heater supply are **power**, not
audio. We model **only the audio path**. See `assumptions.md` for the safety
note on the HV section - do not probe it live.

## Stage decomposition

| # | Stage | Key parts (BOM) | Function | Corner / gain |
|---|-------|-----------------|----------|---------------|
| 0 | Input | R17 10M, C grid | 10 MΩ input Z, no loading | flat (piezo/passive friendly) |
| 1 | V1B gain | V1 12AU7, Rk 1k5, Rp(220k class), Ck | first triode, even-order curvature | small-signal ~16x, soft compress |
| 2 | Tone EQ | BASS/TREBLE A250k, C4 1n5, C8 4n7, C3 100p | boost-only shelves | low shelf **150 Hz**, high shelf **3.5 kHz** |
| 3 | Low-cut | ROLLOFF SPDT, series C/R | sub-bass control | **90 Hz, -6 dB/oct** |
| 4 | V1A gain | V2/V1 12AU7 second triode | second stage, more curvature | interstage ~2.2x |
| 5 | Coupling | C7/C9/C10/C11 100n, VOLUME A250k | DC blocks + level | HPFs 3-10 Hz |
| 6 | White CF | V2 White cathode follower, D3 clamp | low-Z drive, grid clamp 0.6 V | HF/LF split ~34 Hz |
| 7 | Output HPF | C13 1u / output network | final DC block | ~4 Hz |
| 8 | DI xfmr | X1 JT-DB-EPC, R1 51R, C1 10n | balanced XLR, LF weight | LF core sat + HF rolloff |

### Corner-frequency arithmetic (f = 1 / (2*pi*R*C))

All linear corners are taken EXACTLY from the BOM and reproduced in
`reference/python/duke_ref.py`:

- **Bass low-shelf 150 Hz**: `1/(2*pi*10k*106n) ≈ 150 Hz` (A250k set to its
  boost end against the 1n5/4n7 network; modeled as a first-order low shelf).
- **Treble high-shelf 3.5 kHz**: `1/(2*pi*10k*4.5n) ≈ 3.5 kHz`.
- **Low-cut 90 Hz**: series `C ≈ 1/(2*pi*1M*90) ≈ 1.77 nF` into the grid-leak
  (1M R12/19/25), first order → -6 dB/oct, matching the spec.
- **Coupling DC blocks**: C9/C11 100n into 220k → `1/(2*pi*220k*100n) ≈ 7 Hz`;
  staged in the model at 3.18 / 4.02 / 9.5 Hz for the three successive nodes.
- **White CF split 33.9 Hz**: `1/(2*pi*CFHP)` - separates the clamp/even-order
  LF behavior from the linear pass-through above it.
- **Shared-rail sag 2.06 Hz**: envelope one-pole modelling the slow B+ droop
  that gives the preamp its gentle tube compression.

### Tube operating point (12AU7, starved heaters)

From `reference/python/tube.py` (Koren model + starved-heater derate
`STARVED_KG1_SCALE = 2.6`), the shared-rail DC operating point solves to:

```
Vk ≈ 2.41 V    Vp ≈ 73 V    Ip ≈ 0.8 mA    small-signal gain ≈ 16.1x
```

This matches the plan's expected ~16.4x and produces **even-order-dominant**
harmonics (H2 well above H3), the signature of a single-ended triode stage -
the "harmonic warmth" the Noble is known for.

## Control mapping

| Control | Taper | Normalised range | Mapping used |
|---------|-------|------------------|--------------|
| Gain (added) | — | 0..1 | drive = 0.25 * (9.0/0.25)^g (log sweep, baked LUT) |
| Bass  | A250k log | 0..1 | 0 = flat, 1 = +12 dB low shelf @ 150 Hz |
| Treble| A250k log | 0..1 | 0 = flat, 1 = +12 dB high shelf @ 3.5 kHz |
| Volume/Level | A250k log | 0..1 | stock_vol curve; unity at knob 80, +3.5 dB at 100 |
| Low Cut (ROLLOFF) | SPDT | {0,1} | OFF = full range, ON = 90 Hz -6 dB/oct |
| XFMR | selector | {0,1} | OFF = 1/4" out, ON = DI-transformer path |

**Gain** is a deliberate addition - the real circuit has no gain control (it is
a clean preamp). It scales the input into V1B so the player can dial in the
starved-tube compression/grit the fixed circuit only reaches at hot input
levels. It is a straight input scale (louder with more gain, as a preamp
should be), not a unity-compensated drive.

The boost-only EQ and the switchable low-cut are the Noble's actual tone
topology. Maximum shelf boost is provisionally **+12 dB** (see `assumptions.md`).
