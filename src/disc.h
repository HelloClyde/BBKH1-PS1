#ifndef H1_PS1_DISC_H
#define H1_PS1_DISC_H
#ifdef __cplusplus
extern "C" {
#endif
const char *h1_ps1_disc_error(void);
unsigned h1_ps1_disc_count(void);
unsigned h1_ps1_disc_selected(void);
int h1_ps1_disc_switch(unsigned disc);
void h1_ps1_disc_resume(void);
#ifdef __cplusplus
}
#endif
#endif
