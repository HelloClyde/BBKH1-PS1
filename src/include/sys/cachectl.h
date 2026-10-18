#ifndef H1_PS1_CACHECTL_H
#define H1_PS1_CACHECTL_H
#define ICACHE 1
#define DCACHE 2
#define BCACHE 3
#ifdef __cplusplus
extern "C" {
#endif
int cacheflush(void *,int,int);
#ifdef __cplusplus
}
#endif
#endif
