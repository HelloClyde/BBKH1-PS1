#ifndef H1_SPU_ADPCM_FAST_H
#define H1_SPU_ADPCM_FAST_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void h1_spu_adpcm_fast(int *,const unsigned char *,int,int) __attribute__((used,externally_visible));
void h1_spu_adpcm_uncached(int *,const unsigned char *,int,int) __attribute__((used,externally_visible));
extern volatile uint32_t h1_spu_adpcm_fast_stats[36];
#ifdef __cplusplus
}
#endif
#endif
