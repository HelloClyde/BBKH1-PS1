/* Recognized SDK movie gateways. GPL-2.0-or-later.
 * Keep CD/SPU/GPU events in the original core. Never substitute movie assets.
 * No fixed game PC: normalize address pairs, then recheck immutable code.
 */
#include "r3000a.h"
#include "psxmem.h"
#include <stdint.h>
#include <string.h>
extern uint32_t cycle_multiplier;
extern "C" int h1_ps1_vlc_core_admit(unsigned);
extern "C" int h1_ps1_vlc_core_execute(unsigned,unsigned);
extern "C" int h1_ps1_vlc_movie_body(unsigned,unsigned,unsigned);
extern "C" unsigned h1_ps1_movie_io_admit(unsigned);
extern "C" int h1_ps1_movie_io_execute(unsigned,unsigned);
extern "C" unsigned h1_ps1_movie_gpu_admit(unsigned);
extern "C" int h1_ps1_movie_gpu_execute(unsigned,unsigned);
extern "C" {volatile uint32_t h1_movie_hle_stats[16] __attribute__((used,externally_visible));}
extern "C" {volatile uint32_t h1_movie_output_pointer __attribute__((used,externally_visible));
volatile uint32_t h1_movie_output_bytes __attribute__((used,externally_visible));}
struct Movie {unsigned pc,limit,primary,secondary,context,core;uint32_t code[208];};
static Movie movies[16];static unsigned movie_count;
static uint8_t *ram(unsigned address,unsigned bytes,unsigned align=4){
    unsigned seg=address&0xe0000000u,off=address&0x1fffffu;
    if((seg!=0&&seg!=0x80000000u&&seg!=0xa0000000u)||(address&(align-1u))||
       (address&0x1fffffffu)>=0x800000u||bytes>0x200000u-off||!psxM)return 0;
    return (uint8_t*)psxM+off;
}
static unsigned pair(const uint32_t *p){return ((p[0]&65535u)<<16)+(int16_t)p[1];}
static bool overlap(unsigned a,unsigned n,unsigned b,unsigned m){
    a&=0x1fffffu;b&=0x1fffffu;return a<b+m&&b<a+n;
}
static unsigned cost(unsigned n){return (n*cycle_multiplier)>>8;}
static bool budget(unsigned n){return psxRegs.io_cycle_counter>psxRegs.cycle&&
    cost(n)&&cost(n)<psxRegs.io_cycle_counter-psxRegs.cycle;}
static bool same(const Movie &m){
    const uint32_t *p=(const uint32_t*)ram(m.pc,832);if(!p)return false;
    unsigned diff=0;for(unsigned i=0;i<208;++i)diff|=p[i]^m.code[i];return !diff;
}
static bool entry(unsigned x){
    switch(x){
    case 0:case 0x58:case 0x2d8:case 0x2e0:case 0x30c:return true;
    default:return false;
    }
}
static unsigned movie_admit(unsigned pc){
    for(unsigned i=0;i<movie_count;++i)if(entry(pc-movies[i].pc)&&same(movies[i]))return i+1;
    const uint32_t *p=(const uint32_t*)ram(pc,832);
    if(!p||p[0]>>16!=0x3c08||p[1]>>16!=0x2508||p[6]!=0x1480000fu||movie_count==16)return 0;
    unsigned a=2166136261u,b=0;
    for(unsigned i=0;i<208;++i){
        unsigned w=p[i];if(i<6||i==8||i==9||i==195||i==196)w&=0xffff0000u;
        a=(a^w)*16777619u;b=b*33u+w;
    }
    if(a!=0xc8c5c1c0u||b!=0x8e601867u||pair(p+8)!=pair(p+195))return 0;
    unsigned core=h1_ps1_vlc_core_admit(pc+0x1d0);if(!core)return 0;
    Movie &m=movies[movie_count++];m.pc=pc;m.limit=pair(p);m.primary=pair(p+2);
    m.secondary=pair(p+4);m.context=pair(p+8);m.core=core;
    memcpy(m.code,p,832);h1_movie_hle_stats[0]=movie_count;return movie_count;
}
static int movie_execute(unsigned pc,unsigned token){
    if(!token||token>movie_count||!entry(pc-movies[token-1].pc)||!same(movies[token-1])){
        if(token&&token<=movie_count)psxCpu->Clear(movies[token-1].pc,208);
        psxRegs.pc=pc;return 1;
    }
    const Movie &m=movies[token-1];unsigned x=pc-m.pc;uint32_t *r=psxRegs.GPR.r;
    if(!psxRegs.writeok)return 0;
    if(x==0){
        const uint32_t *limit=(const uint32_t*)ram(m.limit,4);if(!limit||!budget(r[4]?8u:22u))return 0;
        const uint32_t *saved=(const uint32_t*)ram(m.context,40);if(!r[4]&&!saved)return 0;
        r[8]=m.limit;r[6]=m.primary;r[7]=m.secondary;r[9]=*limit;
        psxRegs.cycle+=cost(8);++h1_movie_hle_stats[1];
        if(r[4]){psxRegs.pc=m.pc+0x58;return 1;}
        r[8]=m.context;r[4]=saved[0];r[5]=saved[1];r[2]=saved[2];r[3]=saved[3];
        r[12]=saved[4];r[13]=saved[5];r[15]=saved[7];r[24]=saved[8];r[25]=saved[9];
        r[9]+=r[9];r[14]=r[5]+r[9];psxRegs.cycle+=cost(14);psxRegs.pc=m.pc+0x1d0;
        ++h1_movie_hle_stats[2];return 1;
    }
    if(x==0x58){
        if(!budget(65))return 0;
        const uint16_t *src=(const uint16_t*)ram(r[4],12,2);uint16_t *dst=(uint16_t*)ram(r[5],4,2);
        if(!src||!dst||overlap(r[5],4,m.pc,832))return 0;
        uint32_t before[34];memcpy(before,r,sizeof(before));unsigned oldpc=psxRegs.pc,oldcycle=psxRegs.cycle;
        uint16_t old0=dst[0],old1=dst[1];unsigned out=r[5];
        r[13]=r[15]=r[24]=r[25]=0;r[9]+=r[9];r[14]=r[5]+r[9];
        r[8]=src[0];r[9]=src[1];r[12]=src[2];r[10]=src[3];r[2]=src[4];r[3]=src[5];
        r[10]-=3;r[12]<<=10;if((int32_t)r[10]>=0)r[13]=1;
        r[4]+=12;r[2]=(r[2]<<16)|r[3];r[3]=0;dst[0]=(uint16_t)r[8];dst[1]=(uint16_t)r[9];r[5]+=2;
        if(!h1_ps1_vlc_movie_body(m.pc+0xb4,m.core,23)){
            memcpy(r,before,sizeof(before));dst[0]=old0;dst[1]=old1;psxRegs.pc=oldpc;psxRegs.cycle=oldcycle;
            ++h1_movie_hle_stats[7];return 0;
        }
        psxCpu->Clear(out&~3u,((out&3u)+7u)/4u);++h1_movie_hle_stats[3];return 1;
    }
    if(x==0x30c){
        uint32_t *saved=(uint32_t*)ram(m.context,40);if(!saved||!budget(13)||overlap(m.context,40,m.pc,832))return 0;
        r[8]=m.context;saved[0]=r[4];saved[1]=r[5];saved[2]=r[2];saved[3]=r[3];
        saved[4]=r[12];saved[5]=r[13];saved[7]=r[15];saved[8]=r[24];saved[9]=r[25];
        r[2]=1;psxRegs.cycle+=cost(13);psxRegs.pc=r[31];psxCpu->Clear(m.context,10);
        ++h1_movie_hle_stats[4];return 1;
    }
    // Leave the final padding iteration and CP0 status transition to the
    // original JIT, including its exception checks and merged block cycles.
    if(x==0x2d8||x==0x2e0){
        unsigned n=x==0x2d8?64u:r[2];if(!n||n>64u||!cost(4)||!budget(6))return 0;
        unsigned available=(psxRegs.io_cycle_counter-psxRegs.cycle-1u)/cost(4);
        if(x==0x2d8){if(available<2)return 0;--available;}
        if(n>available)n=available;if(!n)return 0;
        uint16_t *dst=(uint16_t*)ram(r[5],n*2u,2);if(!dst||overlap(r[5],n*2u,m.pc,832))return 0;
        unsigned out=r[5];if(x==0x2d8){r[8]=0xfe00;r[2]=64;}
        for(unsigned i=0;i<n;++i)dst[i]=(uint16_t)r[8];
        r[5]+=2*n;r[2]-=n;psxRegs.pc=m.pc+0x2e0;
        psxRegs.cycle+=(x==0x2d8?cost(6)+(n-1)*cost(4):n*cost(4));
        psxCpu->Clear(out&~3u,((out&3u)+2*n+3u)/4u);h1_movie_hle_stats[5]+=n;return 1;
    }
    return 0;
}
extern "C" int h1_ps1_vlc_hle_admit(unsigned pc){
    unsigned movie=movie_admit(pc);if(movie)return (int)(0x80000000u|movie);
    unsigned io=h1_ps1_movie_io_admit(pc);if(io)return (int)(0x40000000u|io);
    unsigned gpu=h1_ps1_movie_gpu_admit(pc);return gpu?(int)(0x20000000u|gpu):h1_ps1_vlc_core_admit(pc);
}
extern "C" int h1_ps1_vlc_hle_execute(unsigned pc,unsigned token){
    if(token&0x80000000u)return movie_execute(pc,token&0x7fffffffu);
    if(token&0x40000000u)return h1_ps1_movie_io_execute(pc,token&0x3fffffffu);
    if(token&0x20000000u){
        // Non-movie image uploads retain their original compiled JIT path
        // and its normal code invalidation; the selected HLE still performs
        // its complete immutable-code and address checks.
        if(!h1_movie_output_bytes||(psxRegs.GPR.r[18]&0x1fffffu)!=h1_movie_output_pointer)return 0;
        return h1_ps1_movie_gpu_execute(pc,token&0x1fffffffu);
    }
    return h1_ps1_vlc_core_execute(pc,token);
}
