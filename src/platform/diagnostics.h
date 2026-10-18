#ifndef H1_PS1_DIAG_H
#define H1_PS1_DIAG_H
#include "h1_port.h"
#define h1_diag h1_ps1_log
static inline int h1_diag_is_verbose(void) { return 0; }
static inline void h1_diag_batch_begin(void) {}
static inline void h1_diag_batch_end(void) {}
#endif
