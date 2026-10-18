#ifndef H1_LIBC_UNISTD_H
#define H1_LIBC_UNISTD_H
#ifdef __cplusplus
extern "C" {
#endif
int fsync(int);
int close(int);
int usleep(unsigned);
#ifdef __cplusplus
}
#endif
#endif
