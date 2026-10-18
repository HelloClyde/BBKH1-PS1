#ifndef H1_PS1_TIMEVAL_H
#define H1_PS1_TIMEVAL_H
struct timeval { long tv_sec,tv_usec; };
#ifdef __cplusplus
extern "C" {
#endif
int gettimeofday(struct timeval *,void *);
#ifdef __cplusplus
}
#endif
#endif
