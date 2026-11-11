# 05 - Build and flash runbook

The one ordered procedure from "nothing installed" to "Duke DI running on the
MS-60B+". Everything up to step 3 is done and verified in this repo; steps 3-8
are the handover you run yourself, because they need TI's compiler and the
physical pedal.

> Two documented brick paths exist (`third_party/stomphacks/SAFETY.md`). The
> flashing steps below are in the order that keeps the pedal safe. Do not
> reorder them and do not automate past the per-write confirmation.

---

## Prerequisites

| Need | For | Status here |
|------|-----|-------------|
| Python 3 + numpy/scipy | Tier A, baking, A/B | present |
| g++ | host A/B harness | present |
| stomphacks + zoom-zt2 checkouts | pack/validate/flash | present (`third_party/`) |
| clone `.venv` | the build scripts hardcode it | **bootstrapped by `tools/stage_build.sh`** |
| **TI C6000 CGT 8.5.0** (`cl6x`/`asm6x`/`lnk6x`/`dis6x`) | compile the kernel | **you install (handover)** |
| MS-60B+ over USB-MIDI | flashing | **your hardware** |

Run the gate first; it prints exactly what is missing and what each gap blocks:

```
python3 tools/check_env.py
```

A green run except `ngspice` and `TI C6000 cl6x` is the expected desktop state:
those two are the only out-of-scope pieces, and `check_env` exits 0 anyway
because they do not block the in-scope work.

---

## Step 1 - Regenerate and validate the model (desktop, done here)

```
python3 reference/python/bake_tables.py     # bake LUTs + host twin
bash    validation/build_host.sh            # gcc -> validation/host_duke
python3 validation/ab_test.py               # expect 8/8
python3 validation/check_safe_dsp.py        # source SAFE-DSP lint
```

All four pass in this repo. Do this whenever you touch the kernel, the tables
or the reference.

## Step 2 - Install TI C6000 CGT 8.5.0 (handover)

`cl6x` is TI's proprietary C6000 compiler: free, but it needs a TI account and
is not redistributable, so it is not present here. Download the 8.5.0.LTS
package (ships with Code Composer Studio) and point the build at it:

```
export ZOOM_TI_CGT=/path/to/ti-cgt-c6000_8.5.0.LTS
# sanity: these four must exist
ls "$ZOOM_TI_CGT"/bin/{cl6x,asm6x,lnk6x,dis6x}
```

## Step 3 - Stage the effect (bootstraps the clone `.venv` too)

```
bash tools/stage_build.sh
```

This copies the effect sources + baked `tables.bin` into
`third_party/stomphacks/effects/duke/`, merges our registered author entry
(`matheusbrasil` -> prefix `MB`) into the clone's gitignored ledger, and
creates the clone's `.venv`. The clone's build scripts call `.venv/bin/python3`
with **no system fallback**, so this step is mandatory even though the deps are
present system-wide. On a host without `python3-venv`/`ensurepip` (no root to
`apt install`), it falls back to a `--system-site-packages` venv that exposes
the already-installed deps; either way `check_env.py` then shows
`clone .venv (build python)` green.

## Step 4 - Compile and pack the `.ZD2`

```
cd third_party/stomphacks
python3 tools/zd2_make_effect.py effects/duke/manifest.json
#   -> effects/duke/build/MBDUKE.ZD2  + MBDUKE.ZIC  + REPORT.md
```

The pipeline runs 8 steps: clean-room scaffold, `cl6x` compile of `duke.c`,
clean-room asm generation, assemble/link/pack (from-scratch container), verify,
icon, finalize, final validation. `verify_cleanroom` auto-asserts the loader
contract for us: relocations are only ABS32/ABS_L16/ABS_H16, no unwanted data
sections (`.bss`/`.cinit`/...), the `.text` size is within budget, the 1164-word
`const_blob` sits after `_Coe`, and the param/function table matches the
manifest. **`REPORT.md`'s checks must all pass before the file goes near a
pedal.**

## Step 5 - Audit the compiled kernel asm (SAFE-DSP, the manual gate made a script)

The build's built-in no-stack assertion (`assert "B15" not in body`) only runs
for effects whose kernel is in the `.audio` section. Duke DI uses
`"kernel_section": "text"` (the kernel exceeds the 1472-byte `.audio` cap), so
that branch only **dumps** the disassembly for review. Close the gap:

```
# back in the repo root
python3 tools/audit_text_dis.py \
    third_party/stomphacks/effects/duke/build/MBDUKE.text.dis --sym DukeDI \
    --allow-stack
```

It scopes to `Fx_SFX_DukeDI` and fails on any `__c6xabi_*` RTS helper, any
divide helper, or any CALL to a non-generated symbol. Duke DI's manifest sets
`"allow_stack": true` (see below), so pass `--allow-stack`: B15/stack use is
then permitted (stock-precedented) while the hard call/divide bans still fire.
Exit 0 = the generated object is real-time-safe at the asm level.
(`python3 tools/audit_text_dis.py --selftest` verifies the auditor itself
without a build.) The build's own `verify_cleanroom` (step 4) independently
asserts the kernel makes **no CALLs at all** - that is the non-negotiable gate;
this script is the reviewable companion.

### Why Duke DI uses `allow_stack` (the register-spill story)

The kernel builds two local coefficient arrays per block (`eqc[7]`, `lcc[3]`);
their addresses are taken, so they **must** live on the stack - a frame is
unavoidable, and a strict no-B15 kernel is not achievable here. The manifest
therefore carries, all together:

```json
"opt_level": 2,          // inline the static-inline DSP helpers (df3, lowcut_of)
"opt_for_space": null,   // DROP -ms: with -ms, cl6x CALLs __c6xabi_push_rts to
                         //   save callee-saved regs (a call -> cleanroom link
                         //   fails on unresolved __c6xabi_push_rts/pop_rts)
"allow_stack": true      // permit the B15 frame (stock-precedented)
```

Two findings that are easy to miss:
- **`opt_for_space` must be `null`, not `3`.** `-ms3` makes cl6x emit
  `CALLP __c6xabi_push_rts/pop_rts` for register saves; the clean-room link has
  no RTS library, so it dies on those unresolved symbols. Without `-ms` the
  saves are inlined.
- **At `-O1` cl6x does not inline `df3`/`lowcut_of`**, leaving real CALLs that
  `verify_cleanroom` rejects. `-O2` inlines them. To make inlining
  deterministic regardless of cl6x heuristics, the helpers are marked
  `FORCE_INLINE` (`static inline __attribute__((always_inline))`, defined in
  `embedded/effects/duke/approx.h`) - this also keeps the gcc host A/B build
  identical. Do not drop it.

### If step 4 or 5 fails

| Symptom | Cause | Fix |
|---------|-------|-----|
| `FileNotFoundError .../bin/cl6x` | `ZOOM_TI_CGT` unset/wrong | step 2 |
| `.venv/bin/python3: No such file` | clone `.venv` missing | rerun step 3 |
| `.text ... exceeds` / over cap | kernel too big | set `opt_for_space` back toward `3`, or trim LUTs (16 KB text budget) |
| link: unresolved `__c6xabi_push_rts`/`pop_rts` | `-ms` made the reg-save a CALL | set `"opt_for_space": null` in the manifest |
| `verify_cleanroom`: `kernel makes calls: [... df3 ... lowcut_of ...]` | cl6x did not inline a helper | keep `"opt_level": 2` and `FORCE_INLINE` on the helper |
| auditor flags `rts-helper` | register spill via RTS call | `"opt_for_space": null`; if it persists, reduce live state in `duke.c` |
| auditor flags `stack` (B15) without `--allow-stack` | the kernel has a frame | pass `--allow-stack` (manifest already sets `allow_stack:true`) |
| auditor flags `divide` | a divide survived into asm | find it in `duke.c`, replace with a reciprocal-step constant (see `approx.h`) |
| relocs/section census assert | ABI contract break | fix the offending reference; see `docs/zd2-abi.md` |

## Step 6 - Measure the real DSP load (on hardware)

`manifest.json` declares `"dspload": 60`. The pedal **trusts this number
completely** - it sums declared loads per patch and refuses an effect that
would overflow the budget, but it never measures. 60 is a conservative
engineering estimate for a two-triode + 3rd-order-EQ + transformer chain, not a
measurement. Before relying on it in dense patches, measure the real cycle cost
on hardware and set an honest number (keep headroom). Treat 60 as a ceiling to
validate, not a guarantee.

## Step 7 - Pre-flight, off the pedal

```
cd third_party/stomphacks
# never-send list + full failure-path proof of the transfer engine
.venv/bin/python3 tools-pedal/install_selftest.py          # exit 0 = PASS
# read-only verdict on OUR file: id/name/filename/icon vs the stock catalog
.venv/bin/python3 tools-pedal/pedal_diy.py classify effects/duke/build/MBDUKE.ZD2
```

`install_selftest.py` never opens a MIDI port and must pass after any change to
the transfer tooling. `classify` is dry-run's read-only core: it must accept
Duke DI as a DIY effect (group byte `04`, id `0x0400A001`, filename `MBDUKE`)
and would refuse anything that looks stock or unknown.

## Step 8 - Flash (the binding SAFETY.md sequence)

Read `third_party/stomphacks/SAFETY.md` first; its never-send SysEx list is
binding. Then, in order, confirming every write by hand:

```
cd third_party/stomphacks
# 1. session opener: connects, records identity, forces autosave OFF and
#    refuses to continue until the pedal's ACK confirms it is really off
.venv/bin/python3 tools-pedal/safe_connect.py <out-dir>

# 2. full backup BEFORE your first write (every effect, patch, FLST_SEQ)
.venv/bin/python3 tools-pedal/backup_pedal.py <out-dir>

# 3. optional dry run of the exact install (no bytes written)
.venv/bin/python3 tools-pedal/pedal_diy.py install effects/duke/build/MBDUKE.ZD2 --dry-run

# 4. the real install (installs the binary + edits the effect list ONLY;
#    never writes a patch or memory slot, so it cannot enter the boot patch)
.venv/bin/python3 tools-pedal/pedal_diy.py install effects/duke/build/MBDUKE.ZD2
```

`pedal_diy.py` is fail-closed: it validates the new effect list on the PC
(`tools/flst_check.py`), runs the whole transfer over one owned connection with
timeout-bounded replies, reads back and byte-compares every uploaded file, and
closes the file session cleanly on any failure. To remove it later:
`pedal_diy.py uninstall effects/duke/build/MBDUKE.ZD2` (uninstall is exempt from
the envelope check, so a bad file can always be removed).

Keep **autosave OFF** until you have auditioned the effect and are confident it
is stable. Autosave OFF is the invariant the whole anti-bricking model rests on.

---

## Status (what builds, what still needs hardware)

With TI CGT 8.5.0 and ngspice installed, **the build now runs end to end**:
`zd2_make_effect.py` produces `MBDUKE.ZD2` (all 8 steps pass, `verify_cleanroom`
green: leaf kernel, no CALLs, relocs ABS32/ABS_L16/ABS_H16 only, dspload 22.2%
of the 270 budget), the asm auditor passes with `--allow-stack`, the host A/B is
8/8, and `spice/run_sweeps.sh` writes both reference Bode files.

| Item | State | Note |
|------|-------|------|
| `MBDUKE.ZD2` blob | **builds** | needs `cl6x` (step 2); recipe above |
| SPICE curves | **generated** | `ngspice -b` via `spice/run_sweeps.sh` |
| Real `dspload` number | open | needs on-hardware cycle measurement (step 6) |
| The flash itself | open | needs the physical MS-60B+ (steps 7-8) |

The only remaining handovers are the two that inherently need the pedal: the
honest `dspload` measurement and the flash. `cl6x` and `ngspice` are free
installs (see the toolchain notes); neither needs root for a user-prefix
install.

---

## Appendix - installing the toolchain (verified commands)

### TI C6000 CGT 8.5.0 (`cl6x`) - free, needs a TI login, no root

TI gates the installer behind a login + export-control click-through (the
public ESD mirror 404s), so fetch it from the signed-in tool page, then install
to a user prefix:

```
# Download ti_cgt_c6000_8.5.0.LTS_linux-x64_installer.bin from
#   https://www.ti.com/tool/C6000-CGT   (or the download_archive.htm page)
chmod +x ti_cgt_c6000_8.5.0.LTS_linux-x64_installer.bin
./ti_cgt_c6000_8.5.0.LTS_linux-x64_installer.bin --mode unattended --prefix "$HOME/ti"
#   (or run it with no flags for the GUI/console wizard)

export ZOOM_TI_CGT="$HOME/ti/ti-cgt-c6000_8.5.0.LTS"      # add to ~/.bashrc
ls "$ZOOM_TI_CGT"/bin/cl6x "$ZOOM_TI_CGT"/bin/asm6x "$ZOOM_TI_CGT"/bin/lnk6x
```

`chmod` and the installer are **two separate commands** - don't chain them, or
`chmod` eats the `--prefix` flag.

### ngspice - free, no login

```
# distro package (needs root on your box):
sudo apt install -y ngspice        # or: dnf install / pacman -S / brew install

# OR a no-root source build to ~/.local (batch mode needs no X/ncurses):
curl -L -o /tmp/ngspice-47.tar.gz \
  "https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/47/ngspice-47.tar.gz"
echo "894e649651f1838a14095e5a5439e7d3aa63e87ede14d283173fda4fcdef675f  /tmp/ngspice-47.tar.gz" | sha256sum -c -
tar -xzf /tmp/ngspice-47.tar.gz -C /tmp
cd /tmp/ngspice-47 && ./configure --prefix="$HOME/.local" --without-x --with-readline=no
make -j"$(nproc)" && make install
export PATH="$HOME/.local/bin:$PATH"
```

Then `cd spice && bash run_sweeps.sh` writes the two Bode files into
`validation/`. (The `12au7.lib` model avoids the PSPICE/LTspice `PWR`/`PWRS`
builtins so it runs on a stock ngspice with no compatibility flag.)
