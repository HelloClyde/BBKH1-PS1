#ifndef H1_CLOCK_RUN_H
#define H1_CLOCK_RUN_H
#ifdef __cplusplus
extern "C" {
#endif
void h1_clock_run_frame(unsigned frame);
void h1_clock_run_close(void);
void h1_clock_run_checkpoint(unsigned stage);
void h1_clock_run_save(void);
void gba_audio_snapshot(unsigned *out);
#ifdef __cplusplus
}
#endif
#endif
