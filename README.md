# Duke DI

**Duke DI** is a white-box digital model of the 1/4-inch preamp path of the
Conspiracy to Commit Electronics **Nobelium** (a Noble Preamp DI-inspired,
12AU7 bass preamp), packaged as a custom effect for the Zoom **MS-60B+**.
It is not affiliated with Noble or C2CE.

The model is grounded in the supplied Nobelium schematic/BOM, then calibrated
where possible against independent Noble NAM A2 captures. It deliberately
models the complete unbalanced 1/4-inch path, not an imagined XLR transformer
emulation: the MS-60B+ has neither a balanced output nor transformer isolation.

## What is in v1.14

- Declared DSP load lowered from 128 to 100, based on an on-pedal cycle
  measurement (`docs/07-cycle-probe.md`): about 14,060 cycles per call on
  average and about 19,950 in the worst call, i.e. roughly 61 and 87 load
  units. This frees budget for other effects in the same chain. The audio
  kernel is unchanged from v1.13.
- v1.13 robustness update over v1.12, same sound: a channel whose output turns
  non-finite clears its filter state and recovers on the next sample; the
  LoCut switch fades instead of stepping; a NaN table index is clamped to the
  table instead of reading outside it. State grows from 184 to 188 bytes.
- Two Koren-model 12AU7 gain stages, a passive interactive FMV tone stack,
  Nobelium ROLLOFF low-cut, shared-cathode sag, and the clean V2 White-follower
  loss of the 1/4-inch output path.
- Local anti-aliased nonlinear processing: 2x for V1B and 4x for V1A. The
  latter has a four-section elliptic decimator designed below the 22.05 kHz
  final Nyquist limit.
- Bass taper calibrated from the supplied NAM captures; Treble remains based
  on the documented A250k law. The controls are interactive rather than
  independent digital shelves.
- A native 1-bit dark MS+ icon, with a 12AU7 symbol, `DUKE DI` wordmark, and
  standard 72x97/102x128 frames.

## Controls

| Control | Practical meaning |
|---|---|
| **Input** | Virtual source level into V1B. 50 is the nominal passive-instrument setting; it is an added digital control, not a Nobelium panel control. |
| **Bass** | Boost-only Nobelium Bass control. 0 is the documented flat reference; 50 is approximately the physical noon response. |
| **Trble** | Boost-only Nobelium Treble control. 0 is the flat reference; high values intentionally reveal upstream hiss/noise. |
| **Level** | Final 1/4-inch output trim. 80 is unity, 100 is approximately +3.5 dB. It does not create distortion or hiss internally. |
| **LoCut** | Nobelium ROLLOFF network (`C8`/`R18`). ON tightens sub-bass and reduces boom without being a generic EQ switch. |

Suggested neutral starting point for a passive P bass: `Input 50`, `Bass 0`,
`Trble 0`, `Level 80`, `LoCut OFF`. Keep Treble below maximum unless a strong
presence lift is specifically wanted: it raises any noise already present in
the bass/interface chain.

## Evidence and limits

The NAM analysis is real: the A2 models from [bassgyh's Noble Preamp capture
set on TONE3000](https://www.tone3000.com/tones/noble-preamp-104776) were
executed and their small-signal frequency responses measured. The host A/B
tests are real too, but compare the embedded kernel with this repository's
Tier-A circuit reference; they are not a sample-for-sample NAM null test and
are not a laboratory measurement of a physical Nobelium. The NAM files are
comparison references only: they are neither embedded, trained on, nor
redistributed by this project. See [`docs/03-validation.md`](docs/03-validation.md)
and [`docs/assumptions.md`](docs/assumptions.md) for the boundary of each claim.

## Project layout

```text
reference/python/        Tier-A Koren/MNA reference and table baker
embedded/effects/duke/   C674x SAFE-DSP kernel, manifest, tables, icon source
validation/              host build and 9-point characteristic test suite
spice/                   runnable 12AU7/tone-stack reference netlists
tools/                   staging, Windows build, ZIC generation and checks
docs/                    circuit, discretization, validation and pedal runbooks
```

## Windows: validate, build, and install

The repository contains the tested PowerShell workflow for Python 3.11 and TI
C6000 CGT 8.5.0.LTS:

```powershell
.\validation\build_host.ps1
.\.venv\Scripts\python.exe validation\corner_test.py
.\.venv\Scripts\python.exe validation\ab_test.py
.\.venv\Scripts\python.exe validation\check_safe_dsp.py

$env:ZOOM_TI_CGT = 'C:\path\to\ti-cgt-c6000_8.5.0.LTS'
.\tools\stage_build.ps1
.\tools\build_windows.ps1
```

The build wrapper creates the standard `MBDUKE.ZD2` and replaces the upstream
generic companion icon with the checked `MBDUKE.ZIC` artwork. The exact
safe-install protocol, including backup, readback comparison and Auto Save
OFF, is in [`docs/05-build-and-flash.md`](docs/05-build-and-flash.md). Never
save a patch containing an experimental effect.

## Current status

v1.14 differs from v1.13 only in the declared `dspload` (100 instead of 128);
it builds with TI CGT 8.5.0 and passes the TI listing audit. On 2026-11-25 it
replaced v1.13 on the MS-60B+ firmware 1.20 with the same safe sequence
(backup, Auto Save OFF, uninstall first, then install); the installed `.ZD2`
and `.ZIC` match the build byte for byte and the effect list changed only in
Duke's version digit. The v1.14 release package below contains exactly those
two files.

v1.13 passes the source lint, the 24 corner tests, the 9/9 A/B checks and the
TI listing audit, and builds with TI CGT 8.5.0. On 2026-11-25 it replaced
v1.12 on an MS-60B+ firmware 1.20 via the StompHacks fail-closed installer
(uninstall first, then install), after a full backup with Auto Save OFF
confirmed. The installed `.ZD2` and `.ZIC` were read back and match the build
byte for byte; the effect list changed only in Duke's version string. Its
release package remains in `releases/Duke-DI-v1.13`.

v1.12 has passed the source/host validation gates and was installed on an
MS-60B+ firmware 1.20 via the StompHacks fail-closed installer. The resulting
`.ZD2` and `.ZIC` were read back byte-for-byte, and Auto Save OFF was confirmed
by the pedal. `dspload` is declaration metadata the pedal trusts for its
270-unit budget, not a percentage. Since v1.14 it is 100, chosen above the
measured worst case (~87 units, `docs/07-cycle-probe.md`) with some margin.

## Download a ready-to-install release

Users who do not intend to build the project should use the versioned package
in [`releases/Duke-DI-v1.14`](releases/Duke-DI-v1.14). It contains the exact
`MBDUKE.ZD2` **and** `MBDUKE.ZIC` pair validated on the pedal, plus SHA-256
hashes and an installation guide. Download
[`Duke-DI-v1.14-MS60BPlus.zip`](releases/Duke-DI-v1.14-MS60BPlus.zip) from the
matching Git tag; do not rename or separate the two files. If an older Duke DI
is installed, uninstall it first. Previous packages stay in
[`releases/Duke-DI-v1.13`](releases/Duke-DI-v1.13) and
[`releases/Duke-DI-v1.12`](releases/Duke-DI-v1.12).

Built on the [StompHacks](https://github.com/thammer/stomphacks) cleanroom ABI.
