#ifndef H1_PS1_MENU_H
#define H1_PS1_MENU_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* 0 resume, 1 exit. Caller owns the stopped guest and paused PCM device. */
int h1_ps1_pause_menu(uint8_t held[45],unsigned opening_touch,unsigned opening_key);
#ifdef __cplusplus
}
#endif
#endif
