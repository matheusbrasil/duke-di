# Duke DI release artefacts

Each versioned directory contains the **exact binary pair** for one Duke DI
release:

- `MBDUKE.ZD2` — DSP effect container;
- `MBDUKE.ZIC` — MS+ icon companion;
- `SHA256SUMS.txt` — SHA-256 hashes for both files;
- `README.txt` — compatibility, controls and safe-install summary.

Users should download the ZIP named for their version, verify both hashes, and
install the pair with StompHacks `pedal_diy.py`. Do not rename either file and
do not install only the ZD2: the pedal needs the ZIC to render the effect tile.

Release directories and ZIP names are immutable once tagged. Source changes
that affect the binary require a new manifest version, a new release directory,
a fresh hash manifest and a new Git tag.
