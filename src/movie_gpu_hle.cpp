/* Common SDK image-upload path, using original GPU/DMA handlers.
 * GPL-2.0-or-later. Clipping, partial DMA blocks and unsupported addresses
 * retain the original SDK; queue scheduling and callbacks are not bypassed.
 */
#include "r3000a.h"
#include "psxmem.h"
#include <stdint.h>
#include <string.h>
extern uint32_t cycle_multiplier;
extern "C" volatile uint32_t h1_movie_hle_stats[16];
extern "C" volatile uint32_t h1_movie_output_bytes;
struct Upload {unsigned pc,capw,caph,slots[5];uint32_t words[149];};
static Upload uploads[16];static unsigned used;
static uint8_t *ram(unsigned a,unsigned n,unsigned align=4){
    unsigned off=a&0x1fffffu,seg=a&0xe0000000u;
    if((seg!=0&&seg!=0x80000000u&&seg!=0xa0000000u)||(a&(align-1u))||
       (a&0x1fffffffu)>=0x800000u||n>0x200000u-off||!psxM)return 0;
    return (uint8_t*)psxM+off;
}
static unsigned pair(const uint32_t *p){return ((p[0]&65535u)<<16)+(int16_t)p[1];}
static bool overlap(unsigned a,unsigned n,unsigned b,unsigned m){a&=0x1fffffu;b&=0x1fffffu;return a<b+m&&b<a+n;}
static bool addresses(unsigned x,unsigned y){return x>>26==15&&(y>>26==9||y>>26==35||y>>26==43)&&((x>>16)&31u)==((y>>21)&31u);}
static bool same(const Upload &t){
    const uint32_t *p=(const uint32_t*)ram(t.pc,596);if(!p)return false;
    unsigned d=0;for(unsigned i=0;i<149;++i)d|=p[i]^t.words[i];return !d;
}
extern "C" unsigned h1_ps1_movie_gpu_admit(unsigned pc){
    for(unsigned i=0;i<used;++i)if(uploads[i].pc+44u==pc&&same(uploads[i]))return i+1;
    const uint32_t *p=(const uint32_t*)ram(pc-44u,596);
    if(!p||p[0]!=0x27bdffc0u||p[11]!=0x86240004u||p[12]!=0x0000a821u||used==16)return 0;
    unsigned a=2166136261u,b=0;
    for(unsigned i=0;i<149;++i){
        unsigned w=p[i];if((i+1<149&&addresses(p[i],p[i+1]))||(i&&addresses(p[i-1],p[i])))w&=0xffff0000u;
        if(w>>26==3)w&=0xfc000000u;a=(a^w)*16777619u;b=b*33u+w;
    }
    if(a!=0x316ccd5au||b!=0x0eb5dd65u)return 0;
    Upload t={};t.pc=pc-44u;t.capw=pair(p+15);t.caph=pair(p+32);
    t.slots[0]=pair(p+62);t.slots[1]=pair(p+87);t.slots[2]=pair(p+125);t.slots[3]=pair(p+130);t.slots[4]=pair(p+134);
    const unsigned controls[3]={75,83,121},data[4]={91,97,102,113};
    for(unsigned i=0;i<3;++i)if(pair(p+controls[i])!=t.slots[0])return 0;
    for(unsigned i=0;i<4;++i)if(pair(p+data[i])!=t.slots[1])return 0;
    memcpy(t.words,p,596);uploads[used]=t;return ++used;
}
static unsigned cycles(unsigned n){return (n*cycle_multiplier)>>8;}
extern "C" int h1_ps1_movie_gpu_execute(unsigned pc,unsigned token){
    if(!token||token>used||uploads[token-1].pc+44u!=pc||!same(uploads[token-1])){
        if(token&&token<=used)psxCpu->Clear(uploads[token-1].pc,149);psxRegs.pc=pc;return 1;
    }
    const Upload &t=uploads[token-1];uint32_t *r=psxRegs.GPR.r;
    if(!psxRegs.writeok||psxRegs.io_cycle_counter<=psxRegs.cycle||!cycles(128)||
       cycles(128)>=psxRegs.io_cycle_counter-psxRegs.cycle)return 0;
    uint16_t *rect=(uint16_t*)ram(r[17],8);const uint16_t *cw=(const uint16_t*)ram(t.capw,2,2),*ch=(const uint16_t*)ram(t.caph,2,2);
    uint32_t *stack=(uint32_t*)ram(r[29],64);if(!rect||!cw||!ch||!stack)return 0;
    int width=(int16_t)rect[2],height=(int16_t)rect[3];
    if(width<=0||height<=0||width>(int16_t)*cw||height>(int16_t)*ch)return 0;
    unsigned product=(unsigned)width*(unsigned)height,words=(product+1u)/2u;
    if(!words||(words&15u)||!ram(r[18],words*4u))return 0;
    if(overlap(r[17],8,r[29],64)||overlap(r[17],8,t.pc,596)||overlap(r[17],8,r[18],words*4u)||
       overlap(r[17],8,t.capw,2)||overlap(r[17],8,t.caph,2))return 0;
    unsigned io[5];const unsigned expected[5]={0x1f801814,0x1f801810,0x1f8010a0,0x1f8010a4,0x1f8010a8};
    for(unsigned i=0;i<5;++i){
        const uint32_t *p=(const uint32_t*)ram(t.slots[i],4);if(!p||*p!=expected[i]||overlap(r[17],8,t.slots[i],4))return 0;io[i]=*p;
    }
    // Positive, in-bounds, whole DMA blocks. Both clamping branches have
    // taken their common forward edges; original guest cycle rounding stays.
    r[21]=0;r[5]=(unsigned)height;r[6]=t.caph;rect[2]=(uint16_t)width;rect[3]=(uint16_t)height;
    r[32]=product;r[33]=0;r[4]=words;r[20]=words>>4;r[16]=0;r[3]=0x04000000u;
    psxRegs.cycle+=cycles(13)+cycles(13)+cycles(12);psxRegs.pc=t.pc+236u;
    unsigned status=psxMemRead32(io[0]);r[2]=status&0x04000000u;r[4]=0xa0000000u;
    psxCpu->Clear(r[17],2);
    if(!r[2]){
        r[19]=0x04000000u;r[31]=t.pc+292u;
        psxRegs.cycle+=cycles(14);psxRegs.pc=((t.pc+288u)&0xf0000000u)|((t.words[71]&0x3ffffffu)<<2);return 1;
    }
    psxRegs.cycle+=cycles(11);psxRegs.pc=t.pc+332u;
    r[3]=io[0];r[2]=0x04000000u;psxMemWrite32(r[3],r[2]);
    r[3]=io[1];r[2]=0x01000000u;psxMemWrite32(r[3],r[2]);r[2]=io[1];
    // The original JIT converts the short s5 conditional to a CMOV and
    // merges these command stores with the following taken branch.
    psxMemWrite32(r[2],r[4]);r[3]=io[1];r[2]=*(const uint32_t*)rect;psxMemWrite32(r[3],r[2]);
    r[3]=io[1];r[2]=*(const uint32_t*)(rect+2);r[16]=0xffffffffu;psxMemWrite32(r[3],r[2]);r[2]=0xffffffffu;
    psxRegs.cycle+=cycles(27);psxRegs.pc=t.pc+476u;
    r[3]=0x04000002u;r[2]=io[0];psxMemWrite32(r[2],r[3]);
    r[2]=io[2];r[4]=0x01000000u;psxMemWrite32(r[2],r[18]);
    r[2]=(r[20]<<16)|16u;r[3]=io[3];psxMemWrite32(r[3],r[2]);
    r[2]=io[4];r[4]|=0x201u;psxMemWrite32(r[2],r[4]);r[2]=0;
    r[31]=stack[14];r[21]=stack[13];r[20]=stack[12];r[19]=stack[11];r[18]=stack[10];r[17]=stack[9];r[16]=stack[8];r[29]+=64;
    psxRegs.cycle+=cycles(30);psxRegs.pc=r[31];h1_movie_output_bytes=0;++h1_movie_hle_stats[12];return 1;
}
