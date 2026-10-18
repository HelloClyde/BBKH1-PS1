#ifndef H1_PS1_PORT_INTERFACE
#define H1_PS1_PORT_INTERFACE
#include "h1_port.h"
unsigned get_ticks(void);
void wait_ticks(unsigned);
void pad_update(void);
unsigned short pad_read(int);
void video_flip(void);
void video_clear(void);
void port_printf(int,int,const char *);
extern unsigned short *SCREEN;
int state_load(int);
int state_save(int);
int SelectGame(void);
int GameMenu(void);
#define TPS 1000000u
#endif
