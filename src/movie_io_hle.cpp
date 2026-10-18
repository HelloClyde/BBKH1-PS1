/* Native SDK stream delivery and MDEC DMA gateways. GPL-2.0-or-later.
 * Real core MMIO handlers own DMA/MDEC/interrupt effects. Busy transfers
 * return to the original core; polling batches stop before its next event.
 */
#include "r3000a.h"
#include "psxmem.h"
#include <stdint.h>
#include <string.h>
extern uint32_t cycle_multiplier;
extern "C" volatile uint32_t h1_movie_hle_stats[16];
extern "C" volatile uint32_t h1_movie_output_pointer,h1_movie_output_bytes;
struct Io {unsigned pc,helper,kind,n,slots[6];uint32_t words[49],sync[38];};
static Io tokens[32];static unsigned used;
static uint32_t *ram(unsigned p,unsigned bytes=4){
    unsigned seg=p&0xe0000000u,off=p&0x1fffffu;
    if((seg!=0&&seg!=0x80000000u&&seg!=0xa0000000u)||(p&3u)||
       (p&0x1fffffffu)>=0x800000u||bytes>0x200000u-off||!psxM)return 0;
    return (uint32_t*)(psxM+off);
}
static unsigned pair(const uint32_t *p){return ((p[0]&65535u)<<16)+(int16_t)p[1];}
static bool overlap(unsigned a,unsigned n,unsigned b,unsigned m){
    a&=0x1fffffu;b&=0x1fffffu;return a<b+m&&b<a+n;
}
static unsigned cycles(unsigned n){return (n*cycle_multiplier)>>8;}
static bool budget(unsigned n){return psxRegs.io_cycle_counter>psxRegs.cycle&&cycles(n)&&
    cycles(n)<psxRegs.io_cycle_counter-psxRegs.cycle;}
static bool addresses(unsigned x,unsigned y){
    return x>>26==15&&(y>>26==9||y>>26==35||y>>26==43)&&((x>>16)&31u)==((y>>21)&31u);
}
static bool hash(const uint32_t *p,unsigned n,unsigned a0,unsigned b0){
    uint32_t a=2166136261u,b=0;
    for(unsigned i=0;i<n;++i){
        unsigned w=p[i];if((i+1<n&&addresses(p[i],p[i+1]))||(i&&addresses(p[i-1],p[i])))w&=0xffff0000u;
        if(w>>26==3)w&=0xfc000000u;
        a=(a^w)*16777619u;b=b*33u+w;
    }
    return a==a0&&b==b0;
}
static bool same(const Io &t){
    const uint32_t *p=ram(t.pc,t.n*4u),*q=t.kind?ram(t.helper,152):0;if(!p||(t.kind&&!q))return false;
    unsigned diff=0;for(unsigned i=0;i<t.n;++i)diff|=p[i]^t.words[i];
    if(t.kind)for(unsigned i=0;i<38;++i)diff|=q[i]^t.sync[i];return !diff;
}
extern "C" unsigned h1_ps1_movie_io_admit(unsigned pc){
    for(unsigned i=0;i<used;++i){
        const Io &t=tokens[i];unsigned stage=pc==t.pc?0:t.kind&&pc==t.helper+48?1:t.kind&&pc==t.helper+104?2:3;
        if(stage<3&&same(t))return (i+1)|(stage<<16);
    }
    const uint32_t *p=ram(pc,196);if(!p||used==32)return 0;
    unsigned kind,n;
    if(p[0]==0x00803821u&&p[5]==0x00021140u&&hash(p,49,0x852a4dd9u,0xedadc33au)){kind=0;n=49;}
    else if(p[0]==0x27bdffe0u&&p[1]==0xafb10014u&&p[5]>>26==3){
        if(hash(p,37,0x10f08a28u,0x11e2f8d1u)){kind=1;n=37;}
        else if(hash(p,36,0x57fc96efu,0x2a4a306cu)){kind=2;n=36;}else return 0;
    }else return 0;
    Io t={};t.pc=pc;t.kind=kind;t.n=n;
    if(kind){
        t.helper=((pc+24u)&0xf0000000u)|((p[5]&0x3ffffffu)<<2);
        const uint32_t *q=ram(t.helper,152);if(!q||!hash(q,38,kind==1?0x0dce54ddu:0xfb70c8abu,kind==1?0x63bbee0eu:0x5a1c1cf4u))return 0;
        if(pair(q+1)!=pair(q+26))return 0;
        t.slots[0]=pair(p+7);t.slots[1]=pair(p+14);t.slots[2]=pair(p+18);
        t.slots[3]=pair(p+22);t.slots[4]=pair(p+(kind==1?27:26));t.slots[5]=pair(q+1);
        memcpy(t.sync,q,152);
    }else{
        t.slots[0]=pair(p+1);t.slots[1]=pair(p+3);t.slots[2]=pair(p+12);t.slots[3]=pair(p+33);
        if(pair(p+14)!=t.slots[0]||pair(p+19)!=t.slots[0]||pair(p+37)!=t.slots[0]||
           pair(p+21)!=t.slots[1]||pair(p+35)!=t.slots[1])return 0;
    }
    memcpy(t.words,p,n*4u);tokens[used]=t;return ++used;
}
static int queue(const Io &t){
    uint32_t *g[4];for(unsigned i=0;i<4;++i){g[i]=ram(t.slots[i]);if(!g[i])return 0;}
    for(unsigned i=0;i<4;++i)for(unsigned j=0;j<i;++j)if(overlap(t.slots[i],4,t.slots[j],4))return 0;
    unsigned index=*g[0],base=*g[1],mode=*g[2],total=*g[3],address=base+(index<<5);
    uint32_t *old=ram(address),*first=ram(base);if(!old||!first||!budget(64))return 0;
    unsigned tag=*old&65535u,next=tag==1?(mode&&index==0?0u:*first&65535u):tag;
    unsigned record=tag==1?base:address;
    uint32_t *r=psxRegs.GPR.r,*out0=0,*out1=0;
    if(next==2){out0=ram(r[4]);out1=ram(r[5]);if(!out0||!out1)return 0;}
    unsigned writes[4]={tag==1?t.slots[0]:0,tag==1&&mode?address:0,next==2?record:0,0};
    for(unsigned i=0;i<3;++i)if(writes[i]){
        if(overlap(writes[i],4,t.pc,t.n*4u))return 0;
        for(unsigned j=0;j<4;++j)if(i!=0&&overlap(writes[i],4,t.slots[j],4))return 0;
    }
    if(next==2)for(unsigned out=0;out<2;++out)if(overlap(r[4+out],4,t.pc,t.n*4u))return 0;
    // Globals and records must not alias: cached reads remain valid until
    // both output stores. Output stores themselves retain original order.
    for(unsigned i=0;i<4;++i)if(overlap(t.slots[i],4,address,4)||overlap(t.slots[i],4,base,4))return 0;
    unsigned elapsed;
    if(tag!=1)elapsed=cycles(12)+(next==2?cycles(24):cycles(5)+cycles(2));
    else if(!mode)elapsed=cycles(18)+(next==2?cycles(30):cycles(11)+cycles(2));
    else elapsed=next==2?cycles(49):cycles(30)+cycles(2);
    if(!elapsed||elapsed>=psxRegs.io_cycle_counter-psxRegs.cycle)return 0;
    r[7]=r[4];r[8]=r[5];r[6]=record;
    if(tag==1){r[1]=(t.words[14]&65535u)<<16;*g[0]=0;index=0;if(mode)*old&=0xffff0000u;}
    r[3]=2;r[2]=1;
    if(next==2){
        uint32_t *state=ram(record);*state=(*state&0xffff0000u)|4u;r[2]=0;
        r[4]=(total<<5)+base;r[5]=index;r[3]=((index<<6)-index)<<5;r[4]+=r[3];
        *out0=r[4];*out1=r[6];psxCpu->Clear(r[7],1);psxCpu->Clear(r[8],1);psxCpu->Clear(record,1);
        ++h1_movie_hle_stats[8];
    }
    if(tag==1){psxCpu->Clear(t.slots[0],1);if(mode)psxCpu->Clear(address,1);}
    psxRegs.cycle+=elapsed;psxRegs.pc=r[31];return 1;
}
static int dma(const Io &t,unsigned stage){
    unsigned addr[6];for(unsigned i=0;i<6;++i){const uint32_t *p=ram(t.slots[i]);if(!p)return 0;addr[i]=*p;}
    const unsigned input[6]={0x1f8010f0,0x1f801080,0x1f801084,0x1f801820,0x1f801088,0x1f801824};
    const unsigned output[6]={0x1f8010f0,0x1f801098,0x1f801090,0x1f801094,0x1f801098,0x1f801098};
    const unsigned *expected=t.kind==1?input:output;
    for(unsigned i=0;i<6;++i)if(addr[i]!=expected[i])return 0;
    uint32_t *r=psxRegs.GPR.r;unsigned mask=t.kind==1?0x20000000u:0x01000000u;
    if(stage){
        uint32_t *counter=ram(r[29]+16u);if(!counter||r[3]!=mask||r[4]!=0xffffffffu||!cycles(8))return 0;
        if(overlap(r[29]+16u,4,t.pc,t.n*4u)||overlap(r[29]+16u,4,t.helper,152))return 0;
        for(unsigned i=0;i<6;++i)if(overlap(r[29]+16u,4,t.slots[i],4))return 0;
        unsigned value=psxMemRead32(addr[5]);if(!(value&mask)||!budget(stage==1?16u:8u))return 0;
        if(stage==2){r[2]=0;psxRegs.cycle+=cycles(8);psxRegs.pc=t.helper+48u;++h1_movie_hle_stats[11];return 1;}
        unsigned n=(psxRegs.io_cycle_counter-psxRegs.cycle-1u)/(2u*cycles(8));
        if(n>65536u)n=65536u;if(n>*counter)n=*counter;if(!n)return 0;
        *counter-=n;r[2]=0;psxRegs.cycle+=n*2u*cycles(8);psxRegs.pc=t.helper+48u;
        psxCpu->Clear(r[29]+16u,1);h1_movie_hle_stats[11]+=n;return 1;
    }
    if(!budget(96))return 0;
    uint32_t *stack=ram(r[29]-64u,64);unsigned bytes=(r[5]>>5)*128u;
    if((r[5]>>5)>0x200000u/128u||!stack||!ram(r[4],bytes+(t.kind==1?4u:0u)))return 0;
    if(overlap(r[29]-64u,64,t.pc,t.n*4u)||overlap(r[29]-64u,64,t.helper,152)||
       overlap(r[4],bytes+4u,r[29]-64u,64)||overlap(r[4],bytes+4u,t.pc,t.n*4u)||overlap(r[4],bytes+4u,t.helper,152))return 0;
    for(unsigned i=0;i<6;++i)if(overlap(t.slots[i],4,r[29]-64u,64)||
        (t.kind==2&&overlap(t.slots[i],4,r[4],bytes)))return 0;
    if(psxMemRead32(addr[5])&mask)return 0;
    unsigned original_sp=r[29],original_ra=r[31];
    stack[12]=r[16];stack[13]=r[17];stack[14]=original_ra;
    r[17]=r[4];r[16]=r[5];r[29]-=32;r[31]=t.pc+28u;
    psxRegs.cycle+=cycles(7);
    stack[4]=0x00100000u;stack[6]=r[31];
    // The helper's idle branch and epilogue are separate original blocks.
    r[2]=0;r[3]=mask;psxRegs.cycle+=cycles(11)+cycles(4);psxRegs.pc=t.pc+28u;
    r[3]=addr[0];r[2]=psxMemRead32(addr[0]);r[16]>>=5;r[2]|=0x88u;psxMemWrite32(r[3],r[2]);
    r[16]<<=16;
    if(t.kind==1){
        r[3]=addr[1];r[2]=r[17]+4u;psxMemWrite32(r[3],r[2]);
        r[2]=addr[2];r[16]|=32;psxMemWrite32(r[2],r[16]);
        r[3]=addr[3];r[2]=*ram(r[17]);r[4]=0x01000000u;psxMemWrite32(r[3],r[2]);
        r[2]=addr[4];r[4]|=0x201u;psxMemWrite32(r[2],r[4]);
    }else{
        r[2]=addr[1];psxMemWrite32(r[2],0);r[2]=addr[2];r[16]|=32;psxMemWrite32(r[2],r[17]);
        r[2]=addr[3];r[3]=0x01000000u;psxMemWrite32(r[2],r[16]);
        r[2]=addr[4];r[3]|=0x200u;psxMemWrite32(r[2],r[3]);
    }
    r[31]=stack[14];r[17]=stack[13];r[16]=stack[12];r[29]=original_sp;
    if(t.kind==2){h1_movie_output_pointer=r[4]&0x1fffffu;h1_movie_output_bytes=bytes;}
    psxRegs.cycle+=cycles(t.kind==1?30u:29u);psxRegs.pc=r[31];
    psxCpu->Clear(original_sp-64u,16);++h1_movie_hle_stats[t.kind==1?9:10];return 1;
}
extern "C" int h1_ps1_movie_io_execute(unsigned pc,unsigned token){
    unsigned stage=token>>16;token&=65535u;
    if(!token||token>used||!same(tokens[token-1])){
        if(token&&token<=used){psxCpu->Clear(tokens[token-1].pc,tokens[token-1].n);if(tokens[token-1].kind)psxCpu->Clear(tokens[token-1].helper,38);}
        psxRegs.pc=pc;return 1;
    }
    const Io &t=tokens[token-1];
    if(stage>2||pc!=(stage==0?t.pc:t.helper+(stage==1?48u:104u)))return 0;
    if(!psxRegs.writeok)return 0;
    return t.kind?dma(t,stage):queue(t);
}
