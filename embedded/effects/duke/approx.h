/* approx.h - division-free, call-free, libm-free inline helpers for the
 * Duke DI C674x kernel.
 *
 * SAFE-DSP (docs/building-effects.md): the audio blob links no runtime
 * library, and the DSP has no divide instruction. So `/`, tanhf, expf, powf
 * all become calls that resolve to nowhere. Everything here is a leaf-safe
 * `static inline` built from multiplies, adds, and the float<->int convert
 * intrinsics the compiler emits inline on the C674x.
 *
 * Every per-knob reciprocal the model needs (filter coefficients, the drive
 * taper, the shelf gains) was precomputed on the desktop into duke_tables[]
 * (reference/python/bake_tables.py). These helpers only ever INTERPOLATE that
 * table - index scaling uses precomputed reciprocal-steps that are constants,
 * so no divide survives into the generated code.
 */
#ifndef DUKE_APPROX_H
#define DUKE_APPROX_H

#include "tables_layout.h"

/* The const blob, emitted by the cleanroom scaffold (manifest "const_blob").
 * Stored as uint32 bit patterns; we read it as float. */
extern const unsigned int duke_tables[];

static inline float tbl(int i) {
    /* type-pun a table word to float without a call or a union-in-memory */
    const float *f = (const float *)duke_tables;
    return f[i];
}

/* Clamp helper (branches compile to compares + selects, no call). */
static inline float clampf(float x, float lo, float hi) {
    if (x < lo) x = lo;
    if (x > hi) x = hi;
    return x;
}

/* Linear interpolation of a 1-D table of length n, base word `off`, over an
 * already-scaled fractional index `fidx` in [0, n-1]. No divide: the caller
 * scales with a constant reciprocal-step from tables_layout.h. */
static inline float lut1(int off, int n, float fidx) {
    fidx = clampf(fidx, 0.0f, (float)(n - 1) - 1e-4f);
    int i = (int)fidx;              /* SPTRUNC on C674x, inline */
    float fr = fidx - (float)i;
    float a = tbl(off + i);
    float b = tbl(off + i + 1);
    return a + fr * (b - a);
}

/* 12AU7 waveshaper: static plate curve, sampled over [-WS_RANGE, WS_RANGE].
 * index = (u + WS_RANGE) * WS_ISTEP, WS_ISTEP a compile-time reciprocal. */
static inline float tube_shape(float u) {
    float fidx = (u + WS_RANGE) * WS_ISTEP;
    return lut1(OFF_WS, WS_N, fidx);
}

/* GAIN knob (0..1) -> input drive factor. */
static inline float drive_of(float gain01) {
    return lut1(OFF_DRV, DRV_N, gain01 * DRV_ISTEP);
}

/* Fetch an interpolated first-order shelf {b0,b1,a1} for a knob step.
 * Writes into the 3 out params; no divide (row stride is a constant). */
static inline void shelf_of(int base_off, float knob01,
                            float *b0, float *b1, float *a1) {
    float fidx = clampf(knob01 * SHELF_ISTEP, 0.0f, (float)(SHELF_N - 1) - 1e-4f);
    int i = (int)fidx;
    float fr = fidx - (float)i;
    int r0 = base_off + i * 3;
    int r1 = r0 + 3;
    *b0 = tbl(r0 + 0) + fr * (tbl(r1 + 0) - tbl(r0 + 0));
    *b1 = tbl(r0 + 1) + fr * (tbl(r1 + 1) - tbl(r0 + 1));
    *a1 = tbl(r0 + 2) + fr * (tbl(r1 + 2) - tbl(r0 + 2));
}

#endif /* DUKE_APPROX_H */
