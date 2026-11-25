/* probe_host.c - host harness for the cycle probe.
 * usage: probe_host MEAN_CYCLES PEAK_CYCLES SECONDS > out.f32
 * A scripted time-stamp counter makes every call cost MEAN_CYCLES, except one
 * call per second that costs PEAK_CYCLES.  Writes interleaved stereo float32
 * at 44.1 kHz so probe_decode.py can check that the tones decode back. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "sh_params.h"

void SH_AUDIO_FN(void **instance, void **ctx);

static unsigned tsc, read_no, cost;
unsigned host_tsc(void)
{
    /* reads per call: t0, t1 (overhead pair), t2, t3 (around the kernel) */
    unsigned n = read_no++ % 4;
    if (n == 1) tsc += 9;            /* overhead of one counter read */
    if (n == 3) tsc += 9 + cost;     /* overhead + kernel */
    return tsc;
}

int main(int argc, char **argv)
{
    if (argc < 4) { fprintf(stderr, "usage: probe_host MEAN PEAK SECONDS\n"); return 2; }
    unsigned mean = (unsigned)atoi(argv[1]), peak = (unsigned)atoi(argv[2]);
    int blocks = (int)(atof(argv[3]) * 44100.0 / SH_FRAMES);
    float coeff[64] = {0};
    coeff[SH_COEFF_BYPASS] = 1.0f;
    coeff[SH_PARAM_INPUT] = 0.5f; coeff[SH_PARAM_LEVEL] = 1.0f;
    static uint32_t state[(SH_STATE_BYTES / 4) + 2];
    state[SH_STATE_GUARD_WORD] = SH_STATE_GUARD;
    float eff[64];
    void *instance[4] = {0, coeff, state, 0};
    void *ctx[16] = {0, eff};
    double ph = 0;
    for (int b = 0; b < blocks; b++) {
        for (int i = 0; i < SH_FRAMES; i++) {
            float s = (float)(0.3 * sin(ph)); ph += 2 * 3.14159265358979 * 110 / 44100;
            eff[i] = s; eff[i + SH_CH_B_OFFSET] = s;
        }
        cost = (b % 2756 == 1000) ? peak : mean;
        SH_AUDIO_FN(instance, ctx);
        for (int i = 0; i < SH_FRAMES; i++) {
            float lr[2] = {eff[i], eff[i + SH_CH_B_OFFSET]};
            fwrite(lr, sizeof(float), 2, stdout);
        }
    }
    return 0;
}
