/* Exact span shortcuts for UNAI. GPL-2.0-or-later. */
#ifndef H1_PS1_RASTER_FAST_H
#define H1_PS1_RASTER_FAST_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void h1_ps1_fill16(uint16_t *dst,unsigned count,unsigned color);
void h1_ps1_blend16(uint16_t *dst,unsigned count,unsigned color,unsigned mask_set);
int h1_ps1_sprite4(uint16_t *dst,unsigned count,const uint8_t *texture,unsigned u,
                   unsigned mask,const uint16_t *clut);
#ifdef __cplusplus
}
#endif
#endif
