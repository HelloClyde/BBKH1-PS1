/* Bounded PCM starvation / synchronous disc latency trace. No file logging
 * on the audio path. Diagnostic builds only; raw ticks are about 40 Hz. */
#include "audio_diag.h"
#include "h1_port.h"
#include "h1_sdk.h"
#include <string.h>
#define CAPACITY 128u
volatile unsigned h1_audio_diag_state[16] __attribute__((used,externally_visible));
volatile unsigned h1_audio_diag_gaps[CAPACITY][16] __attribute__((used,externally_visible));
static unsigned last_tick,last_reads,last_io,last_gpu,last_spu,last_video;
static unsigned io_tick,io_lba,io_ticks,have_tick;
void h1_audio_diag_reset(void)
{
    memset((void*)h1_audio_diag_state,0,sizeof h1_audio_diag_state);
    memset((void*)h1_audio_diag_gaps,0,sizeof h1_audio_diag_gaps);
    h1_audio_diag_state[0]=0x31474150u;h1_audio_diag_state[1]=1;
    h1_audio_diag_state[2]=16;h1_audio_diag_state[3]=CAPACITY;
    last_tick=last_reads=last_io=last_gpu=last_spu=last_video=0;
    io_tick=io_lba=io_ticks=have_tick=0;
}
void h1_audio_diag_io(unsigned lba,unsigned ticks)
{
    ++h1_audio_diag_state[6];h1_audio_diag_state[7]+=ticks;
    if(ticks>h1_audio_diag_state[8])h1_audio_diag_state[8]=ticks;
    unsigned bin=ticks<3?ticks:ticks<=4?3:ticks<=8?4:5;
    ++h1_audio_diag_state[9+bin];
    io_tick=h1_raw_tick_80hz();io_lba=lba;io_ticks=ticks;
}
void h1_audio_diag_retire(unsigned consumed,unsigned queued,unsigned old_position,unsigned position)
{
    (void)old_position;(void)position;
    unsigned now=h1_raw_tick_80hz(),reads=h1_audio_diag_state[6],io=h1_audio_diag_state[7];
    ++h1_audio_diag_state[5];
    if(consumed>queued && h1_ps1_stats.state==3){
        unsigned n=h1_audio_diag_state[4]++;
        volatile unsigned *p=h1_audio_diag_gaps[n%CAPACITY];
        p[0]=h1_ps1_stats.frames;p[1]=now;p[2]=consumed;p[3]=queued;p[4]=consumed-queued;
        p[5]=have_tick?now-last_tick:0;p[6]=reads-last_reads;p[7]=io-last_io;
        p[8]=h1_ps1_stats.gpu_ticks-last_gpu;p[9]=h1_ps1_stats.spu_ticks-last_spu;
        p[10]=h1_ps1_stats.video_ticks-last_video;p[11]=reads?now-io_tick:~0u;
        p[12]=io_lba;p[13]=io_ticks;p[14]=0;p[15]=0;
    }
    last_tick=now;last_reads=reads;last_io=io;have_tick=1;
    last_gpu=h1_ps1_stats.gpu_ticks;last_spu=h1_ps1_stats.spu_ticks;last_video=h1_ps1_stats.video_ticks;
}
void h1_audio_diag_gap_finish(void)
{
    unsigned n=h1_audio_diag_state[4];if(!n)return;
    volatile unsigned *p=h1_audio_diag_gaps[(n-1)%CAPACITY];
    p[14]=h1_raw_tick_80hz()-p[1];
}
