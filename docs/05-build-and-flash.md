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
    third_party/stomphacks/effects/duke/build/MBDUKE.text.dis --sym DukeDI
```

It scopes to `Fx_SFX_DukeDI` and fails on any stack use (`B15`), any
`__c6xabi_*` RTS helper (frame/divide/remainder), any divide helper, or any
call out to a non-generated symbol. Exit 0 = the generated object is
real-time-safe at the asm level. (`python3 tools/audit_text_dis.py --selftest`
verifies the auditor itself without a build.)

### If step 4 or 5 fails

| Symptom | Cause | Fix |
|---------|-------|-----|
| `FileNotFoundError .../bin/cl6x` | `ZOOM_TI_CGT` unset/wrong | step 2 |
| `.venv/bin/python3: No such file` | clone `.venv` missing | rerun step 3 |
| `.text ... exceeds` / over cap | kernel too big | raise `opt_for_space`, or trim LUTs |
| auditor flags `B15`/`rts-helper` | register spill -> stack frame | set `"opt_level": 1` in the manifest, re-run step 4 (documented in `zd2_make_effect.py`: -O1 stays leaf/frame-free) |
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

## What is genuinely blocked here (and why)

| Blocked | Reason | Unblock |
|---------|--------|---------|
| Final `MBDUKE.ZD2` blob | `cl6x` is proprietary; no root here | step 2 |
| SPICE curves (`spice/run_sweeps.sh`) | `ngspice` not installable (no root) | install ngspice/LTspice, run the scripts |
| Real `dspload` number | needs on-hardware cycle measurement | step 6 |
| The flash itself | needs the physical MS-60B+ | steps 7-8 |

Everything else - the model, the kernel, the tables, the SAFE-DSP source lint,
the asm auditor, the manifest validation up to the compile step, and the
off-pedal install self-test - runs and passes in this repo today.
