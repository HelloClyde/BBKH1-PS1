/* H1/Y100 V1.41 opt-in, reversible JZ4740 clock trial. GPL-2.0-or-later. */
#ifndef H1_CLOCK_CONTROL_H
#define H1_CLOCK_CONTROL_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Header 8 words; original, target, running and restored snapshots of 11
 * registers each. State: 0 unused, 1 active, 2 restored, 3 refused, 4 failed. */
#define H1_CLOCK_STATS_WORDS 52
extern volatile uint32_t h1_clock_stats[H1_CLOCK_STATS_WORDS];
int h1_clock_open(unsigned cpu_mhz);
int h1_clock_close(void);
void h1_clock_observe(void);
#ifdef __cplusplus
}
#endif
#endif
