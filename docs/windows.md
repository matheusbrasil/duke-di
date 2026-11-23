# Windows build and validation

This repository supports a native Windows build with PowerShell, Python and
Git for Windows. The final packer invokes Git Bash internally; you do not need
WSL. The TI linker is sensitive to physical paths containing spaces, so the
provided wrapper builds from a temporary no-space copy automatically.

## Prerequisites

- Python 3.11+ with `pip`.
- [Git for Windows](https://git-scm.com/download/win), installed in the normal
  `C:\Program Files\Git` location.
- TI C6000 CGT **8.5.0.LTS**. Set its *install root* (the directory containing
  `bin\cl6x.exe`), not its `bin` directory:

  ```powershell
  $env:ZOOM_TI_CGT = 'C:\Users\mathe\Downloads\ti-cgt-c6000_8.5.0.LTS'
  ```

- For the host A/B harness, install either Visual Studio Build Tools with
  **Desktop development with C++**, LLVM, or MinGW. This is not needed to make
  the pedal `.ZD2`, but it is required to reproduce the desktop A/B gate.

## One-time setup

From the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install numpy scipy matplotlib
.\tools\stage_build.ps1
```

The staging script copies Duke DI into the vendored StompHacks checkout,
merges the author ledger, and creates `third_party\stomphacks\.venv` with its
required packages.

## Validate and build

```powershell
.\.venv\Scripts\python.exe reference\python\bake_tables.py
.\validation\build_host.ps1
.\.venv\Scripts\python.exe validation\ab_test.py
.\.venv\Scripts\python.exe validation\check_safe_dsp.py

$env:ZOOM_TI_CGT = 'C:\Users\mathe\Downloads\ti-cgt-c6000_8.5.0.LTS'
.\tools\build_windows.ps1
```

The expected packaged pair is
`third_party\stomphacks\effects\duke\build\MBDUKE.ZD2` and `MBDUKE.ZIC`.
The build wrapper restores the repository's validated Duke icon after the
upstream packer creates its generic icon. Do not connect or write to the pedal
until `REPORT.md`, the assembly audit, the ZIC check and the StompHacks dry-run
all pass.
