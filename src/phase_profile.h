#ifndef H1_PHASE_PROFILE_H
#define H1_PHASE_PROFILE_H
#include <stdint.h>
/* Diagnostic only. Mutually exclusive wall-clock attribution, including
 * instrumentation cost. CPU includes dispatch and unwrapped core work. */
enum { HPP_CPU, HPP_COMPILE, HPP_INVALIDATE, HPP_EVENT, HPP_GTE,
    HPP_VLC_GATE, HPP_CODE_CHECK, HPP_VLC_BODY, HPP_VIDEO_WAIT,
    HPP_MOVIE, HPP_MOVIE_IO, HPP_MOVIE_GPU, HPP_MDEC,
    HPP_IDCT, HPP_RGB, HPP_GPU, HPP_SPU, HPP_LCD, HPP_DISC,
    HPP_PCM, HPP_INPUT, HPP_PACE, HPP_COUNT };
#define HPP_BINS 120u
#ifdef __cplusplus
extern "C" {
#endif
unsigned h1_phase_enter(unsigned);
void h1_phase_leave(unsigned *);
void h1_phase_frame(unsigned);
extern volatile uint32_t h1_phase_state[8];
extern volatile uint32_t h1_phase_bins[HPP_BINS][HPP_COUNT][2];
#ifdef __cplusplus
}
#endif
/* GCC cleanup executes on every ordinary return in C and C++. */
#define H1_PHASE(kind) unsigned h1_phase_previous \
    __attribute__((cleanup(h1_phase_leave)))=h1_phase_enter(kind)
#endif
