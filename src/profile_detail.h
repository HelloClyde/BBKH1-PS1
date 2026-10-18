#ifndef H1_PS1_PROFILE_DETAIL_H
#define H1_PS1_PROFILE_DETAIL_H
#include "h1_port.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Diagnostic counters: [kind][exact UNAI CF][calls, requested pixels]. */
extern volatile uint64_t h1_raster_stats[4][2048][2];
/* [GTE opcode][calls, raw ticks]; only counted in state 3. */
extern volatile uint64_t h1_gte_stats[64][2];
#ifdef __cplusplus
}
#endif
static inline void h1_ps1_raster_count(unsigned kind,unsigned cf,unsigned pixels){
    if(h1_ps1_stats.state==3){
        ++h1_raster_stats[kind][cf&2047u][0];
        h1_raster_stats[kind][cf&2047u][1]+=pixels;
    }
}
#endif
