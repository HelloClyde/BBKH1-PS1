/* Exact RAM stack countdown batching. GPL-2.0-or-later.
 * Six executed instructions, no fixed BIOS/game PC; guest time is preserved.
 * The zero/untaken iteration remains in the original compiled block. */
#include "delay_hle.h"
#include "r3000a.h"
#include "psxmem.h"
extern uint32_t cycle_multiplier;
extern "C" { volatile uint32_t h1_delay_hle_stats[2] __attribute__((used,externally_visible)); }
struct Token {uint32_t pc,words[6];unsigned a,b,c;int16_t displacement;};
static Token tokens[64];
static unsigned token_count;
static uint32_t *ram(uint32_t address,unsigned bytes=4){
    unsigned segment=address&0xe0000000u,off=address&0x1fffffu;
    if((segment!=0&&segment!=0x80000000u&&segment!=0xa0000000u)||
       (address&3u)||(address&0x1fffffffu)>=0x800000u||off+bytes>0x200000u||!psxM)return 0;
    return (uint32_t*)(psxM+off);
}
static bool unchanged(const Token &t){
    const uint32_t *p=ram(t.pc,24);if(!p)return false;
    uint32_t changed=0;for(unsigned i=0;i<6;++i)changed|=p[i]^t.words[i];return !changed;
}
extern "C" int h1_ps1_delay_hle_admit(unsigned pc){
    const uint32_t *p=ram(pc,24);if(!p)return 0;
    unsigned a=(p[0]>>16)&31u,b=(p[1]>>16)&31u,c=(p[3]>>16)&31u;
    if(!a||!b||!c||a==29||b==29||c==29||a==b||a==c||b==c||
       p[0]!=(0x8fa00000u|(a<<16)|(p[0]&65535u))||
       p[1]!=(0x8fa00000u|(b<<16)|(p[0]&65535u))||p[2]||
       p[3]!=(0x2400ffffu|(b<<21)|(c<<16))||
       p[4]!=(0x1400fffbu|(a<<21))||
       p[5]!=(0xafa00000u|(c<<16)|(p[0]&65535u)))return 0;
    for(unsigned i=0;i<token_count;++i)if(tokens[i].pc==pc&&unchanged(tokens[i]))return i+1;
    if(token_count==64)return 0;
    Token &t=tokens[token_count++];t.pc=pc;t.a=a;t.b=b;t.c=c;t.displacement=(int16_t)p[0];
    for(unsigned i=0;i<6;++i)t.words[i]=p[i];return token_count;
}
extern "C" int h1_ps1_delay_hle_execute(unsigned pc,unsigned token){
    if(!token||token>token_count||tokens[token-1].pc!=pc||!unchanged(tokens[token-1])){
        psxCpu->Clear(pc,6);psxRegs.pc=pc;return 1;
    }
    const Token &t=tokens[token-1];unsigned address=psxRegs.GPR.r[29]+t.displacement;
    uint32_t *slot=ram(address);unsigned off=address&0x1fffffu,head=pc&0x1fffffu;
    if(!slot||!psxRegs.writeok||(off>=head&&off<head+24u))return 0;
    uint32_t value=*slot;unsigned cost=(6u*cycle_multiplier)>>8;
    if(!value||!cost||psxRegs.io_cycle_counter<=psxRegs.cycle)return 0;
    unsigned delta=psxRegs.io_cycle_counter-psxRegs.cycle;
    unsigned n=(delta-1u)/cost;
    if(n>65536u)n=65536u;if(n>value)n=value;if(!n)return 0;
    *slot=value-n;
    psxRegs.GPR.r[t.a]=psxRegs.GPR.r[t.b]=value-n+1u;
    psxRegs.GPR.r[t.c]=value-n;
    psxRegs.pc=pc;psxRegs.cycle+=n*cost;
    ++h1_delay_hle_stats[0];h1_delay_hle_stats[1]+=n;return 1;
}
