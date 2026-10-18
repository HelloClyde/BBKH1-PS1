/* Exact memoization of the existing SPU numerical ADPCM decoder.
 * GPL-2.0-or-later. IRQs, loop flags, pointers and envelopes remain upstream. */
#include "spu_adpcm_cache.h"
#include <string.h>
typedef struct {
    uint32_t control;
    int seed1,seed2;
    uint16_t encoded[7];
    int pcm[28];
} block;
static block cache[64];
volatile uint32_t h1_spu_adpcm_stats[6] __attribute__((used,externally_visible));
void h1_spu_adpcm_cache_reset(void) {
    memset(cache,0,sizeof(cache));
    for(unsigned i=0;i<6;++i)h1_spu_adpcm_stats[i]=0;
}
void h1_spu_adpcm_cached(int *dest,const unsigned char *src,int predictor,int shift) {
    ++h1_spu_adpcm_stats[0];
    uintptr_t s=(uintptr_t)src&0x1fffffffu,d=(uintptr_t)dest&0x1fffffffu;
    if((s&1u)||(unsigned)predictor>15u||(unsigned)shift>15u||(s<d+112u && d<s+14u)) {
        ++h1_spu_adpcm_stats[3];h1_spu_adpcm_uncached(dest,src,predictor,shift);return;
    }
    block *entry=&cache[(s>>4)&63u];
    uint32_t control=0x40000000u|((unsigned)predictor<<16)|(unsigned)shift;
    int independent=predictor==0||predictor>4;
    int seed1=independent?0:dest[27],seed2=independent?0:dest[26];
    const uint16_t *encoded=(const uint16_t*)src;
    uint32_t changed=entry->control^control;
    changed|=(uint32_t)(entry->seed1^seed1)|(uint32_t)(entry->seed2^seed2);
    #pragma GCC unroll 7
    for(unsigned i=0;i<7;++i)changed|=entry->encoded[i]^encoded[i];
    if(!changed) {
        memcpy(dest,entry->pcm,112);++h1_spu_adpcm_stats[1];
        if(independent)++h1_spu_adpcm_stats[5];
        return;
    }
    ++h1_spu_adpcm_stats[2];entry->seed1=seed1;entry->seed2=seed2;
    #pragma GCC unroll 7
    for(unsigned i=0;i<7;++i)entry->encoded[i]=encoded[i];
    h1_spu_adpcm_uncached(dest,src,predictor,shift);
    memcpy(entry->pcm,dest,112);entry->control=control;h1_spu_adpcm_stats[4]+=112;
}
