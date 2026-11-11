/* tables_layout.h - shared const-blob layout for the Duke DI kernel.
 *
 * The embedded kernel may not divide, call, or use libm (docs: SAFE-DSP). So
 * every knob-dependent nonlinear function - the 12AU7 waveshaper, the GAIN
 * drive taper, the boost-only shelf coefficients - is precomputed on the
 * desktop (reference/python/bake_tables.py) into one const_blob the kernel
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

/* ---- boost-only shelf coefficient tables (first order, 3 coeffs each) --- */
/* knob 0..1 -> SHELF_N-1 steps; each row = {b0, b1, a1} of a 1-pole shelf. */
#define SHELF_N     17
#define SHELF_ISTEP ((float)(SHELF_N - 1))

/* ---- word offsets into duke_tables[] ---------------------------------- */
#define OFF_WS       0
#define OFF_DRV      (OFF_WS  + WS_N)
#define OFF_BASS     (OFF_DRV + DRV_N)
#define OFF_TREBLE   (OFF_BASS + SHELF_N * 3)
#define DUKE_TABLES_WORDS (OFF_TREBLE + SHELF_N * 3)

#endif /* DUKE_TABLES_LAYOUT_H */
