/* probe.c - Duke DI cycle probe for the Zoom MS-60B+ C674x.
 *
 * Runs the unmodified Duke DI kernel (duke.c, inlined) and times each call
 * with the C64x+ time-stamp counter.  Instead of audio it outputs two square
 * waves whose PITCH encodes the measured cycles per 16-frame call:
 *   channel A: running mean      channel B: decaying peak
 *   f = PROBE_K / cycles  Hz     (cycles = PROBE_K / f)
 * Pitch survives level, EQ and output-path changes, so the tones can be
 * recorded over USB audio or from the analog output and decoded with
 * validation/probe_decode.py.  If the counter is not running, channel A plays
 * a fixed marker tone and channel B is silent.
 *
 * Test tool only: never save a patch containing it.
 * Copyright (c) 2026. MIT.
 */
#include <stdint.h>
#include "sh_params.h"

#ifdef __TI_COMPILER_VERSION__
#include <c6x.h>
#define READ_TSC() (TSCL)
#else
extern unsigned host_tsc(void);
#define READ_TSC() host_tsc()
#endif

/* inline Duke's kernel as duke_kernel(); FORCE_INLINE comes from approx.h,
 * which duke.c includes before the kernel definition */
#define DUKE_KERNEL FORCE_INLINE void duke_kernel
#include "duke.c"

#define PROBE_K       7.0e6f               /* f = K / cycles */
#define PROBE_HALF    (44100.0f / (2.0f * PROBE_K))   /* half-period samples per cycle */
#define PROBE_AMP     0.25f
#define MARKER_HALF   22.05f               /* 1 kHz marker: counter not running */

/* probe state words, just past Duke's region (S_LOWC is its last word) */
#define P_MEAN  (S_LOWC + 1)
#define P_PEAK  (S_LOWC + 2)
#define P_PHA   (S_LOWC + 3)
#define P_PHB   (S_LOWC + 4)
#define P_SGA   (S_LOWC + 5)
#define P_SGB   (S_LOWC + 6)

FORCE_INLINE float square(float half, float *ph, float *sg)
{
    float s = *sg;
    if (!(s == 1.0f || s == -1.0f)) s = 1.0f;
    *ph += 1.0f;
    if (*ph >= half) {
        *ph -= half;
        if (*ph >= half) *ph = 0.0f;
        s = -s;
    }
    *sg = s;
    return PROBE_AMP * s;
}

void SH_AUDIO_FN(void **instance, void **ctx)
{
    float *eff = (float *)ctx[1];
    float *st  = (float *)instance[2];
    int i;

    if (((const uint32_t *)instance[2])[SH_STATE_GUARD_WORD] != SH_STATE_GUARD) {
        for (i = 0; i < SH_FRAMES; i++) {
            eff[i] = 0.0f;
            eff[i + SH_CH_B_OFFSET] = 0.0f;
        }
        return;
    }

    unsigned t0 = READ_TSC();
    unsigned t1 = READ_TSC();
    unsigned t2 = READ_TSC();
    duke_kernel(instance, ctx);
    unsigned t3 = READ_TSC();

    unsigned over = t1 - t0;
    unsigned span = t3 - t2;
    float c = (span > over) ? (float)(span - over) : 0.0f;

    float mean = st[P_MEAN];
    float peak = st[P_PEAK];
    if (!((mean - mean) == 0.0f)) mean = 0.0f;
    if (!((peak - peak) == 0.0f)) peak = 0.0f;
    if (c > 0.0f) {
        mean = (mean == 0.0f) ? c : mean + 0.001f * (c - mean);
        peak = (c > peak) ? c : peak - 0.00002f * peak;   /* ~20 s hold */
    }
    st[P_MEAN] = mean;
    st[P_PEAK] = peak;

    float ha = (c > 0.0f) ? clampf(mean * PROBE_HALF, 2.0f, 2000.0f) : MARKER_HALF;
    float hb = clampf(peak * PROBE_HALF, 2.0f, 2000.0f);
    for (i = 0; i < SH_FRAMES; i++) {
        eff[i] = square(ha, &st[P_PHA], &st[P_SGA]);
        eff[i + SH_CH_B_OFFSET] = (c > 0.0f) ? square(hb, &st[P_PHB], &st[P_SGB]) : 0.0f;
    }
}
