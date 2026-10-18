#ifndef H1_PS1_PRESENT_FAST_H
#define H1_PS1_PRESENT_FAST_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
__attribute__((noinline,used,externally_visible))
void h1_ps1_present_fused(uint32_t *out,const uint16_t *vram,unsigned x,unsigned y,unsigned w,unsigned h,unsigned depth24);
#ifdef __cplusplus
}
#endif
#endif
