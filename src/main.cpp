#include "h1_sdk.h"
#include "h1_port.h"
#include "settings.h"
#if H1_CPU_MHZ > 336
#include "runtime_clock.h"
#endif
#if H1_CLOCK_TEST
#include "clock_run.h"
#endif
#include "psxcommon.h"
#include "misc.h"
#include "plugins.h"
#include "sio.h"
#include "gpu/gpu_unai/gpu.h"
#include "spu_config.h"
#if H1_AUDIO_TURBO
#include "spu_turbo.h"
#endif
#include <stdio.h>
#include <string.h>
extern uint32_t cycle_multiplier;
static unsigned cpu_ready,plugins_ready;
static char path[240];
static bool valid_exe(const char *name){
    uint32_t header[16]={0};FILE *f=fopen(name,"rb");if(!f)return false;
    bool ok=fread(header,1,sizeof header,f)==sizeof header&&!memcmp(header,"PS-X EXE",8);
    long length=fseek(f,0,SEEK_END)?-1:ftell(f);fclose(f);
    unsigned address=header[6],size=header[7],pc=header[4];
    unsigned segment=address&0xe0000000u,pc_segment=pc&0xe0000000u;
    return ok&&length>=0x800&&(segment==0||segment==0x80000000u||segment==0xa0000000u)&&
        (pc_segment==0||pc_segment==0x80000000u||pc_segment==0xa0000000u)&&
        !(pc&3u)&&(pc&0x1fffffffu)<0x800000u&&(address&0x1fffffffu)<0x800000u&&
        size&&size<=0x200000u-(address&0x1fffffu)&&(unsigned)length-0x800u>=size;
}
extern "C" void h1_ps1_configure(void){
    memset(&Config,0,sizeof Config);Config.HLE=1;Config.PsxAuto=1;
    Config.Cpu=H1_INTERPRETER?1:0;Config.FrameLimit=1;Config.FrameSkip=H1_GPU_SKIP;
    Config.SpuUpdateFreq=3;Config.ForcedXAUpdates=1;
    strcpy(Config.Bios,"HLE");strcpy(Config.BiosDir,"A:\\PS1");
    strcpy(Config.Mcd1,"A:\\PS1\\card1.mcd");strcpy(Config.Mcd2,"A:\\PS1\\card2.mcd");
    // Use supplied BIOS when present, without bundling Sony firmware.
    FILE *bios=fopen("A:\\PS1\\bios.bin","rb");
    if(bios){fseek(bios,0,SEEK_END);long n=ftell(bios);fclose(bios);if(n==524288){Config.HLE=0;strcpy(Config.Bios,"bios.bin");}}
    memset(&gpu_unai_config_ext,0,sizeof gpu_unai_config_ext);
    gpu_unai_config_ext.lighting=1;gpu_unai_config_ext.blending=1;
    gpu_unai_config_ext.fast_lighting=1;
    // LCD skip only: no silent removal of render lines/VRAM primitives.
#ifndef USE_GPULIB
    gpu_unai_config_ext.frameskip_count=0;
#endif
    memset(&spu_config,0,sizeof spu_config);spu_config.iHaveConfiguration=1;
    spu_config.iVolume=1024;spu_config.iTempo=0;spu_config.iUseFixedUpdates=1;
#if H1_AUDIO_TURBO
    h1_spu_turbo_reset();
#endif
    h1_ps1_stats.core=H1_INTERPRETER?1:0;h1_ps1_stats.cache_mib=H1_CODE_CACHE_MIB;
    h1_ps1_stats.video_mode=H1_REFERENCE_VIDEO;
}
extern "C" int h1_app_main(void){
    FILE *log=fopen("A:\\PS1\\h1ps1.log","wb");if(log)fclose(log);
    h1_ps1_log("H1PS1_BEGIN version=" H1_PS1_VERSION " jit=%u",!H1_INTERPRETER);h1_ps1_log_flush();
    h1_ps1_stats.state=1;
    if(h1_ps1_setjmp(h1_ps1_jump)==0){
        int selection=h1_ps1_select(path,sizeof path);if(selection<=0){if(selection<0)h1_ps1_stats.error=1;goto done;}
        h1_ps1_log("SELECTED path=%s",path);h1_ps1_log_flush();
        const char *ext=strrchr(path,'.');
        bool exe=ext&&!strcasecmp(ext,".exe");
        if(exe&&!valid_exe(path)){h1_ps1_stats.error=4;goto done;}
        h1_ps1_configure();
        h1_settings_load(path);h1_ps1_apply_settings();
        h1_ps1_video_open();
        // Calibrate against actual RTC seconds; preserve firmware clocks.
        unsigned rtc=h1_ps1_rtc(),start=h1_raw_tick_80hz();
        unsigned spins=0;while(h1_ps1_rtc()==rtc&&++spins<60000000u){}
        unsigned r=h1_ps1_rtc(),a=h1_raw_tick_80hz();spins=0;
        while(h1_ps1_rtc()==r&&++spins<60000000u){}
        unsigned hz=h1_raw_tick_80hz()-a;
        if(h1_ps1_rtc()==r+1&&hz>=10&&hz<=2000)h1_ps1_stats.tick_hz=hz;
        h1_ps1_log("CLOCK raw_delta=%u hz=%u spins=%u",h1_raw_tick_80hz()-start,h1_ps1_stats.tick_hz,spins);h1_ps1_log_flush();
        h1_ps1_stats.state=2;
        cpu_ready=1;
        if(psxInit()<0){
            psxShutdown();
#if !H1_INTERPRETER
            Config.Cpu=1;h1_ps1_stats.core=1;
            h1_ps1_log("JIT_UNAVAILABLE falling_back_to_interpreter=1");
            if(psxInit()<0)h1_ps1_escape(2);
#else
            h1_ps1_escape(2);
#endif
        }
        if(!exe)SetIsoFile(path);
        plugins_ready=1;if(LoadPlugins()<0)h1_ps1_escape(3);
        psxReset();
        if(exe){if(Load(path)<0)h1_ps1_escape(4);}
        else{if(CheckCdrom()<0||LoadCdrom()<0)h1_ps1_escape(5);}
        h1_ps1_log("RUN pc=%08x hle=%u core=%u",psxRegs.pc,Config.HLE,Config.Cpu);h1_ps1_log_flush();
        h1_ps1_stats.state=3;
        psxCpu->Execute();
    }
done:
    h1_ps1_stats.state=4;
#if H1_CPU_MHZ > 336
    if(!h1_runtime_clock_stop()){
        // Do not save a card or log after an unconfirmed clock restoration.
        h1_ps1_stats.error=31;
        if(plugins_ready)ReleasePlugins();
        if(cpu_ready)psxShutdown();
        h1_ps1_video_close();h1_ps1_stats.state=5;return 31;
    }
#endif
#if H1_CLOCK_TEST
    h1_clock_run_checkpoint(1);
    // Stop native PCM/DMA before switching the active memory/bus clocks.
    h1_ps1_audio_close();
    h1_clock_run_checkpoint(2);
    h1_clock_run_close();
    h1_clock_run_checkpoint(3);
#endif
    if(h1_settings_save()<0)h1_ps1_log("SETTINGS_SAVE failed=1");
    if(cpu_ready){h1_ps1_stats.pc=psxRegs.pc;
        if(psxM){h1_ps1_stats.checksum=*(uint32_t*)(psxM+0x100);for(unsigned i=0;i<4;++i)h1_ps1_stats.cpu_checks[i]=((uint32_t*)(psxM+0x108))[i];}
        sioSyncMcds();EjectMcd(MCD1);EjectMcd(MCD2);}
    h1_ps1_audio_close();
    if(plugins_ready)ReleasePlugins();
    if(cpu_ready)psxShutdown();
    h1_ps1_video_close();
    h1_ps1_log("RESULT error=%u frames=%u displayed=%u raw_start=%u raw_end=%u rtc_start=%u rtc_end=%u hz=%u video_ticks=%u reads=%u hits=%u disc_ticks=%u pc=%08x check=%08x",h1_ps1_stats.error,h1_ps1_stats.frames,h1_ps1_stats.displayed,h1_ps1_stats.raw_start,h1_ps1_stats.raw_end,h1_ps1_stats.rtc_start,h1_ps1_stats.rtc_end,h1_ps1_stats.tick_hz,h1_ps1_stats.video_ticks,h1_ps1_stats.disc_reads,h1_ps1_stats.disc_hits,h1_ps1_stats.disc_ticks,h1_ps1_stats.pc,h1_ps1_stats.checksum);
    h1_ps1_log("PERFORMANCE core=%u gpu_skip=%d idle_batches=%u idle_iterations=%u gpu_ticks=%u gpu_calls=%u spu_ticks=%u spu_calls=%u paused_ticks=%u",h1_ps1_stats.core,(int)Config.FrameSkip,h1_ps1_stats.idle_batches,h1_ps1_stats.idle_iterations,h1_ps1_stats.gpu_ticks,h1_ps1_stats.gpu_calls,h1_ps1_stats.spu_ticks,h1_ps1_stats.spu_calls,h1_ps1_stats.paused_ticks);
    h1_ps1_log_flush();
#if !H1_TEST_FRAMES
    if(h1_ps1_stats.error)h1_ps1_message("Cannot load game. See A:\\PS1\\h1ps1.log");
#endif
    h1_ps1_stats.state=5;
#if H1_CLOCK_TEST
    h1_clock_run_save();
#endif
    return (int)h1_ps1_stats.error;
}
