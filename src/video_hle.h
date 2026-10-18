#ifndef H1_VIDEO_HLE_H
#define H1_VIDEO_HLE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
int h1_ps1_video_hle_admit(unsigned);
int h1_ps1_video_hle_execute(unsigned,unsigned);
extern volatile uint32_t h1_video_hle_stats[2];
#ifdef __cplusplus
}
#endif
#endif
