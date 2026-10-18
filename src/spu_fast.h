#ifndef H1_SPU_FAST_H
#define H1_SPU_FAST_H
#ifdef __cplusplus
extern "C" {
#endif
int h1_spu_samples_noint(int (*decode)(void *,int,int *),void *context,
    int channel,int count,int *history,int step,int *position,int *index,int *output);
#ifdef __cplusplus
}
#endif
#endif
