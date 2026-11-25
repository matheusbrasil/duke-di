DUKE DI v1.13 — Zoom MS-60B+ custom effect
============================================

Contents
--------
MBDUKE.ZD2  DSP effect container
MBDUKE.ZIC  required MS+ icon companion
SHA256SUMS.txt  integrity hashes

What changed since v1.12
------------------------
Robustness only; the sound and controls are unchanged.
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
