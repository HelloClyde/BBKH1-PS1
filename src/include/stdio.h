#ifndef H1_LIBC_STDIO_H
#define H1_LIBC_STDIO_H

#include <stdarg.h>
#include <stddef.h>

#define EOF (-1)
#define SEEK_SET 0
#define SEEK_CUR 1
#define SEEK_END 2

typedef struct h1_ps1_file { void *handle; int fd,error,eof; } FILE;
extern FILE *stdout;
extern FILE *stderr;

#ifdef __cplusplus
extern "C" {
#endif

int printf(const char *format, ...);
int snprintf(char *output, size_t size, const char *format, ...);
int vsnprintf(char *output, size_t size, const char *format, va_list args);
int sscanf(const char *input, const char *format, ...);
int fflush(FILE *stream);
FILE *fopen(const char *,const char *);
int fclose(FILE *);
size_t fread(void *,size_t,size_t,FILE *);
size_t fwrite(const void *,size_t,size_t,FILE *);
int fseek(FILE *,long,int);
long ftell(FILE *);
int fgetc(FILE *);
char *fgets(char *,int,FILE *);
int fprintf(FILE *,const char *,...);
int sprintf(char *,const char *,...);
int puts(const char *);
int putchar(int);
int getchar(void);
int fputc(int,FILE *);
int fputs(const char *,FILE *);
int feof(FILE *);
int ferror(FILE *);
int fileno(FILE *);
int remove(const char *);
void rewind(FILE *);
void perror(const char *);

#ifdef __cplusplus
}
#endif

#endif
