# 01 - Circuit analysis (Noble DI / Nobelium)

White-box decomposition of the **Conspiracy to Commit Electronics "Nobelium"**
(a DIY clone of the **Noble Preamp DI**), from the user-supplied schematic and
BOM. The pedal is an all-tube, clean-focused bass preamp/DI: two 12AU7 triode
stages on a high internal rail, a passive interactive FMV tone stack
(Bass + Treble), a switchable low-cut, and a transformer-balanced XLR output.
The transformer-balanced branch is documented as physical-circuit context only;
it is not emulated by this MS-60B+ effect.

The high-voltage rail (MOSFET-regulated ~250 V from a boost converter: M1
IRF740, U1 NE555, L1 100 uH, D1-D3) and the heater supply are **power**, not
audio. We model **only the audio path**. See `assumptions.md` for the safety
note on the HV section - do not probe it live.

## Implemented output topology

The physical Nobelium has independently switchable outputs. The MS-60B+ build
intentionally implements only the complete **1/4-inch PREAMP** path, because
the pedal cannot reproduce XLR balance, isolation or ground lift:

```
V1B -> FMV tone stack -> ROLLOFF -> V1A -> V2A/V2B White follower -> C12/R22 -> 1/4"
```

V1B and V1A are the gain stages of the first 12AU7; V2A/V2B are the 1/4"
output buffer. This is the single path exposed by the DSP effect.

## Stage decomposition

| # | Stage | Key parts (BOM) | Function | Corner / gain |
|---|-------|-----------------|----------|---------------|
| 0 | Input | R14 1k5, R17 10M | 10 MΩ input Z, grid stopper | flat (piezo/passive friendly) |
| 1 | V1B gain | V1B 12AU7, R24 1k5, R9 220k, C13/C14 | first triode, even-order curvature | small-signal ~16x, soft compress |
| 2 | Tone EQ | R13 47k, C6 270p, C10/C11 100n, BASS/TREBLE A250k, R21 2k7 | interactive FMV stack | 3rd-order, setting-dependent (see below) |
| 3 | Low-cut | ROLLOFF SPDT, C8 4n7 into R18 220k | common sub-bass control | nominal ~90 Hz, -6 dB/oct |
| 4 | V1A gain | V1A 12AU7, R10 220k | second V1 triode, more curvature | interstage ~2.2x |
| 5 | 1/4" branch | V2A/V2B White follower, D3 clamp, C12 2u2, R22 18k | low-Z instrument output | final HPF ~4 Hz; clean follower loss in DSP pending an isolated 1/4" capture |

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
  setting-dependent insertion loss.  The finished-pedal manual specifies the
  fully counter-clockwise Bass/Treble position as the flat-response reference;
  the control mapping must be calibrated to that statement, not to noon.
- **Low-cut / ROLLOFF**: C8 4n7 and R18 220k give a nominal 154 Hz pole before
  wiper loading. The published “~90 Hz” claim conflicts with the BOM; this
  implementation follows the circuit and calculates the C8/R18 corner from
  the tone-stack wiper impedance for each Bass/Trble setting.
- **1/4" output HPF**: `C12 2u2` into `R22 18k` gives
  `1/(2*pi*18k*2.2u) ≈ 4 Hz`.  C13 (1u) is part of the shared cathode bypass,
  not an output coupling capacitor.
- **White CF split 33.9 Hz**: `1/(2*pi*CFHP)` - separates the clamp/even-order
  LF behavior from the linear pass-through above it.  This belongs only to
  the 1/4" branch.
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
| Input (added) | — | 0..1 | virtual instrument source level into V1B; nominal near midpoint |
| Bass  | A250k log | 0..1 | FMV bass leg; 0 is the finished-pedal flat reference, then boost |
| Treble| A250k log | 0..1 | FMV treble leg; 0 is the finished-pedal flat reference, then boost |
| Level | stock volume curve | 0..1 | 1/4" VOLUME-path output trim; 80 is unity |
| LoCut (ROLLOFF) | SPDT | {0,1} | OFF = direct stack; ON = physical C8/R18 network |

**Input** is a deliberate addition - the real circuit has no front-panel gain
control. It scales the virtual source entering V1B, so passive and active
instruments can be calibrated without pretending that the Nobelium has a gain
knob. It is not a unity-compensated drive control.

The interactive FMV tone stack and the switchable low-cut are the Nobelium's
actual topology, modeled node-for-node (not as independent shelves). The
published finished-pedal manual is the authority for the player-facing control
law: Bass and Treble are boost-only relative to their fully
counter-clockwise flat position.
