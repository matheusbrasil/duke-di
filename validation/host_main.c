/* host_main.c - gcc host harness for the Duke DI kernel (duke.c).
 *
 * Proves the SAFE-DSP kernel compiles and runs as portable C, then lets
 * validation/ab_test.py feed signals through the EXACT kernel math and
 * compare against the Tier A golden reference (reference/python/duke_ref.py).
 * This is NOT the pedal build: the real .ZD2 is produced by
 * third_party/stomphacks/tools/zd2_make_effect.py with the TI cl6x compiler.
 * Here we only exercise duke_sample()/SH_AUDIO_FN on the host CPU.
 *
 * Contract we reproduce from the firmware (docs/zd2-abi.md):
 *   instance[1] -> coeff[]   (coeff[0]=bypass fade, coeff[5..]=params)
 *   instance[2] -> state[]   (zeroed, guard magic at word state_bytes/4)
 *   ctx[1]      -> eff[32]    (ch A 0..15, ch B 16..31, in place)
 *
 * Usage:  host_duke  gain bass treble level lowcut xfmr  < in.f64 > out.f64
 *   controls are coeff-domain values in [0,1] (level is amplitude 0..1.6),
 *   matching the normalised controls passed to duke_ref.process().
 *   stdin/stdout are raw little-endian float64 mono streams.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sh_params.h"

/* the kernel's audio entry (duke.c) */
void SH_AUDIO_FN(void **instance, void **ctx);

int main(int argc, char **argv)
{
    if (argc != 7) {
        fprintf(stderr, "usage: %s gain bass treble level lowcut xfmr "
                        "< in.f64 > out.f64\n", argv[0]);
        return 2;
    }

    /* coeff[]: index 0 bypass fade (1.0 = fully wet), 5.. = params */
    float coeff[16];
    memset(coeff, 0, sizeof coeff);
    coeff[SH_COEFF_BYPASS]  = 1.0f;                 /* fully wet */
    coeff[SH_PARAM_GAIN]    = (float)atof(argv[1]);
    coeff[SH_PARAM_BASS]    = (float)atof(argv[2]);
    coeff[SH_PARAM_TREBLE]  = (float)atof(argv[3]);
    coeff[SH_PARAM_LEVEL]   = (float)atof(argv[4]);
    coeff[SH_PARAM_LOCUT]   = (float)atof(argv[5]);
    coeff[SH_PARAM_XFMR]    = (float)atof(argv[6]);

    /* state[]: SH_STATE_BYTES zeroed, guard magic one word past our region */
    enum { STATE_WORDS = (SH_STATE_BYTES / 4) + 2 };
    static uint32_t state[STATE_WORDS];
    memset(state, 0, sizeof state);
    ((uint32_t *)state)[SH_STATE_GUARD_WORD] = SH_STATE_GUARD;

    void *instance[3];
    instance[0] = NULL;
    instance[1] = coeff;
    instance[2] = state;

    float eff[32];
    void *ctx[2];
    ctx[0] = NULL;           /* GTRIN unused by duke */
    ctx[1] = eff;

    /* stream float64 samples; drive both channels with the same mono signal,
     * emit channel A (channels are identical here, so A == B). */
    double in[SH_FRAMES];
    size_t n;
    while ((n = fread(in, sizeof(double), SH_FRAMES, stdin)) > 0) {
        int i;
        for (i = 0; i < SH_FRAMES; i++) {
            float s = (i < (int)n) ? (float)in[i] : 0.0f;
            eff[i] = s;
            eff[i + SH_CH_B_OFFSET] = s;
        }
        SH_AUDIO_FN(instance, ctx);
        double out[SH_FRAMES];
        for (i = 0; i < (int)n; i++) out[i] = (double)eff[i];
        fwrite(out, sizeof(double), n, stdout);
    }
    return 0;
}
