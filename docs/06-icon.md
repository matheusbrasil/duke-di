# 06 - Duke DI icon

The Duke DI icon is original, monochrome MS+ artwork. Its visual language is
intentionally compact, following the same principle used by the FETCOMP icon:
one immediately recognisable device symbol and a high-contrast wordmark rather
than a miniature photograph of a pedal.

It has a dark face, four stock-style controls, a 12AU7 envelope with twin
triode plates, and the `DUKE DI` name. The decorative knobs are fixed icon
furniture; the MS-60B+ overlays the live controls and pages its five actual
parameters normally.

## Files

```text
embedded/effects/duke/icon/
    MBDUKE.ZIC       checked companion file installed by the pedal
    duke_di_0.png    72x97 source frame
    duke_di_1.png    102x128 source frame
tools/make_duke_icon.py  artwork generator
tools/zic.py             ZIC encoder, decoder and structural checker
```

`tools/zic.py` was added from the supplied MS+ ZIC-format guide. It uses the
standard non-amp geometry for the MS-60B+: small 72x97 and large 102x128
frames, dark flag (`invert=1`) and layout `0`. The final two-frame ZIC is
exactly 2,600 bytes.

## Regenerate and inspect

From the repository root:

```powershell
.\.venv\Scripts\python.exe .\tools\make_duke_icon.py
.\.venv\Scripts\python.exe .\tools\zic.py check .\embedded\effects\duke\icon\MBDUKE.ZIC
.\.venv\Scripts\python.exe .\tools\zic.py decode .\embedded\effects\duke\icon\MBDUKE.ZIC .\embedded\effects\duke\icon\preview --scale 4
```

Inspect the generated `preview_0.png` and `preview_1.png`, which are for
viewing only and must not be re-encoded as scaled images.

## Build integration

The upstream StompHacks packer creates a generic icon from the manifest.
`tools/build_windows.ps1` therefore first performs the ordinary clean-room
build, then copies the validated Duke companion icon over the generic
`effects/duke/build/MBDUKE.ZIC`. This does not modify the `.ZD2` audio
container.

An icon update is installed by the same safe replace procedure as a code
update: backup, uninstall the existing `MBDUKE` pair, confirm both files are
absent, install the build pair, and read back **both** files byte-for-byte.
See [`05-build-and-flash.md`](05-build-and-flash.md).
