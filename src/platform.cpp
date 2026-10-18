/* PCSX4ALL H1 frontend. GPL-2.0-or-later. */
#include "h1_sdk.h"
#include "h1_port.h"
#include "hud.h"
#if H1_CPU_MHZ > 336
#include "runtime_clock.h"
#endif
#if H1_CLOCK_TEST
#include "clock_run.h"
#endif
#include "game_input.h"
#include "psxcommon.h"
#include "plugins.h"
#include "plugin_lib.h"
#include "misc.h"
#include "audio.h"
#include "spu_config.h"
#if H1_AUDIO_TURBO
#include "spu_turbo.h"
#endif
#ifdef USE_GPULIB
#include "gpu/gpulib/gpu.h"
#endif
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>

volatile h1_ps1_stats_t h1_ps1_stats={0x31585350u,1};
int h1_ps1_jump[12];
extern "C" const uint32_t h1_ps1_abi[] __attribute__((used,section(".h1meta")))={
    0x31424148u,sizeof(psxRegisters),offsetof(psxRegisters,pc),offsetof(psxRegisters,cycle),
    offsetof(psxRegisters,io_cycle_counter),offsetof(psxRegisters,writeok),offsetof(PcsxConfig,Cpu),
    offsetof(psxRegisters,psxM),offsetof(psxRegisters,GPR),offsetof(psxRegisters,CP0)
};
struct pl_data_t pl_data;
unsigned short *SCREEN;
bool show_fps;
static unsigned gui_open,held[45],skip=H1_GPU_SKIP?0:1,paused;
static char log_buffer[12288];
static unsigned log_used;
static uint32_t colors[32768];
static uint32_t row_cache[480] __attribute__((aligned(32)));
static unsigned colors_ready,clear_screen=1;
static unsigned last_poll;
static unsigned last_guest_poll;
static unsigned pace_origin,pace_frame;
static unsigned present_phase;

extern "C" void h1_ps1_log(const char *fmt,...){
    if(log_used+256>=sizeof log_buffer)return;
    va_list ap;va_start(ap,fmt);int n=vsnprintf(log_buffer+log_used,sizeof log_buffer-log_used-2,fmt,ap);va_end(ap);
    if(n<0)return;unsigned count=(unsigned)n;if(count>sizeof log_buffer-log_used-2)count=sizeof log_buffer-log_used-2;
    log_used+=count;log_buffer[log_used++]='\n';
}
extern "C" void h1_ps1_log_flush(void){
    FILE *f=fopen("A:\\PS1\\h1ps1.log","ab");if(!f)return;
    fwrite(log_buffer,1,log_used,f);fclose(f);log_used=0;
}
extern "C" unsigned h1_ps1_rtc(void){return *(volatile uint32_t*)0xb0003004u;}
extern "C" void h1_ps1_escape(int error){
    if(error)h1_ps1_stats.error=(unsigned)error;
    h1_ps1_stats.stop=1;h1_ps1_longjmp(h1_ps1_jump);
}
extern "C" void h1_ps1_check_stop(void){
    if(h1_ps1_stats.stop)h1_ps1_escape(0);
    // The interpreter checks events on every branch. Bound native service
    // calls by emulated time, preserving prompt exit without taxing hot loops.
    if((unsigned)(psxRegs.cycle-last_guest_poll)<PSXCLK/500u)return;
    last_guest_poll=psxRegs.cycle;
    unsigned now=h1_raw_tick_80hz();
    // Poll even when a malformed executable never enables VBlank output.
    if(now-last_poll>=4u){last_poll=now;pad_update();}
}
extern "C" void h1_ps1_video_open(void){
    typedef int(*fn_t)(void);fn_t fn=(fn_t)h1_runtime_entry(h1_runtime_table(H1_RUNTIME_GUI_TABLE_SLOT),0x84cu);
    gui_open=fn&&fn();clear_screen=1;h1_hud_reset();
    if(!gui_open)h1_ps1_escape(10);
}
extern "C" void h1_ps1_video_close(void){
    if(gui_open){typedef int(*fn_t)(void);fn_t fn=(fn_t)h1_runtime_entry(h1_runtime_table(H1_RUNTIME_GUI_TABLE_SLOT),0x850u);if(fn)fn();gui_open=0;}
}
static uint32_t *framebuffer(void){
    typedef volatile uint32_t*(*fn_t)(uint16_t*,void*);
    fn_t fn=(fn_t)h1_runtime_entry(h1_runtime_table(H1_RUNTIME_GUI_TABLE_SLOT),0x8f4u);
    uint16_t info[6]={0};volatile uint32_t *p=fn?fn(info,0):0;
    if(!p||info[1]!=480||info[2]!=272||info[3]!=1920||info[5]!=32)return 0;
    return (uint32_t*)p;
}
extern "C" void h1_ps1_present(void){
    if(paused || present_phase++%(skip+1))return;
    unsigned start=h1_raw_tick_80hz();
    GPUScreenInfo_t s;GPU_getScreenInfo(&s);
    if(!s.vram||!s.w||s.w>1024||!s.h||s.h>512)return;
    uint32_t *out=framebuffer();if(!out){h1_ps1_stats.error=11;return;}
    unsigned hud_clear=clear_screen;
    if(!colors_ready){
        for(unsigned p=0;p<32768;++p)colors[p]=((p&31u)<<19)|((p&0x3e0u)<<6)|((p&0x7c00u)>>7);
        colors_ready=1;
    }
    if(clear_screen){memset(out,0,480*272*4);clear_screen=0;}
    // PS1 display pixels are non-square: keep the nominal 4:3 TV aspect.
    unsigned w=362,h=272,ox=(480-w)/2;
    static uint16_t cols[480],ys[272];static unsigned oldw,oldh;
    if(oldw!=s.w||oldh!=s.h){for(unsigned x=0;x<w;++x)cols[x]=(uint16_t)(x*s.w/w);for(unsigned y=0;y<h;++y)ys[y]=(uint16_t)(y*s.h/h);oldw=s.w;oldh=s.h;}
    unsigned prev=~0u;
    for(unsigned y=0;y<h;++y){
        unsigned sy=(s.y+ys[y])&511u;
        if(sy!=prev || H1_REFERENCE_VIDEO){
            const uint16_t *src=(const uint16_t*)s.vram+sy*1024;
            if(!s.depth24){for(unsigned x=0;x<w;++x)row_cache[x]=colors[src[(s.x+cols[x])&1023u]&32767u];}
            else{const uint8_t *src8=(const uint8_t*)src;for(unsigned x=0;x<w;++x){unsigned o=(s.x*2+cols[x]*3)&2047u;row_cache[x]=((uint32_t)src8[o]<<16)|((uint32_t)src8[(o+1)&2047]<<8)|src8[(o+2)&2047];}}
        }
#if H1_REFERENCE_VIDEO
        for(unsigned x=0;x<w;++x)((volatile uint32_t*)out)[y*480+ox+x]=row_cache[x];
#else
        memcpy(out+y*480+ox,row_cache,w*4);
#endif
        prev=sy;
    }
    ++h1_ps1_stats.displayed;
    h1_hud_draw(out,h1_raw_tick_80hz(),h1_ps1_stats.tick_hz,h1_ps1_stats.frames,h1_ps1_stats.displayed,hud_clear);
    h1_ps1_stats.video_ticks+=h1_raw_tick_80hz()-start;
}
static int keybit(unsigned key){
    switch(key){
    case H1_KEY_SPACE:return 0;case H1_KEY_ENTER:case H1_KEY_CONFIRM:return 3;
    case H1_KEY_UP:return 4;case H1_KEY_RIGHT:return 5;case H1_KEY_DOWN:return 6;case H1_KEY_LEFT:return 7;
    case H1_KEY_Q:return 8;case H1_KEY_W:return 9;case H1_KEY_A:return 10;case H1_KEY_S:return 11;
    case H1_KEY_V:return 12;case H1_KEY_C:return 13;case H1_KEY_Z:return 14;case H1_KEY_X:return 15;
    default:return -1;}
}
void pad_update(void){
    for(unsigned i=0;i<64;++i){int e=-1,k=-1;h1_event_fetch(&e,&k);if(e==-1&&k==-1)break;
        if((e==H1_EVENT_KEY_DOWN||e==H1_EVENT_KEY_UP)&&k>=1&&k<=44){
            unsigned edge=e==H1_EVENT_KEY_DOWN&&!held[k];held[k]=e==H1_EVENT_KEY_DOWN;
            if(edge&&(k==H1_KEY_ESCAPE||k==H1_KEY_BACK))h1_ps1_stats.stop=1;
            if(edge&&k==H1_KEY_F){skip=(skip+1)%3;clear_screen=1;}
            if(edge&&k==H1_KEY_H){
                bool quality=!spu_config.iUseReverb;
                spu_config.iUseReverb=quality;spu_config.iUseInterpolation=quality?2:0;
                h1_ps1_log("AUDIO_QUALITY gaussian_reverb=%u",quality);
            }
#if H1_AUDIO_TURBO
            if(edge&&k==H1_KEY_T){
                h1_spu_turbo_set(!h1_spu_turbo_mode);
                h1_ps1_log("AUDIO_TURBO enabled=%u mono=1 voice_mix_hz=22050 quiet_peak=256",h1_spu_turbo_mode);
            }
#endif
#ifdef USE_GPULIB
            if(edge&&k==H1_KEY_G){Config.FrameSkip=Config.FrameSkip?0:1;skip=Config.FrameSkip?0:1;gpulib_frameskip_prepare();clear_screen=1;}
#endif
            if(edge&&k==H1_KEY_P){paused=!paused;h1_ps1_audio_pause(paused);clear_screen=1;h1_hud_reset();}
        }
    }
}
unsigned short pad_read(int player){
    if(player)return 0xffff;
    unsigned bits=0;
    // Native simultaneous-key query remains authoritative for release.
    for(unsigned k=1;k<=42;++k){int b=keybit(k);if(b>=0&&h1_game_code_down(h1_game_key_code(k)))bits|=1u<<b;}
    return (unsigned short)~bits;
}
unsigned get_ticks(void){unsigned hz=h1_ps1_stats.tick_hz;if(!hz)hz=100;return (unsigned)((uint64_t)h1_raw_tick_80hz()*1000000u/hz);}
void wait_ticks(unsigned t){unsigned a=get_ticks();while(get_ticks()-a<t)h1_ps1_check_stop();}
void pl_frame_limit(void){
    if(h1_ps1_stats.state!=3){pad_update();h1_ps1_check_stop();return;}
    unsigned n=++h1_ps1_stats.frames;
#if H1_CPU_MHZ > 336
    if(n==1)h1_runtime_clock_start();
#endif
    h1_ps1_stats.pc=psxRegs.pc;
    if(n==1){h1_ps1_stats.raw_start=h1_raw_tick_80hz();h1_ps1_stats.rtc_start=h1_ps1_rtc();pace_origin=h1_ps1_stats.raw_start;pace_frame=n;}
    h1_ps1_stats.raw_end=h1_raw_tick_80hz();h1_ps1_stats.rtc_end=h1_ps1_rtc();
#if H1_CLOCK_TEST
    h1_clock_run_frame(n);
#endif
    pad_update();
    if(paused){
        unsigned pause_start=h1_raw_tick_80hz();
        while(paused&&!h1_ps1_stats.stop)pad_update();
        unsigned delta=h1_raw_tick_80hz()-pause_start;
        pace_origin+=delta;h1_ps1_stats.paused_ticks+=delta;
        h1_ps1_stats.raw_end=h1_raw_tick_80hz();
    }
    if(H1_TEST_FRAMES && n>=H1_TEST_FRAMES){
#if H1_CLOCK_TEST
        h1_ps1_stats.stop=1;
#else
        // Freeze timing before H1Debug takes a final full-resolution snapshot.
        // The PC acknowledges through this BDA's own stop field; finite fallback
        // returns normally if the client disconnects.
        h1_ps1_stats.state=6;
        unsigned start=h1_raw_tick_80hz(),budget=(h1_ps1_stats.tick_hz?h1_ps1_stats.tick_hz:40u)*20u;
        while(h1_ps1_stats.stop!=2u && h1_raw_tick_80hz()-start<budget){}
        h1_ps1_stats.stop=1;
#endif
    }
    if(h1_ps1_stats.stop)h1_ps1_escape(0);
#if !H1_BENCHMARK
    if(gba_audio_pacing()){
        while(gba_audio_wait())h1_ps1_check_stop();
        return;
    }
    // Measured tick rate, fractional NTSC/PAL pacing; never infer 80 Hz.
    if(Config.FrameLimit && h1_ps1_stats.tick_hz){
        unsigned hz=h1_ps1_stats.tick_hz,target=(unsigned)((uint64_t)(n-pace_frame)*hz*(Config.PsxType?1:1001)/(Config.PsxType?50:60000));
        while(h1_raw_tick_80hz()-pace_origin<target)h1_ps1_check_stop();
    }
#endif
}
extern "C" void h1_ps1_disc_pump(void);
void EmuUpdate(void){h1_ps1_disc_pump();pl_frame_limit();}
void pl_init(void){}void pl_reset(void){}void pl_pause(void){}void pl_resume(void){}
void pl_clear_screen(void){clear_screen=1;}void pl_clear_borders(void){clear_screen=1;}
void pl_screenshot_160x120_rgb565(uint16_t *p){memset(p,0,160*120*2);}
void video_flip(void){}void video_clear(void){clear_screen=1;}void port_printf(int,int,const char*){}
int state_load(int){return -1;}int state_save(int){return -1;}int SelectGame(void){return 0;}int GameMenu(void){return 0;}
extern "C" void h1_ps1_message(const char *s){h1_message_box(0,s,"PS1",0);}
extern "C" int h1_ps1_select(char *path,unsigned cap){
#if H1_TEST_FRAMES
    FILE *auto_file=fopen("A:\\PS1\\autorun.txt","rb");
    if(auto_file){char *got=fgets(path,(int)cap,auto_file);fclose(auto_file);if(got){path[strcspn(path,"\r\n")]=0;return path[0]?1:0;}}
#endif
    char output[512]={0};typedef void(*fn_t)(const char*,const char*,char*);
    fn_t fn=(fn_t)h1_runtime_entry(h1_runtime_table(H1_RUNTIME_GUI_TABLE_SLOT),0x9ecu);
    if(!fn)return -1;fn("A:\\PS1\\","exe;bin;iso;cue",output);
    // The native selector sets game-display mode even when cancelled.
    // Pair open/close to restore desktop drawing before returning to main.
    h1_ps1_video_open();h1_ps1_video_close();
    unsigned n=0;while(n<sizeof output&&output[n])++n;if(!n)return 0;
    if(n>=cap||n==sizeof output||n<4||output[1]!=':'||(output[2]!='\\'&&output[2]!='/'))return -1;
    memcpy(path,output,n+1);return 1;
}
