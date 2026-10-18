#ifndef H1_LIBC_STRING_H
#define H1_LIBC_STRING_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

void *memcpy(void *destination, const void *source, size_t count);
void *memmove(void *destination, const void *source, size_t count);
void *memset(void *destination, int value, size_t count);
int memcmp(const void *left, const void *right, size_t count);
size_t strlen(const char *text);
int strcmp(const char *left, const char *right);
int strncmp(const char *left, const char *right, size_t count);
char *strcpy(char *destination, const char *source);
char *strncpy(char *destination, const char *source, size_t count);
char *strcat(char *destination, const char *source);
char *strchr(const char *text, int character);
char *strrchr(const char *text, int character);
char *strstr(const char *text, const char *needle);
int strcasecmp(const char *,const char *);
int strncasecmp(const char *,const char *,size_t);
char *strdup(const char *);
char *strncat(char *,const char *,size_t);
char *strtok(char *,const char *);
size_t strspn(const char *,const char *);
size_t strcspn(const char *,const char *);
char *strpbrk(const char *,const char *);
void *memchr(const void *,int,size_t);
char *strerror(int);

#ifdef __cplusplus
}
#endif

#endif
