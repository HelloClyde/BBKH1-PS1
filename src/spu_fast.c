/* Exact non-interpolated voice stepping, GPL-2.0-or-later.
 * Based on PCSX-ReARMed/PCSX4ALL's make_do_samples(noint) semantics.
 * Keep phase/index in native registers between ADPCM callbacks. Publish and
 * reload both at every callback so IRQ/callback-visible state is preserved.
 */
#include "spu_fast.h"
int h1_spu_samples_noint(int (*decode)(void *,int,int *),void *context,
    int channel,int count,int *history,int step,int *position,int *index,int *output)
{
    int phase=*position,offset=*index,value=history[29],result=count;
    for(int n=0;n<count;++n){
        phase+=step;
        while(phase>=0x10000){
            value=history[offset++];
            if(offset>=28){
                *position=phase;*index=0;
                int ended=decode(context,channel,history);
                phase=*position;offset=*index;
                if(ended&&n<result)result=n;
            }
            phase-=0x10000;
        }
        output[n]=value;
    }
    *position=phase;*index=offset;history[29]=value;
    return result;
}
