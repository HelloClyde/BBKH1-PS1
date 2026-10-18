#include "phase_profile.h"
#include "h1_port.h"
#include "h1_sdk.h"
#include "r3000a.h"
volatile uint32_t h1_phase_state[8] __attribute__((used,externally_visible)) =
    {0x31504850u,1,HPP_COUNT,HPP_BINS,0,0,0,0};
volatile uint32_t h1_phase_bins[HPP_BINS][HPP_COUNT][2]
    __attribute__((used,externally_visible));
extern "C" {
volatile uint32_t h1_phase_cpu_samples[1024][3] __attribute__((used,externally_visible));
volatile uint32_t h1_phase_cpu_meta[4] __attribute__((used,externally_visible))={0,0,0,1};
}
static unsigned bin,current,last,started,enabled;
static void account(unsigned now)
{
    unsigned delta=now-last;
    h1_phase_bins[bin][current][1]+=delta;
    // Attribute only otherwise-unwrapped slow-window intervals. This is a
    // cooperative boundary PC, not an interrupt sample of the host CPU PC.
    if(delta&&current==HPP_CPU&&bin>=65&&bin<88){
        unsigned pc=psxRegs.pc,key=pc|1u,index=((pc>>2)^(pc>>12))&1023u;
        h1_phase_cpu_meta[0]+=delta;++h1_phase_cpu_meta[1];
        unsigned n;
        for(n=0;n<32;++n,index=(index+1)&1023u){
            volatile uint32_t *p=h1_phase_cpu_samples[index];
            if(!p[0]||p[0]==key){p[0]=key;p[1]+=delta;++p[2];break;}
        }
        if(n==32)h1_phase_cpu_meta[2]+=delta;
    }
    last=now;h1_phase_state[5]=now;
}
static void start(unsigned now,unsigned frame)
{
    started=enabled=1;bin=frame/100u;last=now;
    h1_phase_state[4]=now;h1_phase_state[5]=now;h1_phase_state[7]=1;
}
unsigned h1_phase_enter(unsigned kind)
{
    if(h1_ps1_stats.state!=3||kind>=HPP_COUNT)return ~0u;
    if(!started){
        if(h1_ps1_stats.frames>=HPP_BINS*100u)return ~0u;
        start(h1_raw_tick_80hz(),h1_ps1_stats.frames);
    }
    if(!enabled)return ~0u;
    account(h1_raw_tick_80hz());
    unsigned previous=current;current=kind;
    ++h1_phase_bins[bin][kind][0];++h1_phase_state[6];return previous;
}
void h1_phase_leave(unsigned *previous)
{
    if(!enabled||*previous>=HPP_COUNT)return;
    account(h1_raw_tick_80hz());current=*previous;++h1_phase_state[6];
}
void h1_phase_frame(unsigned frame)
{
    if(!started){
        if(frame>=HPP_BINS*100u)return;
        start(h1_raw_tick_80hz(),frame);return;
    }
    if(!enabled)return;
    account(h1_raw_tick_80hz());
    if(frame>=HPP_BINS*100u){enabled=0;h1_phase_state[7]=0;return;}
    bin=frame/100u;
}
