# 07 - Measuring Duke DI's real DSP cost (cycle probe)

`MBPROBE.ZD2` ("Probe", id `0x0900A002`, SFX group) is a test tool, not an
effect to play through. It runs the unmodified Duke DI kernel and times every
call with the C674x time-stamp counter (`TSCL`), then outputs the result as
two square-wave tones instead of audio:

| Channel | Meaning | Decode |
|---|---|---|
| A (left) | running mean of cycles per 16-sample call (~0.4 s smoothing) | cycles = 7,000,000 / Hz |
| B (right) | decaying peak (holds the worst call for ~20 s) | cycles = 7,000,000 / Hz |

Pitch, not level, carries the value, so the output level, the pedal's output
EQ and the recording path do not affect the reading. The cost of the counter
reads themselves is measured and subtracted on every call. If the counter is
not running, channel A plays a fixed 1 kHz marker and channel B is silent.

Its knobs are Duke DI's (Input, Bass, Trble, Level, LoCut) and are passed to
the timed kernel, so different settings can be compared. Duke's cost should
not depend on them much, since it has no setting-dependent branches.

## Build

```powershell
$env:ZOOM_TI_CGT = 'C:\path\to\ti-cgt-c6000_8.5.0.LTS'
.\tools\build_probe.ps1
# -> third_party\stomphacks\effects\probe\build\MBPROBE.ZD2 + MBPROBE.ZIC
.\.venv\Scripts\python.exe .\tools\audit_text_dis.py `
  .\third_party\stomphacks\effects\probe\build\MBPROBE.text.dis --sym Probe --allow-stack
```

The probe's state is 212 bytes (Duke's 188 plus its own 24). StompHacks'
generator caps state at 192 bytes as a "proven floor"; `build_probe.ps1`
raises that cap to 672 bytes in its temporary build copy only, because the
MS-60B+ 1.20 firmware gives every effect slot a fixed 672-byte state buffer
(boot setup `FUN_c0231220`: six buffers at `0x11F01400 + k*0x2A0`). Duke's own
build is unaffected.

## Use

1. Install with the normal safe sequence (`docs/05-build-and-flash.md`): Auto
   Save OFF, backup, `pedal_diy.py install ...\effects\probe\build\MBPROBE.ZD2`.
2. In an unsaved scratch patch, add Probe as the only effect. Never save it.
3. Record at least 10 s of the pedal's output (USB audio or the analog
   output into an interface) as a WAV file, input silent or playing.
4. Decode:

```powershell
.\.venv\Scripts\python.exe .\validation\probe_decode.py recording.wav
```

5. Remove it afterwards: `pedal_diy.py uninstall ...\MBPROBE.ZD2`.

A host round trip (`validation/probe_host.c` with a scripted counter) decodes
fed values within 0.2 % for the mean and within 3 % low for the peak.

## First measurement (2026-11-25, MS-60B+ firmware 1.20)

Probe alone in an unsaved patch, default knobs, 29 s recorded at 48 kHz:
the cycle counter runs, and Duke DI v1.13 costs **14,060 cycles per 16-sample
call** on average (878 cycles per sample; 2-second windows 14,050-14,080).
That is within 0.3 % of the static listing estimate (~14,100), so memory
stalls add almost nothing.

The first recording carried only channel A on both tracks, so the peak was
recorded separately from the pedal's R output: about 352 Hz, i.e. a worst
call of about **19,950 cycles** (the decaying reading moved between 19,700
and 19,950 over 29 s). That is about 42 % above the mean; the counter
measures elapsed time, so this most likely includes interrupts landing during
the call. At ~230 cycles per load unit, the mean corresponds to a load of
about 61 and the worst call to about 87, both under the 128 declared at the
time. v1.14 lowers the declaration to 100 on the strength of this result.
The kernel did not change, so the measurement still applies.

## Reading the result

At an inferred ~372 MHz a 16-sample block lasts about 135,000 cycles. The
static estimate for Duke v1.13 is ~14,100 cycles per call; StompHacks'
budget of 270 load units corresponds to roughly 62,000 cycles (see the
firmware notes). The declared `dspload` should stay above the load implied
by the peak, since the peak shows how much interrupts and cache misses add.
