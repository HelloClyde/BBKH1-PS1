/* Two alternating checked records; failed writes retain the previous slot. */
#include "h1_sdk.h"
#include "settings.h"
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#ifndef H1_AUDIO_TURBO
#define H1_AUDIO_TURBO 0
#endif

h1_settings_t h1_settings;
typedef char settings_size_check[sizeof(h1_settings_t)==56?1:-1];
typedef struct {
    uint32_t magic,version,sequence;
    h1_settings_t settings;
    char game[240];
    uint32_t checksum;
} record_t;
static char game_path[240],slots[2][40];
static unsigned ready,dirty,writable,sequence,active_slot=1;
static unsigned checksum(const void *data,unsigned size){
    const uint8_t *p=(const uint8_t *)data;unsigned c=~0u;
    while(size--){c^=*p++;for(unsigned b=0;b<8;++b)c=(c>>1)^(0xedb88320u&(0u-(c&1)));}
    return ~c;
}
int h1_key_reserved(unsigned key){
    return !key||key>42||key==H1_KEY_ESCAPE||key==H1_KEY_BACK||key==H1_KEY_P||
        key==H1_KEY_F||key==H1_KEY_G||key==H1_KEY_H||key==H1_KEY_T;
}
static int default_bit(unsigned k){
    switch(k){case H1_KEY_SPACE:return 0;case H1_KEY_ENTER:case H1_KEY_CONFIRM:return 3;
    case H1_KEY_UP:return 4;case H1_KEY_RIGHT:return 5;case H1_KEY_DOWN:return 6;case H1_KEY_LEFT:return 7;
    case H1_KEY_Q:return 8;case H1_KEY_W:return 9;case H1_KEY_A:return 10;case H1_KEY_S:return 11;
    case H1_KEY_V:return 12;case H1_KEY_C:return 13;case H1_KEY_Z:return 14;case H1_KEY_X:return 15;default:return -1;}
}
void h1_mapping_defaults(void){
    memset(h1_settings.mapping,0,sizeof h1_settings.mapping);
    for(unsigned k=1;k<=42;++k){int b=default_bit(k);if(b>=0)h1_settings.mapping[k]=(uint8_t)(b+1);}
    dirty=1;
}
void h1_settings_ensure(void){
    if(ready)return;ready=1;memset(&h1_settings,0,sizeof h1_settings);h1_mapping_defaults();
    h1_settings.volume=100;h1_settings.gpu_skip=H1_GPU_SKIP;h1_settings.lcd_skip=H1_GPU_SKIP?0:1;
    h1_settings.turbo=H1_AUDIO_TURBO?1:0;h1_settings.hud=1;dirty=0;
}
int h1_mapping_assign(unsigned bit,unsigned key){
    h1_settings_ensure();if(bit>15||bit==1||bit==2||h1_key_reserved(key))return 0;
    for(unsigned k=1;k<=42;++k)if(h1_settings.mapping[k]==bit+1)h1_settings.mapping[k]=0;
    h1_settings.mapping[key]=(uint8_t)(bit+1);dirty=1;return 1;
}
static int valid(const h1_settings_t *s){
    if(s->mapping[0]||s->volume>100||s->volume_set>1||s->mute>1||s->gpu_skip>3||s->lcd_skip>2||s->quality>1||s->turbo>1||s->hud>1)return 0;
    for(unsigned k=1;k<45;++k)if(s->mapping[k]>16||s->mapping[k]==2||s->mapping[k]==3||(h1_key_reserved(k)&&s->mapping[k]))return 0;
    for(unsigned k=0;k<sizeof s->reserved;++k)if(s->reserved[k])return 0;
    return 1;
}
/* 0 missing, 1 valid, -1 corrupt/foreign. Do not overwrite a foreign path. */
static int read_record(unsigned slot,record_t *r){
    FILE *f=fopen(slots[slot],"rb");if(!f)return 0;
    int ok=fread(r,1,sizeof *r,f)==sizeof *r&&fgetc(f)==EOF;int closed=fclose(f);
    if(!ok||closed||r->magic!=0x31434650u||r->version!=1||r->checksum!=checksum(r,offsetof(record_t,checksum))||!valid(&r->settings))return -1;
    return !memcmp(r->game,game_path,sizeof game_path)?1:-2;
}
void h1_settings_load(const char *game){
    ready=0;h1_settings_ensure();writable=0;sequence=0;active_slot=1;memset(game_path,0,sizeof game_path);
    unsigned n=0;while(game[n]&&n+1<sizeof game_path){unsigned c=(uint8_t)game[n];game_path[n]=(char)(c=='/'?'\\':c>='A'&&c<='Z'?c+32:c);++n;}
    if(game[n]||!n)return;
    unsigned hash=checksum(game_path,n);
    for(unsigned slot=0;slot<2;++slot)snprintf(slots[slot],sizeof slots[slot],"A:\\PS1\\cfg-%08x.%u",hash,slot);
    record_t a,b;int x=read_record(0,&a),y=read_record(1,&b);
    if(x==1||y==1){
        active_slot=y==1&&(x!=1||(int32_t)(b.sequence-a.sequence)>0)?1:0;
        const record_t *chosen=active_slot?&b:&a;h1_settings=chosen->settings;sequence=chosen->sequence;writable=1;
    }else writable=x==0&&y==0;
    if(x==-2||y==-2)writable=0;
    dirty=0;
}
void h1_settings_changed(void){dirty=1;}
int h1_settings_writable(void){return (int)writable;}
int h1_settings_save(void){
    if(!dirty)return 0;if(!writable||!valid(&h1_settings))return -1;
    record_t r,check;memset(&r,0,sizeof r);r.magic=0x31434650u;r.version=1;r.sequence=sequence+1;
    r.settings=h1_settings;memcpy(r.game,game_path,sizeof r.game);r.checksum=checksum(&r,offsetof(record_t,checksum));
    unsigned next=active_slot^1;FILE *f=fopen(slots[next],"wb");if(!f)return -1;
    int ok=fwrite(&r,1,sizeof r,f)==sizeof r;int closed=fclose(f);
    if(!ok||closed||read_record(next,&check)!=1||memcmp(&r,&check,sizeof r))return -1;
    active_slot=next;sequence=r.sequence;dirty=0;return 0;
}
