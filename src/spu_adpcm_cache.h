#ifndef H1_SPU_ADPCM_CACHE_H
#define H1_SPU_ADPCM_CACHE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void h1_spu_adpcm_cached(int *,const unsigned char *,int,int) __attribute__((used,externally_visible));
void h1_spu_adpcm_uncached(int *,const unsigned char *,int,int) __attribute__((used,externally_visible));
void h1_spu_adpcm_cache_reset(void) __attribute__((used,externally_visible));
extern volatile uint32_t h1_spu_adpcm_stats[6];
#ifdef __cplusplus
}
#endif
#endif
