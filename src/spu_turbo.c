/* Lossy mono/22.05 kHz voice rendering; GPL-2.0-or-later.
 * ADPCM stepping and callback-visible state follow spu_fast.c. Only audio
 * rendering is thinned; emulated sample time, decoding and IRQs stay intact.
 */
#include "spu_turbo.h"
unsigned h1_spu_turbo_mode=1;
volatile unsigned h1_spu_turbo_stats[8] __attribute__((used,externally_visible));
void h1_spu_turbo_reset(void) {
    h1_spu_turbo_mode=1;
    for(unsigned n=0;n<8;++n)h1_spu_turbo_stats[n]=0;
}
void h1_spu_turbo_set(unsigned enabled) { h1_spu_turbo_mode=!!enabled; }

/* Keep both individual sample transitions, including every callback phase.
 * Pairing only removes half the waveform stores and outer-loop overhead. */
#define ADVANCE_ONE(sample) do { \
    phase+=step; \
    while(phase>=0x10000){ \
        value=history[offset++]; \
        if(offset>=28){ \
            *position=phase;*index=0; \
            int ended=decode(context,channel,history); \
            phase=*position;offset=*index; \
            if(ended&&(sample)<result)result=(sample); \
        } \
        phase-=0x10000; \
    } \
} while(0)

int h1_spu_samples_half(int (*decode)(void *,int,int *),void *context,
    int channel,int count,int *history,int step,int *position,int *index,int *output)
{
    int phase=*position,offset=*index,value=history[29],result=count;
    int n=0;
    for(;n+1<count;n+=2){
        ADVANCE_ONE(n);output[n]=value;
        ADVANCE_ONE(n+1);
    }
    if(n<count){ADVANCE_ONE(n);output[n]=value;}
    *position=phase;*index=offset;history[29]=value;
    return result;
}
int h1_spu_samples_quiet(int (*decode)(void *,int,int *),void *context,
    int channel,int count,int *history,int step,int *position,int *index)
{
    int phase=*position,offset=*index,value=history[29],result=count;
    for(int n=0;n<count;++n)ADVANCE_ONE(n);
    *position=phase;*index=offset;history[29]=value;
    return result;
}
#undef ADVANCE_ONE

void h1_spu_mix_half_mono(int *sum,int count,int left,int right,const int *voice)
{
    int gain=(left+right)/2;
    for(int n=0;n<count;n+=2){
        int value=voice[n]*gain>>14;
        sum[n*2]+=value;sum[n*2+1]+=value;
        if(n+1<count){sum[n*2+2]+=value;sum[n*2+3]+=value;}
    }
    h1_spu_turbo_stats[7]+=(count+1)/2;
}
void h1_spu_finish_mono(int *sum,int count,int volume,int enabled,short *out)
{
    for(int n=0;n<count;++n){
        int value=(int)((unsigned)sum[n*2]+(unsigned)sum[n*2+1])/2;
        sum[n*2]=sum[n*2+1]=0;
        value=enabled?(value*volume>>10):0;
        if(value>32767)value=32767;
        if(value< -32768)value=-32768;
        out[n*2]=out[n*2+1]=(short)value;
    }
}
