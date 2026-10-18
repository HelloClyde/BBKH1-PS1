/* Conservative batching of the SDK-style VSync wait with a stack timeout.
 * GPL-2.0-or-later. Recognition is instruction-based, never game/PC based.
 * Each batch stops at the same branch boundary as the next hardware event.
 */
#include "h1_port.h"
#include "r3000a.h"
#include "psxmem.h"
#include <stdint.h>
extern uint32_t cycle_multiplier;

struct WaitLoop {uint32_t head,tail,poll,slot;unsigned reg,limit,sentinel;};
struct Admission {WaitLoop loop;uint32_t head_words[6],tail_words[8];};
static Admission admissions[128];
static unsigned admission_count;
static uint32_t *ram(uint32_t address){
    unsigned segment=address&0xe0000000u;
    if((segment!=0&&segment!=0x80000000u&&segment!=0xa0000000u)||
       (address&3u)||(address&0x1fffffffu)>=0x800000u||!psxM)return 0;
    return (uint32_t*)(psxM+(address&0x1fffffu));
}
static bool decode(uint32_t pc,WaitLoop &d){
    uint32_t *p=ram(pc);if(!p||(pc&0x1fffffu)>0x1fffe8u)return false;
    unsigned reg=(p[0]>>16)&31u;
    if(!reg||reg==29||p[0]!=(0x3c000000u|(reg<<16)|(p[0]&65535u)))return false;
    if((p[1]&0xffff0000u)!=(0x8c000000u|(reg<<21)|(reg<<16))||p[2]||p[5])return false;
    unsigned limit=(p[3]>>16)&31u;
    if(limit==reg||p[3]!=((reg<<21)|(limit<<16)|(reg<<11)|0x2au))return false;
    if((p[4]&0xffff0000u)!=(0x14000000u|(reg<<21)))return false;
    uint32_t tail=pc+20u+(int16_t)p[4]*4u;
    uint32_t *q=ram(tail);if(!q||(tail&0x1fffffu)>0x1fffe0u)return false;
    if((q[0]&0xffff0000u)!=(0x8fa00000u|(reg<<16))||q[1]||q[5]||q[7])return false;
    if(q[2]!=(0x24000000u|(reg<<21)|(reg<<16)|65535u))return false;
    if(q[3]!=(0xafa00000u|(reg<<16)|(q[0]&65535u))||q[4]!=q[0])return false;
    unsigned sentinel=(q[6]>>16)&31u;
    if(sentinel==reg||q[6]!=(0x14000000u|(reg<<21)|(sentinel<<16)|(q[6]&65535u)))return false;
    if(tail+28u+(int16_t)q[6]*4u!=pc)return false;
    uint32_t poll=((p[0]&65535u)<<16)+(int16_t)p[1];
    if(!ram(poll))return false;
    d={pc,tail,poll,q[0]&65535u,reg,limit,sentinel};return true;
}
static bool unchanged(const Admission &a,const uint32_t *p,const uint32_t *q){
    if(!p||!q)return false;
    // Compare the exact instruction words, without decoding the same loop on
    // every event. These five delay/spacing instructions were admitted as NOP.
    uint32_t changed=p[2]|p[5]|q[1]|q[5]|q[7];
    changed|=(p[0]^a.head_words[0])|(p[1]^a.head_words[1])|
             (p[3]^a.head_words[3])|(p[4]^a.head_words[4]);
    changed|=(q[0]^a.tail_words[0])|(q[2]^a.tail_words[2])|
             (q[3]^a.tail_words[3])|(q[4]^a.tail_words[4])|(q[6]^a.tail_words[6]);
    return changed==0;
}
extern "C" int h1_ps1_idle_admit(unsigned pc){
    WaitLoop d;if(!decode(pc,d))return 0;
    uint32_t *p=ram(pc),*q=ram(d.tail);
    unsigned index=0;
    while(index<admission_count){
        if(admissions[index].loop.head==pc&&unchanged(admissions[index],p,q))return (int)index+1;
        ++index;
    }
    if(index==128)return 0;
    // Tokens baked into existing JIT blocks stay immutable after code changes.
    ++admission_count;admissions[index].loop=d;
    for(unsigned n=0;n<6;++n)admissions[index].head_words[n]=p[n];
    for(unsigned n=0;n<8;++n)admissions[index].tail_words[n]=q[n];
    return (int)index+1;
}
extern "C" int h1_ps1_idle_execute(unsigned pc,unsigned token){
    if(!token||token>admission_count||admissions[token-1].loop.head!=pc){
        psxCpu->Clear(pc,6);psxRegs.pc=pc;return 1;
    }
    const Admission &a=admissions[token-1];const WaitLoop &d=a.loop;
    if(!unchanged(a,ram(pc),ram(d.tail))){psxCpu->Clear(pc,6);psxRegs.pc=pc;return 1;}
    unsigned head_cost=(6u*cycle_multiplier)>>8,tail_cost=(8u*cycle_multiplier)>>8;
    uint32_t *poll=ram(d.poll);
    bool waiting=(int32_t)*poll<(int32_t)psxRegs.GPR.r[d.limit];
    if(!waiting||!head_cost||!tail_cost)return 0;
    uint32_t slot=psxRegs.GPR.r[29]+(int16_t)d.slot;
    uint32_t *counter=ram(slot);
    unsigned off=slot&0x1fffffu,h=pc&0x1fffffu,t=d.tail&0x1fffffu;
    // The emitter retains the original compiled block as the fallback.
    if(!counter||counter==poll||!psxRegs.writeok||
       psxRegs.GPR.r[d.sentinel]!=0xffffffffu||
       (off>=h&&off<h+24u)||(off>=t&&off<t+32u)||
       psxRegs.io_cycle_counter<=psxRegs.cycle||
       psxRegs.io_cycle_counter-psxRegs.cycle<=head_cost){
        return 0;
    }
    unsigned cost=head_cost+tail_cost;
    unsigned delta=psxRegs.io_cycle_counter-psxRegs.cycle;
    unsigned iterations=(delta-1u-head_cost)/cost+1u;
    // Avoid huge arithmetic/work if a malformed scheduler advertises infinity.
    if(iterations>65536u)iterations=65536u;
    uint32_t distance=*counter-0xffffffffu;
    // Leave the timeout iteration to the unmodified block: its untaken branch
    // may run into error handling before the next branch/event checkpoint.
    if(distance&&distance<=iterations)iterations=distance-1u;
    if(!iterations)return 0;
    *counter-=iterations;
    psxRegs.GPR.r[d.reg]=*counter;
    psxRegs.pc=pc;
    psxRegs.cycle+=iterations*cost;
    ++h1_ps1_stats.idle_batches;h1_ps1_stats.idle_iterations+=iterations;
    return 1;
}
