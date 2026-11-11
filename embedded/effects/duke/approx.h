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

/* Interpolated interactive FMV tone-stack coefficients {b0,b1,b2,b3,a1,a2,a3}
 * for the current (treble, bass) knobs, via 2-D bilinear interpolation of the
 * EQ_N x EQ_N grid. Row-major cell(ti,bj); no divide (EQ_ISTEP, strides are
 * compile-time constants). Writes 7 floats into `c`. */
static inline void eq_of(float treb01, float bass01, float *c) {
    float ft = clampf(treb01 * EQ_ISTEP, 0.0f, (float)(EQ_N - 1) - 1e-4f);
    float fb = clampf(bass01 * EQ_ISTEP, 0.0f, (float)(EQ_N - 1) - 1e-4f);
    int ti = (int)ft, bj = (int)fb;
    float rt = ft - (float)ti, rb = fb - (float)bj;
    int r00 = OFF_EQ + (ti * EQ_N + bj) * EQ_STRIDE;
    int r01 = r00 + EQ_STRIDE;                 /* bass + 1 */
    int r10 = OFF_EQ + ((ti + 1) * EQ_N + bj) * EQ_STRIDE;   /* treble + 1 */
    int r11 = r10 + EQ_STRIDE;
    int k;
    for (k = 0; k < EQ_STRIDE; k++) {
        float v0 = tbl(r00 + k) + rb * (tbl(r01 + k) - tbl(r00 + k));
        float v1 = tbl(r10 + k) + rb * (tbl(r11 + k) - tbl(r10 + k));
        c[k] = v0 + rt * (v1 - v0);
    }
}

/* Interpolated ROLLOFF low-cut {b0,b1,a1} for the current treble knob. */
static inline void lowcut_of(float treb01, float *b0, float *b1, float *a1) {
    float fidx = clampf(treb01 * LC_ISTEP, 0.0f, (float)(LC_N - 1) - 1e-4f);
    int i = (int)fidx;
    float fr = fidx - (float)i;
    int r0 = OFF_LC + i * 3;
    int r1 = r0 + 3;
    *b0 = tbl(r0 + 0) + fr * (tbl(r1 + 0) - tbl(r0 + 0));
    *b1 = tbl(r0 + 1) + fr * (tbl(r1 + 1) - tbl(r0 + 1));
    *a1 = tbl(r0 + 2) + fr * (tbl(r1 + 2) - tbl(r0 + 2));
}

#endif /* DUKE_APPROX_H */
