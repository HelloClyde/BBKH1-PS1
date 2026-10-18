/* Optional lossy audio rendering; GPL-2.0-or-later. */
#ifndef H1_SPU_TURBO_H
#define H1_SPU_TURBO_H
#ifdef __cplusplus
extern "C" {
#endif
extern unsigned h1_spu_turbo_mode;
/* batches, half-rate voices, quiet voices, protected voices, source frames,
 * half-rate voice frames, quiet voice frames, mono mixed pairs. */
extern volatile unsigned h1_spu_turbo_stats[8];
void h1_spu_turbo_reset(void);
void h1_spu_turbo_set(unsigned enabled);
int h1_spu_samples_half(int (*decode)(void *,int,int *),void *context,
    int channel,int count,int *history,int step,int *position,int *index,int *output);
int h1_spu_samples_quiet(int (*decode)(void *,int,int *),void *context,
    int channel,int count,int *history,int step,int *position,int *index);
void h1_spu_mix_half_mono(int *sum,int count,int left,int right,const int *voice);
void h1_spu_finish_mono(int *sum,int count,int volume,int enabled,short *out);
#ifdef __cplusplus
}
#endif
#endif
