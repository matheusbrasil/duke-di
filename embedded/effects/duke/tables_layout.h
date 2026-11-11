/* tables_layout.h - shared const-blob layout for the Duke DI kernel.
 *
 * The embedded kernel may not divide, call, or use libm (docs: SAFE-DSP). So
 * every knob-dependent nonlinear function - the 12AU7 waveshaper, the GAIN
 * drive taper, the passive tone-stack filter coefficients - is precomputed on
 * the desktop (reference/python/bake_tables.py) into one const_blob the kernel
 * reads with lookup + linear interpolation (multiplies only).
 *
 * THIS FILE IS THE SINGLE SOURCE OF TRUTH for the layout. bake_tables.py
 * mirrors these exact numbers; if you change one, change both (a self-check in
 * bake_tables.py asserts the total word count).
 *
 * All entries are float32 stored as uint32 bit patterns in `duke_tables[]`.
 */
#ifndef DUKE_TABLES_LAYOUT_H
#define DUKE_TABLES_LAYOUT_H

/* ---- 12AU7 stage waveshaper: quiescent static plate map ---------------- */
/* input grid u in [-WS_RANGE, +WS_RANGE], WS_N samples, uniform step.       */
#define WS_N        513
#define WS_RANGE    8.0f
/* precomputed so the kernel never divides: index = (u + WS_RANGE) * WS_ISTEP */
#define WS_ISTEP    (((float)(WS_N - 1)) / (2.0f * WS_RANGE))   /* 1/step */

/* ---- GAIN -> input drive taper ---------------------------------------- */
#define DRV_N       33            /* gain knob 0..1 in DRV_N-1 steps */
#define DRV_ISTEP   ((float)(DRV_N - 1))   /* index = gain * DRV_ISTEP */

/* ---- interactive passive FMV tone stack (3rd order) -------------------- */
/* 2-D grid over (treble, bass) knob fractions, EQ_N steps each. Each cell is
 * 7 floats {b0,b1,b2,b3,a1,a2,a3} of the bilinear-discretised stack biquad-
 * cubic, with the noon makeup gain folded into the numerator. Row-major:
 * cell(ti,bj) base = OFF_EQ + (ti*EQ_N + bj)*EQ_STRIDE.                      */
#define EQ_N        9
#define EQ_STRIDE   7
#define EQ_ISTEP    ((float)(EQ_N - 1))    /* index = knob01 * EQ_ISTEP */

/* ---- ROLLOFF low-cut: TREBLE-dependent corner (C8 4n7 into R18 220k, with
 * the TREBLE wiper Zout in series -> ~82..154 Hz). 1-D grid over treble;
 * each row = {b0,b1,a1} of a first-order high-pass.                         */
#define LC_N        17
#define LC_ISTEP    ((float)(LC_N - 1))

/* ---- word offsets into duke_tables[] ---------------------------------- */
#define OFF_WS       0
#define OFF_DRV      (OFF_WS  + WS_N)
#define OFF_EQ       (OFF_DRV + DRV_N)
#define OFF_LC       (OFF_EQ  + EQ_N * EQ_N * EQ_STRIDE)
#define DUKE_TABLES_WORDS (OFF_LC + LC_N * 3)

#endif /* DUKE_TABLES_LAYOUT_H */
