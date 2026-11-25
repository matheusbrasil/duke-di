/* duke.c - Duke DI: white-box 12AU7 preamp/DI kernel for the Zoom MS+ C674x.
 *
 * Models the Conspiracy-to-Commit "Nobelium" (a Noble Preamp DI clone): two
 * starved-heater 12AU7 gain stages on a 250 V rail, an interactive passive FMV
 * tone stack (Bass/Treble, derived by nodal analysis), and the Nobelium's
 * full 1/4-inch output topology, including the V2 White cathode follower.
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
/* R24 / V_SENS: plate-current delta (A) -> normalised Vgk shift. */
#define CATH_SCALE     4.285714355e+03f
#define CATH_LIMIT     4.0f
/* The V1A elliptic decimator has 0.1 dB passband ripple to 18 kHz and >=60 dB
 * at 22.05 kHz, the final 44.1-kHz Nyquist edge.  The old 25-kHz Butterworth
 * was above that edge and could fold a hard low-E transient into audio.
 *
 * V1B remains clean at nominal INPUT, so it runs 2x with a compact 20-kHz
 * Butterworth prefilter.  V1A receives the boosted FMV output and remains
 * 4x with the strict elliptic decimator, where the extra rejection matters. */
#define B2_B0           2.513799900e-01f
#define B2_B1           5.027599900e-01f
#define B2_B2           2.513799900e-01f
#define B2_A1          -1.712413900e-01f
#define B2_A2           1.767613700e-01f
#define B4_B0           2.802560000e-03f
#define B4_B1           2.215270000e-03f
#define B4_B2           2.802560000e-03f
#define B4_A1          -1.477739260e+00f
#define B4_A2           5.690956100e-01f
#define B4C_B0          1.0f
#define B4C_B1         -9.868615800e-01f
#define B4C_B2          1.0f
#define B4C_A1         -1.501997210e+00f
#define B4C_A2          7.218505700e-01f
#define B4D_B0          1.0f
#define B4D_B1         -1.363996640e+00f
#define B4D_B2          1.0f
#define B4D_A1         -1.530220330e+00f
#define B4D_A2          8.711596400e-01f
#define B4E_B0          1.0f
#define B4E_B1         -1.458749010e+00f
#define B4E_B2          1.0f
#define B4E_A1         -1.561586730e+00f
#define B4E_A2          9.644954800e-01f

/* ---- per-channel state layout inside instance[2] ----------------------- */
/* state[0]=drive smoothed, [1]=level smoothed, [S_LOWC]=LoCut smoothed; the
 * firmware writes the init guard at word SH_STATE_GUARD_WORD (= state_bytes/4),
 * just past our region. Channel A block at CHA, channel B at CHB. */
#define S_DRIVE 0
#define S_LEVEL 1
#define CHA     2
#define SB      22
#define CHB     (CHA + SB)
#define S_LOWC  (CHB + SB)
/* section indices within a channel block */
#define Z_CATH   0    /* shared V1A/V1B cathode shift, normalised */
#define Z_EQ     1    /* FMV tone stack, 3rd order -> words 1,2,3 */
#define Z_LC     4
#define Z_DC1    5
#define Z_DC2    6
#define Z_OUTHP  7
/* V1B/V1A: two input-history words plus four biquad states (8 words). */
#define Z_OS_V1B 8
#define Z_OS_V1A 12

/* one transposed-direct-form-II first-order section: y = b0*x + z, z updated */
FORCE_INLINE float tdf2(float x, float b0, float b1, float a1, float *z)
{
    float y = b0 * x + *z;
    *z = b1 * x - a1 * y;
    return y;
}

/* transposed-direct-form-II 3rd-order section (the interactive FMV stack).
 * c = {b0,b1,b2,b3,a1,a2,a3}; z[0..2] are this section's three state words.
 * Multiplies and adds only - SAFE-DSP compliant. */
FORCE_INLINE float df3(float x, const float *c, float *z)
{
    float y = c[0] * x + z[0];
    z[0] = c[1] * x - c[4] * y + z[1];
    z[1] = c[2] * x - c[5] * y + z[2];
    z[2] = c[3] * x - c[6] * y;
    return y;
}


/* transposed-direct-form-II biquad, used only inside the decimators. */
FORCE_INLINE float biquad(float x, float b0, float b1, float b2,
                          float a1, float a2, float *z)
{
    float y = b0 * x + z[0];
    z[0] = b1 * x - a1 * y + z[1];
    z[1] = b2 * x - a2 * y;
    return y;
}

FORCE_INLINE float decim2(float x, float *z)
{
    return biquad(x, B2_B0, B2_B1, B2_B2, B2_A1, B2_A2, z);
}

FORCE_INLINE float decim4(float x, float *z)
{
    x = biquad(x, B4_B0, B4_B1, B4_B2, B4_A1, B4_A2, &z[0]);
    x = biquad(x, B4C_B0, B4C_B1, B4C_B2, B4C_A1, B4C_A2, &z[2]);
    x = biquad(x, B4D_B0, B4D_B1, B4D_B2, B4D_A1, B4D_A2, &z[4]);
    return biquad(x, B4E_B0, B4E_B1, B4E_B2, B4E_A1, B4E_A2, &z[6]);
}

/* 2x V1B stage. `os` is {x[-2], one biquad state pair, x[-1]}.  Like the
 * 4x stage, it emits one base sample late so the decimator always sees time
 * increasing samples; feeding the midpoint before x[-1] attenuates treble. */
FORCE_INLINE float tube_stage_2x(float x, float cath, float *idelta, float *os)
{
    float xnm2 = os[0];
    float xnm1 = os[3];
    /* Causal 3-point Lagrange midpoint: flatter than a linear midpoint in
     * the upper audio octave, while still emitting the delayed x[-1] frame. */
    float u0 = (0.375f * xnm2 + 0.75f * xnm1 - 0.125f * x) - cath;
    float u1 = xnm1 - cath;
    (void)decim2(tube_shape(u0), &os[1]);
    {
        float y = decim2(tube_shape(u1), &os[1]);
        *idelta = 0.5f * (tube_current(u0) + tube_current(u1));
        os[0] = xnm1;
        os[3] = x;
        return y;
    }
}

/* 4x oversampled V1A stage. `os` is {x[-2], four biquad states, x[-1]}.
 * It deliberately emits one base sample late so a causal three-point Lagrange
 * curve can generate the .25/.50/.75 intermediate positions using x[0]. */
FORCE_INLINE float tube_stage_4x(float x, float cath, float *idelta, float *os)
{
    float xnm2 = os[0];
    float xnm1 = os[9];
    float q1 = 0.65625f * xnm2 + 0.4375f * xnm1 - 0.09375f * x;
    float q2 = 0.375f * xnm2 + 0.75f * xnm1 - 0.125f * x;
    float q3 = 0.15625f * xnm2 + 0.9375f * xnm1 - 0.09375f * x;
    float u0 = q1 - cath;
    float u1 = q2 - cath;
    float u2 = q3 - cath;
    float u3 = xnm1 - cath;
    (void)decim4(tube_shape(u0), &os[1]);
    (void)decim4(tube_shape(u1), &os[1]);
    (void)decim4(tube_shape(u2), &os[1]);
    float y = decim4(tube_shape(u3), &os[1]);
    *idelta = 0.25f * (tube_current(u0) + tube_current(u1)
                      + tube_current(u2) + tube_current(u3));
    os[0] = xnm1;
    os[9] = x;
    return y;
}

/* Zero one channel's SB-word state block (rare recovery path). */
FORCE_INLINE void clear_block(float *s)
{
    int k;
    for (k = 0; k < SB; k++)
        s[k] = 0.0f;
}

/* V2A/V2B White cathode follower is a clean buffer at the signal levels the
 * Noble NAM captures exercise.  The previous base-rate D3 hard clamp and
 * invented low-frequency asymmetry created unprotected harmonics; keep the
 * measured follower loss, while reserving nonlinear V2 modelling until a
 * 1/4-inch capture isolates and constrains it. */
FORCE_INLINE float white_cf(float u)
{
    return 0.92f * u;
}

/* Process one channel's 16-frame slice: the Nobelium 1/4 path only. */
FORCE_INLINE float duke_sample(float x, float drive, const float *eqc,
                                float lcb0, float lcb1, float lca1,
                                float lowcut, float vol, float *st)
{
    float u = x * drive;
    float cath = st[Z_CATH];
    float i1, i2;

    /* V1B is clean at nominal INPUT: 2x + strict elliptic decimation. */
    u = tube_stage_2x(u, cath, &i1, &st[Z_OS_V1B]);

    /* C8/R18 is derived at the actual output impedance of this EQ setting. */
    {
        float flat = df3(u, eqc, &st[Z_EQ]);
        float roll = tdf2(flat, lcb0, lcb1, lca1, &st[Z_LC]);
        u = flat + lowcut * (roll - flat);
    }

    /* V1A: same 4x anti-aliased nonlinearity. */
    u = u * CAL_INTERSTAGE;
    u = tube_stage_4x(u, cath, &i2, &st[Z_OS_V1A]);

    /* V1A and V1B share R24/C13/C14. Update one cathode-bias state from
     * their combined Koren plate-current deltas, rather than two artificial
     * |signal|-driven compressors. */
    {
        float target = CATH_SCALE * (i1 + i2);
        target = clampf(target, -CATH_LIMIT, CATH_LIMIT);
        cath += (1.0f - SAG_A) * (target - cath);
        st[Z_CATH] = cath;
    }

    /* C7 / VOLUME node: common to both output paths. */
    u = tdf2(u, DC1_B0, DC1_B1, DC1_A1, &st[Z_DC1]);
    u = u * CAL_VOL_NOM;

    /* C9 -> V2A/V2B White cathode follower -> C12/R22 -> 1/4 output. */
    u = tdf2(u, DC2_B0, DC2_B1, DC2_A1, &st[Z_DC2]);
    u = white_cf(u);
    u = tdf2(u, OUTHP_B0, OUTHP_B1, OUTHP_A1, &st[Z_OUTHP]);

    return u * vol;
}

/* The cycle probe (embedded/effects/probe) includes this file and defines
 * DUKE_KERNEL to inline the kernel inside its timed wrapper. */
#ifndef DUKE_KERNEL
#define DUKE_KERNEL void SH_AUDIO_FN
#endif
DUKE_KERNEL(void **instance, void **ctx)
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
    float input = coef[SH_PARAM_INPUT];
    float bass = coef[SH_PARAM_BASS];
    float treb = coef[SH_PARAM_TRBLE];
    float lvl  = coef[SH_PARAM_LEVEL];     /* stock VOL curve amplitude 0..1.5 */
    float lowc = coef[SH_PARAM_LOCUT];   /* selector 0 or 1 */

    if (!(fade >= 0.0f && fade <= 1.0f)) ok = 0;
    if (!(input >= 0.0f && input <= 1.0f)) ok = 0;
    if (!(bass >= 0.0f && bass <= 1.0f)) ok = 0;
    if (!(treb >= 0.0f && treb <= 1.0f)) ok = 0;
    if (!(lvl  >= 0.0f && lvl  <= 1.6f)) ok = 0;
    if (!(lowc >= 0.0f && lowc <= 1.0f)) ok = 0;

    if (!ok) {
        for (i = 0; i < SH_FRAMES; i++) {
            eff[i] = 0.0f;
            eff[i + SH_CH_B_OFFSET] = 0.0f;
        }
        return;
    }

    /* ---- per-block derived values (shared across both channels) --------- */
    /* Input maps to a bounded virtual source level: 50 is unity, rather
     * than a fictional gain knob on the Nobelium. */
    float drive_t = drive_of(input);
    float level_t = lvl * CAL_MAKEUP;
    float eqc[7];
    float lcb0, lcb1, lca1;
    eq_of(treb, bass, eqc);
    lowcut_of(treb, bass, &lcb0, &lcb1, &lca1);

    /* smoothed gain/level/LoCut carried in the shared state words */
    float sD = st[S_DRIVE];
    float sL = st[S_LEVEL];
    float sC = st[S_LOWC];

    for (i = 0; i < SH_FRAMES; i++) {
        sD += 0.01f * (drive_t - sD);      /* click-free drive/level */
        sL += 0.01f * (level_t - sL);
        sC += 0.01f * (lowc - sC);         /* click-free LoCut switch */
        float a = duke_sample(eff[i], sD, eqc, lcb0, lcb1, lca1, sC, sL, &st[CHA]);
        float b = duke_sample(eff[i + SH_CH_B_OFFSET], sD, eqc,
                              lcb0, lcb1, lca1, sC, sL, &st[CHB]);

        /* A non-finite result means this channel's filter state is poisoned;
         * clear the block so the next sample recovers instead of staying
         * silent until the chain is rebuilt.  (x - x) is NaN for NaN/Inf. */
        if (!((a - a) == 0.0f)) clear_block(&st[CHA]);
        if (!((b - b) == 0.0f)) clear_block(&st[CHB]);

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
    st[S_LOWC] = sC;
}
