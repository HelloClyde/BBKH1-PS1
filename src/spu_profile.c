#include "spu_profile.h"
#include "h1_port.h"
#include "h1_sdk.h"
volatile uint32_t h1_spu_profile[HSP_COUNT][3] __attribute__((used,externally_visible));
volatile uint32_t h1_spu_voice_histogram[25] __attribute__((used,externally_visible));
unsigned h1_spu_profile_begin(unsigned kind,unsigned stride)
{
    if(h1_ps1_stats.state!=3)return ~0u;
    unsigned call=h1_spu_profile[kind][0]++;
    if(call&(stride-1u))return ~0u;
    ++h1_spu_profile[kind][1];
    return h1_raw_tick_80hz();
}
void h1_spu_profile_end(unsigned kind,unsigned start)
{
    if(start!=~0u)h1_spu_profile[kind][2]+=h1_raw_tick_80hz()-start;
}
void h1_spu_profile_voices(unsigned mask)
{
    if(h1_ps1_stats.state!=3)return;
    unsigned count=0;mask&=0xffffffu;
    while(mask){mask&=mask-1u;++count;}
    ++h1_spu_voice_histogram[count];
}
