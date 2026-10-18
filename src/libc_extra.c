/* H1 file ABI adapter and small libc additions, GPL-2.0-or-later. */
#include "h1_sdk.h"
#include "h1_port.h"
#include "port.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <limits.h>
#include <sys/stat.h>
#include <sys/time.h>

FILE *stderr;
static FILE *files[32];
FILE *fopen(const char *path,const char *mode) {
    unsigned i; for(i=0;i<32 && files[i];++i) {}
    if(i==32)return 0;
    void *h=h1_fopen(path,mode); if(!h)return 0;
    FILE *f=calloc(1,sizeof(*f));
    if(!f){h1_fclose(h);return 0;}
    f->handle=h;f->fd=(int)i+3;files[i]=f;return f;
}
int fclose(FILE *f) {
    if(!f || !f->handle)return -1;
    int r=h1_fclose(f->handle);files[f->fd-3]=0;free(f);return r;
}
size_t fread(void *p,size_t s,size_t n,FILE *f) {
    if(!f || !f->handle || !s || n>UINT_MAX/s)return 0;
    size_t bytes=s*n,got=h1_fread(p,1,bytes,f->handle);
    if(got>bytes){f->error=1;return 0;}
    if(got<bytes)f->eof=1;
    return got/s;
}
size_t fwrite(const void *p,size_t s,size_t n,FILE *f) {
    if(!f || !f->handle || !s || n>UINT_MAX/s)return 0;
    size_t bytes=s*n,got=h1_fwrite(p,1,bytes,f->handle);
    if(got>bytes){f->error=1;return 0;}if(got<bytes)f->error=1;
    return got/s;
}
int fseek(FILE *f,long offset,int whence) {
    if(!f || !f->handle)return -1;
    int r=h1_fseek(f->handle,offset,whence);
    if(r<0){f->error=1;return -1;}f->eof=0;return 0;
}
long ftell(FILE *f){return f&&f->handle?h1_ftell(f->handle):-1;}
int fgetc(FILE *f){unsigned char c;return fread(&c,1,1,f)==1?c:EOF;}
char *fgets(char *p,int n,FILE *f){int i=0,c;while(i+1<n && (c=fgetc(f))!=EOF){p[i++]=(char)c;if(c=='\n')break;}if(n>0)p[i]=0;return i?p:0;}
int fputc(int c,FILE *f){unsigned char b=(unsigned char)c;return fwrite(&b,1,1,f)==1?b:EOF;}
int fputs(const char *s,FILE *f){return fwrite(s,1,strlen(s),f)==strlen(s)?0:EOF;}
int puts(const char *s){h1_ps1_log("%s",s);return 0;}
int putchar(int c){return c;}
int getchar(void){return EOF;}
char *ctime_r(const time_t *t,char *s){(void)t;strcpy(s,"Thu Jan 01 00:00:00 1970\n");return s;}
int fprintf(FILE *f,const char *fmt,...){char b[1024];va_list ap;va_start(ap,fmt);int n=vsnprintf(b,sizeof b,fmt,ap);va_end(ap);if(f&&f->handle)fwrite(b,1,(unsigned)n<sizeof b?(unsigned)n:sizeof b-1,f);return n;}
int sprintf(char *b,const char *fmt,...){va_list ap;va_start(ap,fmt);int n=vsnprintf(b,0x7fffffffu,fmt,ap);va_end(ap);return n;}
int feof(FILE *f){return f?f->eof:1;}
int ferror(FILE *f){return f?f->error:1;}
void rewind(FILE *f){fseek(f,0,SEEK_SET);}
int fileno(FILE *f){return f?f->fd:-1;}
int fsync(int fd){return fd>=3&&fd<35&&files[fd-3]?0:-1;}
int close(int fd){return fd>=3&&fd<35?fclose(files[fd-3]):-1;}
int fstat(int fd,struct stat *st){FILE *f=fd>=3&&fd<35?files[fd-3]:0;if(!f||!st)return -1;long pos=ftell(f);if(pos<0||fseek(f,0,SEEK_END))return -1;st->st_size=ftell(f);st->st_mtime=0;st->st_mode=0;return fseek(f,pos,SEEK_SET);}
int stat(const char *p,struct stat *st){FILE *f=fopen(p,"rb");if(!f)return -1;int r=fstat(fileno(f),st);fclose(f);return r;}
int mkdir(const char *p,unsigned mode){(void)p;(void)mode;return -1;}
int remove(const char *p){return h1_remove(p);}
void perror(const char *s){h1_ps1_log("IO_ERROR %s",s);}
void exit(int e){h1_ps1_escape(e?e:101);}
int abs(int n){return n<0?-n:n;}
long labs(long n){return n<0?-n:n;}
unsigned long strtoul(const char *s,char **e,int b){return (unsigned long)strtol(s,e,b);}
static unsigned random_state=1;
void srand(unsigned n){random_state=n;}
int rand(void){random_state=random_state*1103515245u+12345u;return (random_state>>16)&32767;}
int strncasecmp(const char *a,const char *b,size_t n){while(n--){int c=tolower((unsigned char)*a++),d=tolower((unsigned char)*b++);if(c!=d||!c)return c-d;}return 0;}
int strcasecmp(const char *a,const char *b){return strncasecmp(a,b,UINT_MAX);}
char *strdup(const char *s){char *p=malloc(strlen(s)+1);if(p)strcpy(p,s);return p;}
char *strncat(char *d,const char *s,size_t n){char *p=d+strlen(d);while(n--&&*s)*p++=*s++;*p=0;return d;}
size_t strspn(const char *s,const char *accept){size_t n=0;while(s[n]&&strchr(accept,s[n]))++n;return n;}
size_t strcspn(const char *s,const char *reject){size_t n=0;while(s[n]&&!strchr(reject,s[n]))++n;return n;}
char *strpbrk(const char *s,const char *set){while(*s){if(strchr(set,*s))return (char*)s;++s;}return 0;}
char *strtok(char *s,const char *sep){static char *next;if(!s)s=next;if(!s)return 0;s+=strspn(s,sep);if(!*s){next=0;return 0;}char *e=s+strcspn(s,sep);next=*e?e+1:0;*e=0;return s;}
void *memchr(const void *s,int c,size_t n){const unsigned char *p=s;while(n--){if(*p==(unsigned char)c)return (void*)p;++p;}return 0;}
char *strerror(int e){(void)e;return "H1 I/O error";}
/* Fields needed by ISO SYSTEM.CNF, BIOS services, and EXE parsing. */
int sscanf(const char *s,const char *fmt,...){
    int assigned=0;va_list ap;va_start(ap,fmt);
    while(*fmt){
        if(isspace(*fmt)){while(isspace(*fmt))++fmt;while(isspace(*s))++s;continue;}
        if(*fmt!='%'){if(*s++!=*fmt++)break;continue;}
        ++fmt;int suppress=*fmt=='*';if(suppress)++fmt;
        unsigned width=0;while(isdigit(*fmt))width=width*10u+(unsigned)(*fmt++-'0');if(!width)width=UINT_MAX;
        int lng=0;if(*fmt=='l'){lng=1;++fmt;}
        char c=*fmt++;if(c!='c')while(isspace(*s))++s;
        if(c=='s'||c=='c'){
            if(!*s)break;char *dst=suppress?0:va_arg(ap,char*);unsigned n=0;
            if(c=='c'&&width==UINT_MAX)width=1;
            while(n<width&&*s&&(c=='c'||!isspace(*s))){if(dst)dst[n]=*s;++s;++n;}
            if(dst&&c=='s')dst[n]=0;if(!suppress)++assigned;
        }else if(c=='d'||c=='u'||c=='x'||c=='i'){
            char *end;long v=strtol(s,&end,c=='x'?16:c=='i'?0:10);if(end==s)break;s=end;
            if(!suppress){if(lng)*va_arg(ap,long*)=v;else *va_arg(ap,int*)=(int)v;++assigned;}
        }else if(c=='%'){if(*s++!='%')break;}else break;
    }
    va_end(ap);return assigned;
}
int gettimeofday(struct timeval *tv,void *tz){(void)tz;unsigned t=get_ticks();tv->tv_sec=t/1000000u;tv->tv_usec=t%1000000u;return 0;}
int usleep(unsigned us){unsigned start=get_ticks();while(get_ticks()-start<us)h1_ps1_check_stop();return 0;}
/* Same hit operations and 16-byte coverage as H1Debug's verified EXEC path. */
int cacheflush(void *p,int n,int flags){
    (void)flags;uintptr_t a=(uintptr_t)p&~15u,end=((uintptr_t)p+(unsigned)n+15u)&~15u;
    __asm__ volatile("sync":::"memory");
    for(uintptr_t q=a;q<end;q+=16)__asm__ volatile("cache 0x15,0(%0)"::"r"(q):"memory");
    __asm__ volatile("sync":::"memory");
    for(uintptr_t q=a;q<end;q+=16)__asm__ volatile("cache 0x10,0(%0)"::"r"(q):"memory");
    __asm__ volatile("sync\n\tnop\n\tnop\n\tnop":::"memory");return 0;
}
