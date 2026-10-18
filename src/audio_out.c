#include "h1_port.h"
#include "audio.h"
#include "out.h"
#include <stddef.h>
#include "spu_profile.h"
static int ready;
static int init(void){
#if !H1_BENCHMARK
    ready=gba_audio_open(44100);
#endif
    return 0;
}
static void finish(void){gba_audio_close();ready=0;}
static int busy(void){return ready&&gba_audio_wait();}
static void feed(void *p,int bytes){
    if(bytes<=0 || bytes%4)return;
    h1_ps1_stats.audio_samples+=(unsigned)bytes/4;
    H1_SPU_BEGIN(tick,HSP_FEED,1);
    if(ready)gba_audio_write(p,(size_t)bytes/4);
    H1_SPU_END(HSP_FEED,tick);
}
static struct out_driver driver={"H1 native PCM",init,finish,busy,feed};
struct out_driver *out_current=&driver;
void SetupSound(void){out_current=&driver;init();}
void h1_ps1_audio_close(void){finish();}
void h1_ps1_audio_pause(int pause){if(ready){if(pause)gba_audio_pause();else if(!gba_audio_resume())ready=gba_audio_open(44100);}}
