/* Bounded physical clock experiment. No filesystem I/O in the measured
 * window, and no dependency on live USB polls. An exit checkpoint precedes
 * PCM shutdown and restoration; the final journal follows resource cleanup. */
#include "h1_sdk.h"
#include "h1_port.h"
#include "clock_control.h"
#include "clock_run.h"
#include <stdio.h>
enum { ROW_WORDS=47, MAX_ROWS=121 };
static unsigned rows[MAX_ROWS][ROW_WORDS],count,attempted,closed=1;
static unsigned header[8],final_audio[12];
void h1_clock_run_frame(unsigned frame){
    if(frame==2400 && !attempted){
        attempted=1;
        h1_ps1_audio_pause(1);
#if H1_CLOCK_TEST != 336
        int opened=h1_clock_open(H1_CLOCK_TEST);
#else
        int opened=1;
#endif
        h1_ps1_audio_pause(0);
        if(!opened)h1_ps1_escape(30);
    }
    if(frame%100 || count==MAX_ROWS)return;
    unsigned *row=rows[count++];
    const volatile unsigned *stats=(const volatile unsigned *)&h1_ps1_stats;
    for(unsigned n=0;n<33;++n)row[n]=stats[n];
    gba_audio_snapshot(row+33);
    row[45]=*(volatile unsigned *)0xb0000000u;row[46]=*(volatile unsigned *)0xb0000010u;
}
void h1_clock_run_close(void){
#if H1_CLOCK_TEST != 336
    closed=h1_clock_close();if(!closed)h1_ps1_stats.error=31;
#endif
}
static void save(const char *suffix,unsigned restore_done){
    header[0]=0x31434f48;header[1]=1;header[2]=H1_CLOCK_TEST;header[3]=count;
    header[4]=ROW_WORDS;header[5]=restore_done;header[6]=attempted;header[7]=h1_ps1_stats.error;
    gba_audio_snapshot(final_audio);
    char path[64];snprintf(path,sizeof path,"A:\\PS1\\oc%u%s.bin",H1_CLOCK_TEST,suffix);
    FILE *f=fopen(path,"wb");if(!f)return;
    fwrite(header,1,sizeof header,f);fwrite((const void *)h1_clock_stats,1,sizeof h1_clock_stats,f);
    fwrite(rows,ROW_WORDS*sizeof(unsigned),count,f);fwrite(final_audio,1,sizeof final_audio,f);fclose(f);
}
void h1_clock_run_save(void){if(closed)save("",1);}
void h1_clock_run_checkpoint(unsigned stage){
    /* Timing is already frozen. A private measurement file can be saved at
     * the stable active rate, just as game data was read at that rate. Save
     * cards only after returning to the original clocks in main. */
    if(stage==1)save("-pre",H1_CLOCK_TEST==336);
    if(stage>=3 && !closed)return;
    unsigned v[20]={0x58434f48u,stage,H1_CLOCK_TEST,h1_raw_tick_80hz(),
        *(volatile unsigned *)0xb0000000u,*(volatile unsigned *)0xb0000010u,
        h1_clock_stats[2],h1_clock_stats[3]};
    gba_audio_snapshot(v+8);
    char path[64];snprintf(path,sizeof path,"A:\\PS1\\oc%u-exit.bin",H1_CLOCK_TEST);
    FILE *f=fopen(path,"wb");if(f){fwrite(v,1,sizeof v,f);fclose(f);}
}
