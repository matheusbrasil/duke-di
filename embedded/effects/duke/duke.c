/* duke.c - Duke DI: white-box 12AU7 preamp/DI kernel for the Zoom MS+ C674x.
 *
 * Models the Conspiracy-to-Commit "Nobelium" (a Noble Preamp DI clone): two
 * starved-heater 12AU7 gain stages on a 250 V rail, a passive boost-only
 * shelving EQ (bass 150 Hz, treble 3.5 kHz), a switchable 90 Hz low-cut, a
 * V2 White cathode follower, and an optional JT-DB-EPC DI-transformer path.
 * Full circuit analysis: docs/01-circuit-analysis.md. Tier A reference:
 * reference/python/duke_ref.py. This kernel is the Tier B reduction of it.
 *
 * SAFE-DSP contract (docs/building-effects.md, SAFETY.md) - every line obeys:
 *   - leaf function: no calls. No libm (tanh/exp/pow), no divide instruction.
 *   - every knob-dependent reciprocal/transcendental is a precomputed LUT in
 *     duke_tables[] (reference/python/bake_tables.py); the loop only
 *     interpolates (approx.h). Fixed filters are float literals (duke_fixed.h).
 *   - no statics, no stack reliance; all state in instance[2].
 *   - guard prologue + per-sample output clamp: both mandatory (SAFETY.md).
 *   - coefficients read into locals ONCE, checked, then only locals used.
 *
 * Needs "kernel_section": "text" (the model exceeds the 1472-B .audio budget).
 * Copyright (c) 2026. MIT. Built on the stomphacks cleanroom ABI.
 */
#include <stdint.h>
#include "sh_params.h"     /* generated from manifest.json into build/ */
#include "duke_fixed.h"    /* generated: fixed first-order section coeffs */
#include "approx.h"        /* LUT interpolation; declares duke_tables[] */

/* ---- voicing calibration (plain constants; see docs/assumptions.md) ----- */
#define CAL_INTERSTAGE 2.2f      /* V1B -> V1A fixed voicing gain */
#define CAL_VOL_NOM    0.64f     /* nominal VOLUME-pot node divider */
#define CAL_MAKEUP     1.14f     /* final normalisation; matches Tier A level */
#define SAG_DEPTH      0.15f     /* shared-rail compression depth */
#define GRID_CLAMP     1.714f    /* D3 clamp: 0.6 V / V_SENS(0.35) */
#define XF_SAT         0.33f     /* transformer LF core-sat cubic coeff */

/* ---- per-channel state layout inside instance[2] ----------------------- */
/* state[0]=drive smoothed, [1]=level smoothed; firmware writes the init guard
 * at word SH_STATE_GUARD_WORD (= state_bytes/4 = 32), just past our region.
 * Channel A block at CHA, channel B at CHB; SB sections each (TDF2, 1 word). */
#define S_DRIVE 0
#define S_LEVEL 1
#define CHA     5
#define SB      11
#define CHB     (CHA + SB)
/* section indices within a channel block */
#define Z_V1BSAG 0
#define Z_TRE    1
#define Z_BAS    2
#define Z_LC     3
#define Z_V1ASAG 4
#define Z_DC1    5
#define Z_DC2    6
#define Z_CFHP   7
#define Z_OUTHP  8
#define Z_XFHP   9
#define Z_XFLP   10

/* one transposed-direct-form-II first-order section: y = b0*x + z, z updated */
static inline float tdf2(float x, float b0, float b1, float a1, float *z)
{
    float y = b0 * x + *z;
    *z = b1 * x - a1 * y;
    return y;
}

/* one 12AU7 stage: waveshaper + slow shared-rail sag compression.
 * `env` carries the per-channel sag envelope state (one float). */
static inline float tube_stage(float u, float *env)
{
    float e = *env;
    float ax = u >= 0.0f ? u : -u;
    e += (1.0f - SAG_A) * (ax - e);     /* 2.06 Hz one-pole on |u| */
    *env = e;
    float w = tube_shape(u);            /* static plate curve, LUT */
    return w * (1.0f - SAG_DEPTH * e);  /* rail sag -> gentle compression */
}

/* White cathode follower + D3 grid clamp (no divide). */
static inline float white_cf(float u, float *zhp)
{
    float ucl = u > GRID_CLAMP ? GRID_CLAMP : u;
    float hi  = tdf2(ucl, CFHP_B0, CFHP_B1, CFHP_A1, zhp);  /* >33.9 Hz */
    float lo  = ucl - hi;                                   /* deep bass */
    float alo = lo >= 0.0f ? lo : -lo;
    return 0.92f * hi + 0.92f * (lo + 0.15f * lo * alo);
}

/* process one channel's 16-frame slice. `st` -> this channel's state block. */
static inline float duke_sample(float x, float drive, float b0t, float b1t,
                                float a1t, float b0b, float b1b, float a1b,
                                float lowcut, float xfmr, float vol, float *st)
{
    float u = x * drive;

    /* V1B */
    u = tube_stage(u, &st[Z_V1BSAG]);

    /* boost-only EQ: treble high-shelf then bass low-shelf */
    u = tdf2(u, b0t, b1t, a1t, &st[Z_TRE]);
    u = tdf2(u, b0b, b1b, a1b, &st[Z_BAS]);

    /* ROLLOFF low-cut (90 Hz) - selector 0/1 crossfaded, no branch divergence */
    {
        float hp = tdf2(u, LOWCUT_B0, LOWCUT_B1, LOWCUT_A1, &st[Z_LC]);
        u = u + lowcut * (hp - u);
    }

    /* V1A */
    u = u * CAL_INTERSTAGE;
    u = tube_stage(u, &st[Z_V1ASAG]);

    /* V1A loading + coupling DC blocks */
    u = tdf2(u, DC1_B0, DC1_B1, DC1_A1, &st[Z_DC1]);
    u = u * CAL_VOL_NOM;
    u = tdf2(u, DC2_B0, DC2_B1, DC2_A1, &st[Z_DC2]);

    /* V2 White cathode follower */
    u = white_cf(u, &st[Z_CFHP]);

    /* output DC block */
    u = tdf2(u, OUTHP_B0, OUTHP_B1, OUTHP_A1, &st[Z_OUTHP]);

    /* optional DI transformer (XLR path): LF core sat + HF leakage rolloff */
    {
        float hf  = tdf2(u, XFHP_B0, XFHP_B1, XFHP_A1, &st[Z_XFHP]);
        float lf  = u - hf;
        float sat = lf - XF_SAT * lf * lf * lf;      /* cubic LF core sat */
        float xf  = tdf2(sat + hf, XFLP_B0, XFLP_B1, XFLP_A1, &st[Z_XFLP]);
        u = u + xfmr * (xf - u);                     /* selector crossfade */
    }

    return u * vol;
}

void SH_AUDIO_FN(void **instance, void **ctx)
{
    const float *coef = (const float *)instance[1];
    float *eff        = (float *)ctx[1];
    float *st         = (float *)instance[2];
    int i;

    /* ---- mandatory guard prologue (SAFETY.md) -------------------------- */
    unsigned ok = 1;
#ifdef SH_STATE_GUARD
    if (((const uint32_t *)instance[2])[SH_STATE_GUARD_WORD] != SH_STATE_GUARD)
        ok = 0;
#endif
    /* read every coefficient into a local ONCE, then validate the locals */
    float fade = coef[SH_COEFF_BYPASS];
    float gain = coef[SH_PARAM_GAIN];
    float bass = coef[SH_PARAM_BASS];
    float treb = coef[SH_PARAM_TREBLE];
    float lvl  = coef[SH_PARAM_LEVEL];     /* stock VOL curve amplitude 0..1.5 */
    float lowc = coef[SH_PARAM_LOCUT];   /* selector 0 or 1 */
    float xfm  = coef[SH_PARAM_XFMR];      /* selector 0 or 1 */

    if (!(fade >= 0.0f && fade <= 1.0f)) ok = 0;
    if (!(gain >= 0.0f && gain <= 1.0f)) ok = 0;
    if (!(bass >= 0.0f && bass <= 1.0f)) ok = 0;
    if (!(treb >= 0.0f && treb <= 1.0f)) ok = 0;
    if (!(lvl  >= 0.0f && lvl  <= 1.6f)) ok = 0;
    if (!(lowc >= 0.0f && lowc <= 1.0f)) ok = 0;
    if (!(xfm  >= 0.0f && xfm  <= 1.0f)) ok = 0;

    if (!ok) {
        for (i = 0; i < SH_FRAMES; i++) {
            eff[i] = 0.0f;
            eff[i + SH_CH_B_OFFSET] = 0.0f;
        }
        return;
    }

    /* ---- per-block derived values (shared across both channels) --------- */
    float drive_t = drive_of(gain);
    float level_t = lvl * CAL_MAKEUP;
    float b0t, b1t, a1t, b0b, b1b, a1b;
    shelf_of(OFF_TREBLE, treb, &b0t, &b1t, &a1t);
    shelf_of(OFF_BASS,   bass, &b0b, &b1b, &a1b);

    /* smoothed gain/level carried in the shared state words */
    float sD = st[S_DRIVE];
    float sL = st[S_LEVEL];

    for (i = 0; i < SH_FRAMES; i++) {
        sD += 0.01f * (drive_t - sD);      /* click-free drive/level */
        sL += 0.01f * (level_t - sL);

        float a = duke_sample(eff[i], sD, b0t, b1t, a1t, b0b, b1b, a1b,
                              lowc, xfm, sL, &st[CHA]);
        float b = duke_sample(eff[i + SH_CH_B_OFFSET], sD, b0t, b1t, a1t,
                              b0b, b1b, a1b, lowc, xfm, sL, &st[CHB]);

        /* bypass crossfade (click-free, exact pass-through when fade=0) */
        float ina = eff[i];
        float inb = eff[i + SH_CH_B_OFFSET];
        a = ina + fade * (a - ina);
        b = inb + fade * (b - inb);

        /* mandatory output clamp: scrubs NaN/Inf/torn reads */
        if (!(a > -8.0f && a < 8.0f)) a = 0.0f;
        if (!(b > -8.0f && b < 8.0f)) b = 0.0f;

        eff[i] = a;
        eff[i + SH_CH_B_OFFSET] = b;
    }

    st[S_DRIVE] = sD;
    st[S_LEVEL] = sL;
}
