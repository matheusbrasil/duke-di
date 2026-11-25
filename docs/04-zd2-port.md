# 04 - ZD2 port and real-time constraints

The Duke DI kernel targets the MS-60B+ C674x through the StompHacks cleanroom
ABI. Its effect identity is `0x0400A001` (PREAMP group), filename `MBDUKE`,
author prefix `MB`, and current version is **1.13**.

## Embedded design

Tier A is a desktop reference: it may evaluate Koren equations and solve the
FMV network using ordinary floating-point math. Tier B (`duke.c`) is the code
that runs on the pedal. It contains no divide, libm call, heap allocation, or
runtime coefficient solve.

| Reference operation | Pedal implementation |
|---|---|
| 12AU7 Koren transfer | 513-point precomputed table with linear interpolation |
| Input drive law | 33-point precomputed table |
| Interactive FMV tone stack | 9x9 Bass/Trble, seven-coefficient IIR grid |
| ROLLOFF corner | 17-step low-cut coefficient table |
| V1B nonlinearity | 2x causal interpolation and compact 20 kHz prefilter |
| V1A nonlinearity | 4x causal interpolation and four-biquad 18 kHz elliptic decimator |
| V2 White follower | calibrated clean 0.92 loss; no unsupported distortion model |

The oversampling split is deliberate. V1A is fed by the potentially boosted
FMV signal and needs the stronger anti-aliasing path. V1B is normally cleaner,
so 2x protects headroom without making the effect impractically expensive.

## State and safety

The manifest declares `state_bytes: 188`, including the local-oversampling and
filter delay states and the smoothed LoCut amount. This is within the 192-byte
firmware limit used by this effect. A guard word prevents processing before
state initialisation, and every output sample is finite/clamped before it
returns to the audio bus. If a channel produces a non-finite sample, its state
block is cleared so it recovers on the next sample instead of staying silent.

The kernel sits in `.text`, not the tiny `.audio` region. It has a stack frame
for local filter coefficient arrays, so the manifest intentionally uses
`allow_stack: true`; it still must make no external or RTS calls. Audit the
generated listing after every TI build:

```powershell
.\.venv\Scripts\python.exe .\tools\audit_text_dis.py `
  .\third_party\stomphacks\effects\duke\build\MBDUKE.text.dis `
  --sym DukeDI --allow-stack
```

## Parameters

The MS-60B+ pages five parameters over its four physical encoders:

| Parameter | Range/default | Port meaning |
|---|---|---|
| Input | 0..100 / 50 | Added virtual source level into V1B. |
| Bass | 0..100 / 0 | Capture-calibrated A250k Bass travel; 0 is the flat reference. |
| Trble | 0..100 / 0 | A250k Treble travel; 0 is the flat reference. |
| Level | 0..100 / 80 | 1/4-inch path final trim; 80 is unity. |
| LoCut | OFF/ON / OFF | Physical C8/R18 ROLLOFF network. |

There is no `OUT` or `XFMR` switch in v1.13. The final design models the
physical 1/4-inch path only; XLR balance, ground lift and Jensen transformer
behaviour are unavailable on the MS-60B+ output hardware.

## Build on Windows

`tools/stage_build.ps1` stages source/tables and the author record into the
vendored StompHacks clone. `tools/build_windows.ps1` builds from a temporary
path without spaces (a TI linker requirement), copies the generated artefacts
back, and replaces the packer's generic ZIC with the checked Duke icon.

```powershell
$env:ZOOM_TI_CGT = 'C:\path\to\ti-cgt-c6000_8.5.0.LTS'
.\tools\stage_build.ps1
.\tools\build_windows.ps1
```

Validate the ZD2 and companion icon before connecting a pedal:

```powershell
Push-Location .\third_party\stomphacks
.\.venv\Scripts\python.exe .\tools-pedal\install_selftest.py
.\.venv\Scripts\python.exe .\tools-pedal\pedal_diy.py classify .\effects\duke\build\MBDUKE.ZD2
Pop-Location
.\.venv\Scripts\python.exe .\tools\zic.py check .\third_party\stomphacks\effects\duke\build\MBDUKE.ZIC
```

`dspload: 128` is a conservative scheduler declaration. The pedal uses it for
admission control but does not measure cycles. It must not be reported as an
actual DSP percentage; only an independent hardware-cycle instrument could do
that.
