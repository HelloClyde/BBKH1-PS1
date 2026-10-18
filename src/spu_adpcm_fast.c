/* Exact scalar ADPCM kernel. GPL-2.0-or-later.
 * Preserve each 32-bit multiply wrap and separate arithmetic rounding.
 * Caller still owns IRQs, looping, voices, ADSR and all output settings. */
#include "spu_adpcm_fast.h"
volatile uint32_t h1_spu_adpcm_fast_stats[36] __attribute__((used,externally_visible));
static inline int contribution(int value,int coefficient) {
    return (int32_t)((uint32_t)value*(uint32_t)coefficient)>>6;
}
void h1_spu_adpcm_fast(int *dest,const unsigned char *src,int predictor,int shift) {
    ++h1_spu_adpcm_fast_stats[0];
    uintptr_t s=(uintptr_t)src&0x1fffffffu,d=(uintptr_t)dest&0x1fffffffu;
    if((unsigned)predictor>15u||(unsigned)shift>15u||(s<d+112u && d<s+14u)) {
        ++h1_spu_adpcm_fast_stats[1];h1_spu_adpcm_uncached(dest,src,predictor,shift);return;
    }
    ++h1_spu_adpcm_fast_stats[4+predictor];++h1_spu_adpcm_fast_stats[20+shift];
    unsigned scale=16u+(unsigned)shift;
    if(predictor==0||predictor>4) {
        ++h1_spu_adpcm_fast_stats[2];
        #pragma GCC unroll 2
        for(unsigned i=0;i<14;++i) {
            unsigned byte=src[i];
            dest[2*i]=(int32_t)(byte<<28)>>scale;
            dest[2*i+1]=(int32_t)((byte&240u)<<24)>>scale;
        }
    } else if(predictor==1) {
        ++h1_spu_adpcm_fast_stats[3];int a=dest[27];
        #pragma GCC unroll 2
        for(unsigned i=0;i<14;++i) {
            unsigned byte=src[i];
            int low=(int32_t)(byte<<28)>>scale,high=(int32_t)((byte&240u)<<24)>>scale;
            a=(int32_t)((uint32_t)low+(uint32_t)contribution(a,60));dest[2*i]=a;
            a=(int32_t)((uint32_t)high+(uint32_t)contribution(a,60));dest[2*i+1]=a;
        }
    } else {
        static const int first[3]={115,98,122},second[3]={-52,-55,-60};
        int f=first[predictor-2],g=second[predictor-2],a=dest[27],b=dest[26];
        #pragma GCC unroll 2
        for(unsigned i=0;i<14;++i) {
            unsigned byte=src[i];
            int low=(int32_t)(byte<<28)>>scale,high=(int32_t)((byte&240u)<<24)>>scale;
            int next=(int32_t)((uint32_t)low+(uint32_t)contribution(a,f)+(uint32_t)contribution(b,g));
            b=a;a=next;dest[2*i]=a;
            next=(int32_t)((uint32_t)high+(uint32_t)contribution(a,f)+(uint32_t)contribution(b,g));
            b=a;a=next;dest[2*i+1]=a;
        }
    }
}
