#ifndef H1_SPU_PROFILE_H
#define H1_SPU_PROFILE_H
#include <stdint.h>
#ifndef H1_SPU_PROFILE
#define H1_SPU_PROFILE 0
#endif
enum h1_spu_profile_kind {
    HSP_SYNTH, HSP_CHANNELS, HSP_ADPCM, HSP_ADSR, HSP_MIX, HSP_FINISH,
    HSP_XA, HSP_IRQ, HSP_FEED, HSP_RETIRE, HSP_RESAMPLE, HSP_SUBMIT,
    HSP_RESET, HSP_COUNT
};
#if H1_SPU_PROFILE
#ifdef __cplusplus
extern "C" {
#endif
/* calls, sampled calls, sampled raw ticks. Nested scopes overlap. */
extern volatile uint32_t h1_spu_profile[HSP_COUNT][3];
extern volatile uint32_t h1_spu_voice_histogram[25];
unsigned h1_spu_profile_begin(unsigned kind,unsigned stride);
void h1_spu_profile_end(unsigned kind,unsigned start);
void h1_spu_profile_voices(unsigned mask);
#ifdef __cplusplus
}
#endif
#define H1_SPU_BEGIN(name,kind,stride) unsigned name=h1_spu_profile_begin(kind,stride)
#define H1_SPU_END(kind,name) h1_spu_profile_end(kind,name)
#else
#define H1_SPU_BEGIN(name,kind,stride)
#define H1_SPU_END(kind,name)
#endif
#endif
