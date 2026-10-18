/* SDK STR stream wait HLE. GPL-2.0-or-later.
 * Recognizes executed instruction paths, not a game name or fixed address.
 * Batch only an empty queue, never data delivery, and stop before the next
 * emulated event. Timeout, all clobbered registers and guest cycles remain.
 */
#include "video_hle.h"
#include "r3000a.h"
#include "psxmem.h"
extern uint32_t cycle_multiplier;
extern "C" { volatile uint32_t h1_video_hle_stats[2] __attribute__((used,externally_visible)); }
struct Wait {uint32_t pc,helper,index,table,argument;unsigned counter;};
struct Token {Wait w;uint32_t head[8],first[12],second[5],ret[2];};
static Token tokens[64];
static unsigned token_count;
static uint32_t *ram(uint32_t address,unsigned bytes=4){
    unsigned segment=address&0xe0000000u,off=address&0x1fffffu;
    if((segment!=0&&segment!=0x80000000u&&segment!=0xa0000000u)||
       (address&3u)||(address&0x1fffffffu)>=0x800000u||off+bytes>0x200000u||!psxM)return 0;
    return (uint32_t*)(psxM+off);
}
static bool decode(unsigned pc,Wait &w){
    uint32_t *p=ram(pc,32);if(!p)return false;
    unsigned c=(p[5]>>16)&31u;
    if(c<9||c==29||c==31||p[5]!=(0x2400ffffu|(c<<21)|(c<<16))||
       p[0]>>16!=0x3c05||p[1]>>16!=0x24a5||p[2]>>26!=3||p[3]>>16!=0x27a4||
       p[4]>>16!=0x1040||p[6]>>16!=(0x1400u|(c<<5))||p[7]!=0x00001021u||
       pc+28u+(int16_t)p[6]*4u!=pc)return false;
    unsigned helper=((pc+12u)&0xf0000000u)|((p[2]&0x03ffffffu)<<2);
    uint32_t *q=ram(helper,196);if(!q)return false;
    if(q[0]!=0x00803821u||q[1]>>16!=0x3c02||q[2]>>16!=0x8c42||
       q[3]>>16!=0x3c03||q[4]>>16!=0x8c63||q[5]!=0x00021140u||q[6]!=0x00433021u||
       q[7]!=0x94c20000u||q[8]!=0x34030001u||q[9]!=0x3042ffffu||
       q[10]!=0x1443000eu||q[11]!=0x00a04021u||
       q[25]!=0x94c20000u||q[26]!=0x34030002u||q[27]!=0x3042ffffu||
       q[28]!=0x14430012u||q[29]!=0x34020001u||q[47]!=0x03e00008u||q[48])return false;
    unsigned index=((q[1]&65535u)<<16)+(int16_t)q[2];
    unsigned table=((q[3]&65535u)<<16)+(int16_t)q[4];
    if(!ram(index)||!ram(table))return false;
    w={pc,helper,index,table,((p[0]&65535u)<<16)+(int16_t)p[1],c};return true;
}
static bool unchanged(const Token &t){
    const uint32_t *p=ram(t.w.pc,32),*q=ram(t.w.helper,196);if(!p||!q)return false;
    uint32_t changed=0;
    for(unsigned i=0;i<8;++i)changed|=p[i]^t.head[i];
    for(unsigned i=0;i<12;++i)changed|=q[i]^t.first[i];
    for(unsigned i=0;i<5;++i)changed|=q[25+i]^t.second[i];
    return !(changed|(q[47]^t.ret[0])|(q[48]^t.ret[1]));
}
extern "C" int h1_ps1_video_hle_admit(unsigned pc){
    Wait w;if(!decode(pc,w))return 0;
    for(unsigned i=0;i<token_count;++i)if(tokens[i].w.pc==pc&&unchanged(tokens[i]))return i+1;
    if(token_count==64)return 0;
    Token &t=tokens[token_count++];t.w=w;
    const uint32_t *p=ram(pc),*q=ram(w.helper);
    for(unsigned i=0;i<8;++i)t.head[i]=p[i];
    for(unsigned i=0;i<12;++i)t.first[i]=q[i];
    for(unsigned i=0;i<5;++i)t.second[i]=q[25+i];
    t.ret[0]=q[47];t.ret[1]=q[48];return token_count;
}
extern "C" int h1_ps1_video_hle_execute(unsigned pc,unsigned token){
    if(!token||token>token_count||tokens[token-1].w.pc!=pc||!unchanged(tokens[token-1])){
        psxCpu->Clear(pc,8);psxRegs.pc=pc;return 1;
    }
    const Token &t=tokens[token-1];const Wait &w=t.w;
    uint32_t *index=ram(w.index),*table=ram(w.table);if(!index||!table)return 0;
    uint32_t record=*table+(*index<<5);
    uint32_t *state=ram(record);if(!state)return 0;
    unsigned tag=*state&65535u;if(tag==1||tag==2)return 0;
    unsigned cost=2u*((4u*cycle_multiplier)>>8)+((12u*cycle_multiplier)>>8)+
                  ((5u*cycle_multiplier)>>8)+((2u*cycle_multiplier)>>8);
    if(!cost||psxRegs.io_cycle_counter<=psxRegs.cycle)return 0;
    unsigned delta=psxRegs.io_cycle_counter-psxRegs.cycle,n=(delta-1u)/cost;
    if(n>65536u)n=65536u;
    uint32_t remaining=psxRegs.GPR.r[w.counter];
    if(remaining&&remaining<=n)n=remaining-1u;
    if(!n)return 0;
    psxRegs.GPR.r[2]=0;psxRegs.GPR.r[3]=2;
    psxRegs.GPR.r[4]=psxRegs.GPR.r[29]+(int16_t)t.head[3];
    psxRegs.GPR.r[5]=w.argument;psxRegs.GPR.r[6]=record;
    psxRegs.GPR.r[7]=psxRegs.GPR.r[4];psxRegs.GPR.r[8]=w.argument;
    psxRegs.GPR.r[w.counter]-=n;psxRegs.GPR.r[31]=pc+16u;
    psxRegs.pc=pc;psxRegs.cycle+=n*cost;
    ++h1_video_hle_stats[0];h1_video_hle_stats[1]+=n;return 1;
}
