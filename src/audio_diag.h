#ifndef H1_PS1_AUDIO_DIAG_H
#define H1_PS1_AUDIO_DIAG_H
#ifdef __cplusplus
extern "C" {
#endif
#define H1_AUDIO_DIAG_API __attribute__((noinline,used,externally_visible))
H1_AUDIO_DIAG_API void h1_audio_diag_reset(void);
H1_AUDIO_DIAG_API void h1_audio_diag_io(unsigned lba,unsigned ticks);
H1_AUDIO_DIAG_API void h1_audio_diag_retire(unsigned consumed,unsigned queued,unsigned old_position,unsigned position);
H1_AUDIO_DIAG_API void h1_audio_diag_gap_finish(void);
#ifdef __cplusplus
}
#endif
#endif
