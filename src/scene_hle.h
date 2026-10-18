#ifndef H1_SCENE_HLE_H
#define H1_SCENE_HLE_H
#include <stdint.h>
extern "C" {
int h1_ps1_scene_hle_admit(unsigned) __attribute__((noinline,used,externally_visible));
int h1_ps1_scene_hle_execute(unsigned,unsigned) __attribute__((noinline,used,externally_visible));
extern volatile uint32_t h1_scene_hle_stats[12];
}
#endif
