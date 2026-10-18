/* Per-game frontend preferences. GPL-2.0-or-later. */
#ifndef H1_PS1_SETTINGS_H
#define H1_PS1_SETTINGS_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint8_t mapping[45]; /* physical key -> PS1 button bit + 1, zero unassigned */
    uint8_t volume,volume_set,mute,gpu_skip,lcd_skip,quality,turbo,hud,reserved[3];
} h1_settings_t;
extern h1_settings_t h1_settings;
void h1_settings_ensure(void);
void h1_settings_load(const char *game);
void h1_settings_changed(void);
int h1_settings_save(void);
int h1_settings_writable(void);
void h1_mapping_defaults(void);
int h1_mapping_assign(unsigned bit,unsigned key);
int h1_key_reserved(unsigned key);
/* Called at startup and at a paused frame boundary, never from SPU mixing. */
void h1_ps1_apply_settings(void);
#ifdef __cplusplus
}
#endif
#endif
