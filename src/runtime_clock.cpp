/* The same PCM quiesce / PLL / restore backend as the accepted 408 MHz run. */
#include "clock_control.h"
#include "h1_port.h"
#include "runtime_clock.h"
#include "hud.h"
void h1_runtime_clock_start(void){
    h1_ps1_audio_pause(1);
    int active=h1_clock_open(H1_CPU_MHZ);
    h1_ps1_audio_pause(0);
    h1_hud_reset();
    h1_ps1_log("CPU_CLOCK requested=%u active=%u state=%u error=%u",H1_CPU_MHZ,active,h1_clock_stats[2],h1_clock_stats[3]);
    if(!active&&h1_clock_stats[2]==4)h1_ps1_escape(30);
}
int h1_runtime_clock_stop(void){h1_ps1_audio_close();return h1_clock_close();}
