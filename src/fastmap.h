#ifndef H1_PS1_FASTMAP_H
#define H1_PS1_FASTMAP_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    void *(*allocate)(size_t);
    void (*release)(void *);
    int (*flush)(void *,int,int);
} h1_fastmap_api;
/* Table pointer mapping only: four aliases of 2 MiB RAM block pointers and
 * one 512 KiB BIOS block pointer region. Game RAM remains on the checked path. */
__attribute__((noinline,used,externally_visible)) int h1_fastmap_open(const h1_fastmap_api *api);
__attribute__((noinline,used,externally_visible)) int h1_fastmap_close(void);
extern volatile uint32_t h1_fastmap_stats[32];
#ifdef __cplusplus
}
#endif
#endif
