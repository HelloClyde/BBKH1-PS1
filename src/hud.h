#ifndef H1_PS1_HUD_H
#define H1_PS1_HUD_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
void h1_hud_reset(void);
void h1_hud_draw(uint32_t *lcd,unsigned tick,unsigned hz,unsigned frames,unsigned displayed,unsigned erased);
#ifdef __cplusplus
}
#endif
#endif
