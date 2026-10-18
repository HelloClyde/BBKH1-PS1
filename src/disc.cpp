/* Cached BIN/ISO/CUE reader for H1. GPL-2.0-or-later. */
#include "h1_sdk.h"
#include "plugins.h"
#include "cdriso.h"
#include "ppf.h"
#include "h1_port.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

static char iso[240];
static s64 open_time;
struct Track {char path[240];unsigned base,first,start,end,file_end,stride,audio;};
static Track tracks[100];
static unsigned ntracks,total_sectors,play_pos,playing,play_cycle;
static FILE *data_file,*audio_file;
static char data_path[240],audio_path[240];
static uint8_t cache[32*2352] __attribute__((aligned(32)));
static unsigned cache_base=~0u,cache_count,cache_stride;
static uint8_t sector[2352] __attribute__((aligned(32)));
static int16_t audio_sector[1176] __attribute__((aligned(32)));
static uint8_t *get_buffer(void){return sector+12;}
unsigned char *(*CDR_getBuffer)(void)=get_buffer;
unsigned char *sbi_sectors;
void (CALLBACK *cdrIsoMultidiskCallback)(void);
unsigned int cdrIsoMultidiskCount=1,cdrIsoMultidiskSelect;

static unsigned msf(unsigned m,unsigned s,unsigned f){return (m*60+s)*75+f;}
static unsigned unbcd(unsigned b){return (b>>4)*10+(b&15);}
static unsigned bcd(unsigned b){return ((b/10)<<4)|(b%10);}
static bool join(char *out,const char *cue,const char *name){
    if(strlen(name)>=240)return false;
    if(name[0]&&name[1]==':'){strcpy(out,name);return true;}
    unsigned end=0;
    // A GBK trail byte 0x5c is not a directory separator.
    for(unsigned i=0;cue[i];++i){unsigned c=(unsigned char)cue[i],d=(unsigned char)cue[i+1];
        if(c>=0x81&&c<=0xfe&&d>=0x40&&d<=0xfe&&d!=0x7f){++i;continue;}
        if(c=='\\'||c=='/')end=i+1;}
    if(end+strlen(name)>=240)return false;
    memcpy(out,cue,end);strcpy(out+end,name);return true;
}
static long file_size(const char *p){FILE *f=fopen(p,"rb");if(!f)return -1;long size=fseek(f,0,SEEK_END)?-1:ftell(f);fclose(f);return size;}
static int parse_cue(void){
    FILE *f=fopen(iso,"rb");if(!f)return -1;
    char line[512],current[240]={0};unsigned base=150,previous_file_sectors=0;
    int result=-1;
    while(fgets(line,sizeof line,f)){
        char *p=line;while(*p==' '||*p=='\t')++p;
        if(!strncmp(p,"FILE ",5)){
            char *q=strchr(p,'"'),*e=q?strchr(q+1,'"'):0;
            if(!q||!e)goto done;*e=0;
            base+=previous_file_sectors;
            if(!join(current,iso,q+1))goto done;
            long size=file_size(current);if(size<=0||size%2352)goto done;
            previous_file_sectors=(unsigned)size/2352;
        }else if(!strncmp(p,"TRACK ",6)){
            unsigned t=0;char mode[32]={0};if(sscanf(p,"TRACK %u %31s",&t,mode)!=2||t!=ntracks+1||t>99||!current[0])goto done;
            if(strcmp(mode,"MODE2/2352")&&strcmp(mode,"MODE1/2352")&&strcmp(mode,"AUDIO"))goto done;
            Track &tr=tracks[++ntracks];strcpy(tr.path,current);tr.base=base;tr.first=tr.start=~0u;
            tr.file_end=base+previous_file_sectors;tr.stride=2352;tr.audio=!strcmp(mode,"AUDIO");
        }else if(!strncmp(p,"INDEX ",6)){
            unsigned idx,m,s,fr;if(!ntracks||sscanf(p,"INDEX %u %u:%u:%u",&idx,&m,&s,&fr)!=4||s>=60||fr>=75)goto done;
            if(idx==0)tracks[ntracks].first=base+msf(m,s,fr);
            if(idx==1){tracks[ntracks].start=base+msf(m,s,fr);if(tracks[ntracks].first==~0u)tracks[ntracks].first=tracks[ntracks].start;}
        }else if(!strncmp(p,"PREGAP ",7)){
            // External pregaps require a separate mapping. Reject explicitly.
            h1_ps1_log("CUE_UNSUPPORTED external_pregap");goto done;
        }
    }
    if(!ntracks||tracks[1].audio)goto done;
    total_sectors=base+previous_file_sectors;
    for(unsigned t=1;t<=ntracks;++t){
        Track &tr=tracks[t];tr.end=t<ntracks?tracks[t+1].first:total_sectors;
        if(tr.first<tr.base||tr.first>tr.start||tr.start>=tr.end||tr.end>tr.file_end)goto done;
    }
    result=0;
done:fclose(f);return result;
}
void SetIsoFile(const char *p){if(!p){iso[0]=0;return;}if(strlen(p)<sizeof iso)strcpy(iso,p);else iso[0]=0;}
const char *GetIsoFile(void){return iso;}
boolean UsingIso(void){return iso[0]!=0;}
void SetCdOpenCaseTime(s64 t){open_time=t;}s64 GetCdOpenCaseTime(void){return open_time;}
long CDR_init(void){return 0;}
long CDR_close(void){if(data_file)fclose(data_file);if(audio_file)fclose(audio_file);data_file=audio_file=0;data_path[0]=audio_path[0]=0;cache_base=~0u;cache_count=0;playing=0;return 0;}
long CDR_shutdown(void){return CDR_close();}
long CDR_open(void){
    CDR_close();ntracks=0;total_sectors=0;memset(tracks,0,sizeof tracks);
    const char *ext=strrchr(iso,'.');
    if(ext&&!strcasecmp(ext,".cue")){if(parse_cue())return -1;}
    else{
        long size=file_size(iso);if(size<=0)return -1;
        unsigned stride=ext&&!strcasecmp(ext,".iso")?2048:2352;
        if((unsigned)size%stride)return -1;
        ntracks=1;strcpy(tracks[1].path,iso);tracks[1].base=tracks[1].first=tracks[1].start=150;tracks[1].stride=stride;
        tracks[1].end=total_sectors=150+(unsigned)size/stride;
    }
    h1_ps1_log("DISC tracks=%u sectors=%u stride=%u",ntracks,total_sectors,tracks[1].stride);return 0;
}
static Track *locate(unsigned lba){for(unsigned t=ntracks;t>0;--t)if(lba>=tracks[t].first&&lba<tracks[t].end)return &tracks[t];return 0;}
static int read_sector(unsigned lba,uint8_t *dest,bool audio){
    Track *tr=locate(lba);if(!tr||lba<tr->base)return -1;
    FILE **fp=audio?&audio_file:&data_file;char *path=audio?audio_path:data_path;
    if(!*fp||strcmp(path,tr->path)){
        if(*fp)fclose(*fp);*fp=fopen(tr->path,"rb");if(!*fp)return -1;
        strcpy(path,tr->path);if(!audio){cache_base=~0u;cache_count=0;}
    }
    unsigned raw=lba-tr->base;
    if(!audio&&cache_stride==tr->stride&&raw>=cache_base&&raw-cache_base<cache_count){
        memcpy(dest,cache+(raw-cache_base)*tr->stride,tr->stride);++h1_ps1_stats.disc_hits;return (int)tr->stride;
    }
    unsigned tick=h1_raw_tick_80hz();
    if(raw>INT_MAX/tr->stride||fseek(*fp,(long)(raw*tr->stride),SEEK_SET))return -1;
    unsigned count=audio?1:32;if(count>tr->end-lba)count=tr->end-lba;
    size_t got=fread(audio?dest:cache,tr->stride,count,*fp);
    ++h1_ps1_stats.disc_reads;h1_ps1_stats.disc_ticks+=h1_raw_tick_80hz()-tick;
    if(!got)return -1;
    if(!audio){cache_base=raw;cache_stride=tr->stride;cache_count=(unsigned)got;memcpy(dest,cache,tr->stride);}
    return (int)tr->stride;
}
long CDR_readTrack(unsigned char *t){
    unsigned lba=msf(unbcd(t[0]),unbcd(t[1]),unbcd(t[2]));
    memset(sector,0,sizeof sector);int stride=read_sector(lba,sector,false);if(stride<0)return -1;
    if(stride==2048){memmove(sector+24,sector,2048);memset(sector,0,24);sector[15]=2;}
    else if(sector[15]==1){memmove(sector+24,sector+16,2048);memset(sector+16,0,8);sector[15]=2;}
    sector[12]=t[0];sector[13]=t[1];sector[14]=t[2];return 0;
}
long CDR_getTN(unsigned char *b){b[0]=1;b[1]=(unsigned char)(ntracks?ntracks:1);return 0;}
long CDR_getTD(unsigned char track,unsigned char *b){if(track>ntracks)return -1;unsigned lba=track?tracks[track].start:total_sectors;b[2]=lba/4500;b[1]=(lba/75)%60;b[0]=lba%75;return 0;}
unsigned char *CDR_getBufferSub(void){return 0;}
long CDR_play(unsigned char *t){play_pos=msf(t[0],t[1],t[2]);playing=1;play_cycle=psxRegs.cycle;return 0;}
long CDR_stop(void){playing=0;return 0;}
extern "C" void h1_ps1_disc_pump(void){
    if(!playing)return;
    unsigned count=0;
    while((unsigned)(psxRegs.cycle-play_cycle)>=PSXCLK/75 && count++<3){
        Track *tr=locate(play_pos);if(!tr||!tr->audio){playing=0;break;}
        if(read_sector(play_pos,(uint8_t*)audio_sector,true)<0){playing=0;break;}
        if(SPU_playCDDAchannel(audio_sector,2352)!=0x676f)break;
        play_cycle+=PSXCLK/75;++play_pos;
    }
}
extern "C" void h1_ps1_disc_adjust(unsigned previous){if(playing)play_cycle-=previous;}
long CDR_getStatus(struct CdrStat *st){st->Status=open_time<0||open_time>(s64)time(0)?0x10:0;st->Type=playing?2:1;if(playing)st->Status|=0x80;st->Time[0]=play_pos/4500;st->Time[1]=(play_pos/75)%60;st->Time[2]=play_pos%75;return 0;}
void cdrIsoInit(void){}int cdrIsoActive(void){return 1;}
int ReloadCdromPlugin(void){CDR_close();return (int)CDR_open();}
void BuildPPFCache(void){}void FreePPFCache(void){}void CheckPPFCache(unsigned char*,unsigned char,unsigned char,unsigned char){}
int LoadSBI(const char*,int){return -1;}void UnloadSBI(void){}
