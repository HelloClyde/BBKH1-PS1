#ifndef H1_PS1_STAT_H
#define H1_PS1_STAT_H
#include <time.h>
struct stat { unsigned st_mode; long st_size; time_t st_mtime; };
#ifdef __cplusplus
extern "C" {
#endif
int stat(const char *,struct stat *);
int fstat(int,struct stat *);
int mkdir(const char *,unsigned);
#ifdef __cplusplus
}
#endif
#define S_IRUSR 0400
#define S_IWUSR 0200
#endif
