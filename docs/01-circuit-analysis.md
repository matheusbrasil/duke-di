# 01 - Circuit analysis (Noble DI / Nobelium)

White-box decomposition of the **Conspiracy to Commit Electronics "Nobelium"**
(a DIY clone of the **Noble Preamp DI**), from the user-supplied schematic and
BOM. The pedal is an all-tube, clean-focused bass preamp/DI: two 12AU7 triode
stages on a high internal rail, a passive interactive FMV tone stack
(Bass + Treble), a switchable low-cut, and a transformer-balanced XLR output.

The high-voltage rail (MOSFET-regulated ~250 V from a boost converter: M1
IRF740, U1 NE555, L1 100 uH, D1-D3) and the heater supply are **power**, not
audio. We model **only the audio path**. See `assumptions.md` for the safety
note on the HV section - do not probe it live.

## Stage decomposition

| # | Stage | Key parts (BOM) | Function | Corner / gain |
|---|-------|-----------------|----------|---------------|
| 0 | Input | R17 10M, C grid | 10 MΩ input Z, no loading | flat (piezo/passive friendly) |
| 1 | V1B gain | V1 12AU7, Rk 1k5, Rp(220k class), Ck | first triode, even-order curvature | small-signal ~16x, soft compress |
| 2 | Tone EQ | R13 47k, C6 270p, C10/C11 100n, BASS/TREBLE A250k, R21 2k7 | interactive FMV stack | 3rd-order, setting-dependent (see below) |
| 3 | Low-cut | ROLLOFF SPDT, C8 4n7 into R18 220k + wiper Zout | sub-bass control | treble-dependent **~82..154 Hz, -6 dB/oct** |
| 4 | V1A gain | V2/V1 12AU7 second triode | second stage, more curvature | interstage ~2.2x |
| 5 | Coupling | C7/C9/C10/C11 100n, VOLUME A250k | DC blocks + level | HPFs 3-10 Hz |
| 6 | White CF | V2 White cathode follower, D3 clamp | low-Z drive, grid clamp 0.6 V | HF/LF split ~34 Hz |
| 7 | Output HPF | C13 1u / output network | final DC block | ~4 Hz |
| 8 | DI xfmr | X1 JT-DB-EPC, R1 51R, C1 10n | balanced XLR, LF weight | LF core sat + HF rolloff |

### Corner-frequency arithmetic (f = 1 / (2*pi*R*C))

All linear corners are taken EXACTLY from the BOM and reproduced in
`reference/python/duke_ref.py`:

- **Tone stack (interactive FMV)**: `R13 47k` from the V1B plate to the mid
  node, `C6 270p` treble bleed from plate to the TREBLE top, `C10 100n` and
  `C11 100n` from the mid node to the Treble/Bass legs, TREBLE A250k wiper =
  output, BASS A250k as a rheostat, `R21 2k7` to ground. Solved exactly by
  nodal analysis in `reference/python/tonestack.py`; the transfer is a (3,3)
  rational H(s), discretised to a 3rd-order IIR and baked over a 9x9
  (treble,bass) grid. Bass and Treble interact and the stack has a
  setting-dependent insertion loss; noon is restored to ~unity by a fixed
  makeup gain (`TONE_MAKEUP`), so the knobs boost from noon.
- **Low-cut ~82..154 Hz (treble-dependent)**: the ROLLOFF switch inserts
  `C8 4n7` fed from the TREBLE wiper's output impedance `Zout(T)` in series
  with `R18 220k`: `fc = 1/(2*pi*(Zout+220k)*4n7)`, first order → -6 dB/oct.
- **Coupling DC blocks**: C9/C11 100n into 220k → `1/(2*pi*220k*100n) ≈ 7 Hz`;
  staged in the model at 3.18 / 4.02 / 9.5 Hz for the three successive nodes.
- **White CF split 33.9 Hz**: `1/(2*pi*CFHP)` - separates the clamp/even-order
  LF behavior from the linear pass-through above it.
- **Shared-rail sag 0.48 Hz**: V1A+V1B share `R24 1k5` bypassed by
  `C13 1u || C14 220u = 221 uF` → `1/(2*pi*1k5*221u) ≈ 0.48 Hz`; an envelope
  one-pole modelling the slow B+ droop that gives the gentle tube compression.

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
| Bass  | A250k log | 0..1 | FMV bass leg; noon≈flat (makeup), boosts lows from noon |
| Treble| A250k log | 0..1 | FMV treble leg; noon≈flat (makeup), boosts highs from noon |
| Volume/Level | A250k log | 0..1 | stock_vol curve; unity at knob 80, +3.5 dB at 100 |
| Low Cut (ROLLOFF) | SPDT | {0,1} | OFF = full range, ON = ~82..154 Hz -6 dB/oct |
| XFMR | selector | {0,1} | OFF = 1/4" out, ON = DI-transformer path |

**Gain** is a deliberate addition - the real circuit has no gain control (it is
a clean preamp). It scales the input into V1B so the player can dial in the
starved-tube compression/grit the fixed circuit only reaches at hot input
levels. It is a straight input scale (louder with more gain, as a preamp
should be), not a unity-compensated drive.

The interactive FMV tone stack and the switchable low-cut are the Noble's
actual tone topology, modeled node-for-node (not as independent shelves). With
the A250k log pots, noon maps to a wiper fraction ~0.15 where the stack is
nearly flat but heavily attenuated; a fixed `TONE_MAKEUP` restores ~unity so
the controls boost from noon - matching the pedal's "boost-only shelving" spec.
