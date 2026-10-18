#ifndef H1_PS1_DELAY_HLE_H
#define H1_PS1_DELAY_HLE_H
#ifdef __cplusplus
extern "C" {
#endif
__attribute__((noinline,used,externally_visible)) int h1_ps1_delay_hle_admit(unsigned pc);
int h1_ps1_delay_hle_execute(unsigned pc,unsigned token);
#ifdef __cplusplus
}
#endif
#endif
