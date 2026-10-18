#ifndef H1_PS1_PORT_H
#define H1_PS1_PORT_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint32_t magic,version,state,error,frames,displayed,raw_start,raw_end,rtc_start,rtc_end;
    uint32_t video_ticks,disc_reads,disc_hits,disc_ticks,audio_samples,stop,pc,checksum;
    uint32_t tick_hz,core,cache_mib,video_mode;
    uint32_t cpu_checks[4];
    uint32_t gpu_ticks,gpu_calls,spu_ticks,spu_calls;
    uint32_t idle_batches,idle_iterations;
    uint32_t paused_ticks;
} h1_ps1_stats_t;
extern volatile h1_ps1_stats_t h1_ps1_stats;
extern int h1_ps1_jump[12];
int h1_ps1_setjmp(int *);
void h1_ps1_longjmp(int *) __attribute__((noreturn));
void h1_ps1_escape(int) __attribute__((noreturn));
void h1_ps1_present(void);
void h1_ps1_log(const char *,...);
void h1_ps1_log_flush(void);
void h1_ps1_check_stop(void);
void h1_ps1_video_open(void);
void h1_ps1_video_close(void);
void h1_ps1_message(const char *);
unsigned h1_ps1_rtc(void) __attribute__((__noinline__,__used__,__externally_visible__));
void h1_ps1_audio_close(void);
void h1_ps1_audio_pause(int);
int h1_ps1_select(char *path,unsigned capacity);
void h1_ps1_configure(void);
int h1_ps1_idle_admit(unsigned);
int h1_ps1_idle_execute(unsigned,unsigned);
#ifdef __cplusplus
}
#endif
#endif
