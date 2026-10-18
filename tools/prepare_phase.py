"""Diagnostic-only exclusive phase scopes in prepared source copies."""
import re

def prepare_phase(root,build,sources):
    copies={};receipts=[]
    def edit(path,change):
        path=path.resolve()
        if path not in copies:
            dest=build/('phase-'+path.name) if root/'src' in path.parents else path
            if dest!=path:dest.write_bytes(path.read_bytes())
            copies[path]=dest
        dest=copies[path];text=dest.read_text(encoding='utf-8')
        if '#include "phase_profile.h"' not in text:text='#include "phase_profile.h"\n'+text
        text=change(text);dest.write_text(text,encoding='utf-8')
    def scope(path,name,kind):
        def change(text):
            prefix=r'(?:(?:extern\s+"C"|static|inline)\s+)*(?:void|int|unsigned|bool|long|size_t|u32|uint32_t)(?:\s+(?:short|long|int))?(?:\s+CALLBACK)?\s+'
            pattern=r'(?m)^[ \t]*'+prefix+re.escape(name)+r'\([^;{}]*?\)\s*\{'
            text,n=re.subn(pattern,lambda m:m[0]+'\n H1_PHASE('+kind+');',text)
            # execute_full has mutually exclusive compile-time signatures;
            # all named function definitions here must be unique.
            assert n==1,(str(path),name,n);receipts.append((str(path),name,kind,n));return text
        edit(path,change)
    core=build/'core'
    scope(core/'recompiler/mips/recompiler.cpp','recRecompile','HPP_COMPILE')
    scope(core/'recompiler/mips/recompiler.cpp','recClear','HPP_INVALIDATE')
    scope(core/'r3000a.cpp','psxBranchTest','HPP_EVENT')
    for name in ('RTPS','RTPT','MVMVA','NCLIP','AVSZ3','AVSZ4','SQR','NCCS','NCCT','NCDS','NCDT','OP','DCPL','GPF','GPL','DPCS','DPCT','NCS','NCT','CC','INTPL','CDP'):
        scope(core/'gte.cpp','gte'+name,'HPP_GTE')
    for name,kind in (('psxDma0','HPP_MDEC'),('psxDma1','HPP_MDEC'),('idct','HPP_IDCT'),('yuv2rgb15','HPP_RGB'),('yuv2rgb24','HPP_RGB')):
        scope(core/'mdec.cpp',name,kind)
    for name in ('GPU_dmaChain','GPU_writeDataMem','GPU_writeData','GPU_writeStatus','GPU_readDataMem','GPU_readData','GPU_readStatus','GPU_updateLace'):
        scope(core/'gpu/gpulib/gpu.cpp',name,'HPP_GPU')
    scope(core/'spu/spu_pcsxrearmed/spu.c','SPUasync','HPP_SPU')
    for p in list(sources):
        if p.name=='disc.cpp':scope(p,'read_sector','HPP_DISC')
        if p.name=='audio.c':scope(p,'gba_audio_write','HPP_PCM')
        if p.name in ('platform.cpp','platform-present.cpp'):
            for name,kind in (('h1_ps1_present','HPP_LCD'),('pad_update','HPP_INPUT'),('pad_read','HPP_INPUT')):scope(p,name,kind)
            def frame(text):
                old='    pad_update();\n    if(paused)';assert text.count(old)==1
                text=text.replace(old,'    h1_phase_frame(n);\n'+old)
                old='    if(gba_audio_pacing()){' ;assert text.count(old)==1
                text=text.replace(old,'    H1_PHASE(HPP_PACE);\n'+old)
                return text
            edit(p,frame)
        if p.name=='vlc_hle.cpp':
            for name,kind in (('h1_ps1_vlc_hle_admit','HPP_VLC_GATE'),('h1_ps1_vlc_hle_execute','HPP_VLC_GATE'),('unchanged','HPP_CODE_CHECK')):scope(p,name,kind)
            def body(text):
                old='    const uint32_t *primary=(const uint32_t*)(tables+2048);';assert text.count(old)==1
                return text.replace(old,'    H1_PHASE(HPP_VLC_BODY);\n'+old)
            edit(p,body)
        if p.name=='video_hle.cpp':scope(p,'h1_ps1_video_hle_execute','HPP_VIDEO_WAIT')
        if p.name=='movie_hle.cpp':
            scope(p,'movie_execute','HPP_MOVIE');scope(p,'same','HPP_CODE_CHECK')
        if p.name=='movie_io_hle.cpp':
            scope(p,'h1_ps1_movie_io_execute','HPP_MOVIE_IO');scope(p,'same','HPP_CODE_CHECK')
        if p.name=='movie_gpu_hle.cpp':
            scope(p,'h1_ps1_movie_gpu_execute','HPP_MOVIE_GPU');scope(p,'same','HPP_CODE_CHECK')
    import json
    (build/'phase-scopes.json').write_text(json.dumps(receipts,indent=2)+'\n')
    return [copies.get(p.resolve(),p) for p in sources]
