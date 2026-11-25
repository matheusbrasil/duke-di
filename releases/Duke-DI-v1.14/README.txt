DUKE DI v1.14 — Zoom MS-60B+ custom effect
============================================

Contents
--------
MBDUKE.ZD2  DSP effect container
MBDUKE.ZIC  required MS+ icon companion
SHA256SUMS.txt  integrity hashes

What changed since v1.13
------------------------
Only the declared DSP load: 100 instead of 128.  The sound, controls and
audio code are identical to v1.13.
- Measured on the pedal with a cycle probe: about 14,060 DSP cycles per
  16-sample call on average and about 19,950 in the worst call, roughly 61
  and 87 load units.  100 keeps headroom above that worst case.
- The pedal refuses a patch whose effects' declared loads add up to more
  than 270, so the lower value leaves more room for other effects in the
  same patch.

Changes in v1.13 (since v1.12), robustness only:
- A channel whose output turns non-finite clears its filter state and
  recovers on the next sample instead of staying silent.
- The LoCut switch fades in and out instead of stepping.
- A NaN table index is clamped to the table instead of reading outside it.

Compatibility
-------------
Built and read-back verified on Zoom MS-60B+ firmware 1.20.
This is a custom effect distributed at your own risk.  Do not use it on a
saved patch while testing.

Install safely
--------------
1. Back up the pedal with StompHacks tools-pedal/backup_pedal.py.
2. Ensure Auto Save is OFF and confirm it on the pedal.
3. If an older MBDUKE is already installed, uninstall it FIRST:
     python tools-pedal/pedal_diy.py uninstall MBDUKE.ZD2
4. Confirm MBDUKE.ZD2 and MBDUKE.ZIC are absent.
5. Install this MBDUKE.ZD2 with tools-pedal/pedal_diy.py install MBDUKE.ZD2.
   The installer automatically requires and uploads the matching MBDUKE.ZIC.
6. Read back both files and compare their SHA-256 values against SHA256SUMS.txt.
7. Audition only in an unsaved scratch patch. Never save the test patch.

Controls
--------
Input  virtual source level; 50 is nominal passive-instrument level.
Bass   boost-only; 0 is the flat reference.
Trble  boost-only; 0 is the flat reference.
Level  final 1/4-inch trim; 80 is unity.
LoCut  physical Nobelium ROLLOFF network.

Starting point: Input 50, Bass 0, Trble 0, Level 80, LoCut OFF.
