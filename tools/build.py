"""Build PSX: bare-metal MIPS32, PCSX4ALL + H1 SDK."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse, hashlib, json, os, subprocess, sys
from prepare import prepare

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT
# Match the BDA header's fixed UTC date, including upstream __DATE__ strings.
# Always override an inherited value so local and CI builds use the same bytes.
SOURCE_DATE_EPOCH='1792195200' # 2026-10-17 00:00:00 UTC

def run(args):
    p=subprocess.run(list(map(str,args)),capture_output=True,text=True,encoding='utf-8',errors='replace',
                     env={**os.environ,'SOURCE_DATE_EPOCH':SOURCE_DATE_EPOCH})
    if p.returncode: raise RuntimeError(p.stdout+p.stderr)
    return p.stdout

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--interpreter',action='store_true')
    ap.add_argument('--test-frames',type=int,default=0)
    ap.add_argument('--benchmark',action='store_true')
    ap.add_argument('--reference-video',action='store_true')
    ap.add_argument('--profile',action='store_true')
    ap.add_argument('--detailed-profile',action='store_true',help='Diagnostic UNAI span and GTE counters; adds overhead')
    ap.add_argument('--mdec-profile',action='store_true',help='Diagnostic MDEC DMA, IDCT and color conversion timers')
    ap.add_argument('--spu-profile',action='store_true',help='Diagnostic sampled SPU stages and native PCM timings')
    ap.add_argument('--audio-diag',action='store_true',help='Bounded PCM starvation and synchronous read latency trace')
    ap.add_argument('--phase-profile',action='store_true',help='Diagnostic exclusive per-100-frame phase accounting; adds overhead')
    ap.add_argument('--delay-hle',action='store_true',help='Event-bounded exact batching of recognized stack countdown loops')
    ap.add_argument('--fast-present',action='store_true',help='Exact LCD conversion with fused single/duplicate row stores')
    ap.add_argument('--fast-map',action='store_true',help='Experimental JZ4740 TLB mapping of JIT block pointer tables')
    ap.add_argument('--fast-spu',action='store_true',help='Exact native-register SPU voice stepping between ADPCM callbacks')
    ap.add_argument('--audio-turbo',action='store_true',help='Lossy mono/22.05 kHz voice mixing and very quiet voice rendering skip; T toggles')
    ap.add_argument('--clock-test',type=int,choices=(0,336,384,408),default=0,help='Bounded clock experiment; 420 disabled after two physical automatic resets; 336 records a control')
    ap.add_argument('--cpu-mhz',type=int,choices=(336,408),default=336,help='Normal game clock; restores original clocks on exit')
    ap.add_argument('--fast-lsu',action='store_true',help='Fold singleton RAM load/store effective address before mirror masking')
    ap.add_argument('--mdec-lut',action='store_true',help='Exact full-domain MDEC color clamp tables')
    ap.add_argument('--mxu',action='store_true',help='JZ4740 MXU1 exact MDEC RGB24 conversion')
    ap.add_argument('--mxu-rows',action='store_true',help='Reuse one verified MXU context across four RGB24 strips')
    ap.add_argument('--video-hle',action='store_true',help='Event-bounded HLE of recognized empty STR stream waits')
    ap.add_argument('--vlc-hle',action='store_true',help='Event-bounded native HLE of recognized SDK VLC coefficient loops')
    ap.add_argument('--vlc-batch',action='store_true',help='Larger proven VLC windows and a 42-instruction event reserve, without extra SDK gateways')
    ap.add_argument('--scene-hle',action='store_true',help='Event-bounded native GTE polygon packet construction loops')
    ap.add_argument('--movie-hle',action='store_true',help='Experimental SDK movie pipeline gateways and larger event-bounded VLC batches')
    ap.add_argument('--scene-small',action='store_true',help='Compile the scene HLE kernels for code size to test I-cache sensitivity')
    ap.add_argument('--adpcm-cache',action='store_true',help='Exact seed/content-keyed cache of SPU ADPCM block decoding')
    ap.add_argument('--fast-adpcm',action='store_true',help='Exact scalar ADPCM shifts and predictor specialization')
    ap.add_argument('--optimize',choices=('O2','O3'),default='O2')
    ap.add_argument('--lto',action='store_true')
    ap.add_argument('--gpulib',action='store_true')
    ap.add_argument('--gpu-skip',type=int,choices=(0,1,2,3),default=0)
    ap.add_argument('--idle',action='store_true',help='Batch recognized SDK VSync waits at hardware event boundaries')
    ap.add_argument('--fast-spans',action='store_true',help='Exact pair-wise 4bpp sprites and packed fill/average spans')
    ap.add_argument('--cache-mib',type=int,choices=(1,2,4,8),default=4)
    args=ap.parse_args()
    dependencies=json.loads((ROOT/'UPSTREAM.json').read_text())
    from verify_source import verify as verify_snapshot
    source_snapshot = not (ROOT/'.git').exists() and (ROOT/'SOURCE-MANIFEST.json').is_file()
    if source_snapshot:verify_snapshot(ROOT)
    for key in (() if source_snapshot else ('pcsx4all','zlib','h1_sdk')):
        repository=ROOT/'third_party'/key if key!='h1_sdk' else (ROOT/dependencies[key]['path']).resolve()
        git=['git','-c',f'safe.directory={repository.as_posix()}','-C',repository]
        if run([*git,'rev-parse','HEAD']).strip()!=dependencies[key]['commit']:
            ap.error(f'{key} commit mismatch; see UPSTREAM.json')
        if run([*git,'status','--porcelain','--untracked-files=no']).strip():
            ap.error(f'{key} was modified; restore the pinned dependency before building')
    if not 0<=args.test_frames<=36000: ap.error('invalid frame bound')
    if args.benchmark and not args.test_frames: ap.error('benchmark must be bounded')
    if args.detailed_profile and (not args.profile or not args.test_frames):ap.error('detailed profiling requires --profile and bounded frames')
    if args.mdec_profile and (not args.profile or not args.test_frames):ap.error('MDEC profiling requires --profile and bounded frames')
    if args.spu_profile and (not args.profile or not args.test_frames):ap.error('SPU profiling requires --profile and bounded frames')
    if args.audio_diag and (not args.profile or not args.test_frames or args.benchmark):ap.error('audio diagnosis requires --profile and bounded frames with PCM enabled')
    if args.fast_map and args.interpreter:ap.error('fast mapping requires the MIPS JIT')
    if args.adpcm_cache and args.fast_adpcm:ap.error('select the ADPCM cache or arithmetic experiment, not both')
    if args.scene_small and not args.scene_hle:ap.error('--scene-small requires --scene-hle')
    if args.mxu_rows and not args.mxu:ap.error('--mxu-rows requires --mxu')
    if args.vlc_batch and (not args.vlc_hle or args.movie_hle):ap.error('--vlc-batch requires --vlc-hle and excludes --movie-hle')
    if args.audio_turbo and args.spu_profile:ap.error('--audio-turbo currently excludes the source-rewriting --spu-profile')
    if args.clock_test and (args.test_frames!=12000 or not args.profile or args.benchmark):ap.error('--clock-test requires 12000 frames, --profile and physical PCM')
    if args.cpu_mhz!=336 and (args.clock_test or args.test_frames or args.benchmark):ap.error('--cpu-mhz 408 is for normal interactive builds')
    if args.movie_hle and (not args.video_hle or not args.vlc_hle):ap.error('--movie-hle requires --video-hle --vlc-hle')
    if args.phase_profile and (not args.profile or args.test_frames!=12000 or not args.gpulib or args.benchmark or args.audio_diag or args.detailed_profile or args.spu_profile or args.mdec_profile):ap.error('phase profiling requires 12000 frames, --profile --gpulib, PCM and no other detailed instrumentation')
    name=('interpreter' if args.interpreter else 'jit')+(f'-test{args.test_frames}' if args.test_frames else '')+('-bench' if args.benchmark else '')+('-reference' if args.reference_video else '')
    name+=('-profile' if args.profile else '')+('-'+args.optimize.lower() if args.optimize!='O2' else '')+('-lto' if args.lto else '')
    if args.detailed_profile:name+='-detail'
    if args.mdec_profile:name+='-mdec'
    if args.spu_profile:name+='-spu'
    name+=('-gpulib' if args.gpulib else '')+(f'-gskip{args.gpu_skip}' if args.gpu_skip else '')
    if args.idle:name+='-idle'
    if args.fast_spans:name+='-spans'
    if args.mdec_lut:name+='-mlut'
    if args.mxu:name+='-mxu'
    if args.video_hle:name+='-vhle'
    if args.vlc_hle:name+='-vlc'
    if args.fast_spu:name+='-spufast'
    if args.fast_lsu:name+='-lsu'
    if args.delay_hle:name+='-delay'
    if args.fast_present:name+='-present'
    if args.fast_map:name+='-fmap'
    if args.audio_diag:name+='-adiag'
    if args.scene_hle:name+='-scene'
    if args.movie_hle:name+='-movie'
    if args.scene_small:name+='-small'
    if args.adpcm_cache:name+='-adpcm'
    if args.fast_adpcm:name+='-fadpcm'
    if args.phase_profile:name+='-phase'
    if args.mxu_rows:name+='-mrows'
    if args.vlc_batch:name+='-vbatch'
    if args.audio_turbo:name+='-aturbo'
    if args.clock_test:name+=f'-oc{args.clock_test}'
    if args.cpu_mhz!=336:name+=f'-cpu{args.cpu_mhz}'
    build=ROOT/'build'/name
    build.mkdir(parents=True,exist_ok=True)
    core=prepare(ROOT/'third_party/pcsx4all',build/'core',profile=args.profile,gpulib=args.gpulib,idle=args.idle,detail=args.detailed_profile,fast_spans=args.fast_spans,mdec_profile=args.mdec_profile,mdec_lut=args.mdec_lut,mxu=args.mxu,video_hle=args.video_hle,vlc_hle=args.vlc_hle,spu_profile=args.spu_profile,fast_spu=args.fast_spu,fast_lsu=args.fast_lsu,delay_hle=args.delay_hle,fast_map=args.fast_map,scene_hle=args.scene_hle,adpcm_cache=args.adpcm_cache,fast_adpcm=args.fast_adpcm)
    if args.audio_turbo:
        from prepare_spu_turbo import prepare_spu_turbo
        prepare_spu_turbo(ROOT,core)
    zlib=ROOT/'third_party/zlib'
    sdk=(ROOT/dependencies['h1_sdk']['path']).resolve()
    tc=Path(os.environ.get('H1_GNU_BIN',WORK/'.tools/toolchain/bin'))
    flags=['-EL','-march=mips32','-mabi=32','-msoft-float','-mno-abicalls','-G0','-fno-pic',
           '-'+args.optimize,'-ffreestanding','-fno-builtin','-fno-stack-protector','-ffunction-sections',
           '-fdata-sections','-fno-strict-aliasing','-g','-Wall','-Wno-sign-compare',
           '-DNO_OS','-DHAVE_MEMCPY','-DNO_GZIP','-DSPU_PCSXREARMED','-DGPU_UNAI','-Dmips',
           '-DINLINE=static __inline__','-D_spu_pcsxrearmed',
           f'-DH1_CODE_CACHE_MIB={args.cache_mib}',f'-DH1_TEST_FRAMES={args.test_frames}',
           f'-DH1_BENCHMARK={int(args.benchmark)}',f'-DH1_INTERPRETER={int(args.interpreter)}',
           f'-DH1_REFERENCE_VIDEO={int(args.reference_video)}']
    flags += [f'-DH1_GPU_SKIP={args.gpu_skip}']
    if args.spu_profile:flags+=['-DH1_SPU_PROFILE=1']
    if args.gpulib:flags+=['-DUSE_GPULIB']
    flags += [f'-ffile-prefix-map={ROOT}=h1-ps1']
    if args.lto:flags+=['-flto']
    if args.movie_hle:flags+=['-DH1_MOVIE_HLE=1']
    if args.vlc_batch:flags+=['-DH1_VLC_BATCH=1']
    if args.audio_turbo:flags+=['-DH1_AUDIO_TURBO=1']
    if args.clock_test:flags+=[f'-DH1_CLOCK_TEST={args.clock_test}']
    flags+=[f'-DH1_CPU_MHZ={args.cpu_mhz}']
    flags+=[f'-DH1_PS1_VERSION="{(ROOT/"VERSION").read_text(encoding="ascii").strip()}"']
    if not args.interpreter: flags+=['-DPSXREC']
    includes=[ROOT/'src/include',ROOT/'src',sdk/'sdk/include',core,core/'plugin_lib',
              core/'gpu/gpu_unai',core/'spu/spu_pcsxrearmed',zlib]
    flags += [x for p in includes for x in ('-I',str(p))]
    sources=[ROOT/'src'/p for p in ['entry.S','startup.c','libc.c','libc_extra.c','jump.S',
             'platform.cpp','disc.cpp','audio_out.c','audio.c','main.cpp','hud.c','settings.c','menu.cpp']]
    if args.audio_diag:
        from prepare_audio_diag import prepare_audio_diag
        audio,disc=prepare_audio_diag(ROOT,build)
        sources=[audio if p.name=='audio.c' else disc if p.name=='disc.cpp' else p for p in sources]
        sources+=[ROOT/'src/audio_diag.c']
    if args.fast_present:
        from prepare_present import prepare_present
        platform=prepare_present(ROOT,build)
        sources=[platform if p.name=='platform.cpp' else p for p in sources]
        sources+=[ROOT/'src/present_fast.cpp']
    if args.fast_map:sources+=[ROOT/'src/fastmap.c']
    if args.idle:sources+=[ROOT/'src/idle.cpp']
    if args.detailed_profile:sources+=[ROOT/'src/profile_detail.cpp']
    if args.fast_spans:sources+=[ROOT/'src/raster_fast.cpp']
    if args.mxu:
        if args.mxu_rows:
            from prepare_mxu_rows import prepare_mxu_rows
            sources+=[prepare_mxu_rows(ROOT,build,core)]
        else:sources+=[ROOT/'src/mdec_mxu.S']
    if args.movie_hle:sources+=[ROOT/'src/movie_hle.cpp',ROOT/'src/movie_io_hle.cpp',ROOT/'src/movie_gpu_hle.cpp']
    if args.video_hle:sources+=[ROOT/'src/video_hle.cpp']
    if args.vlc_hle:sources+=[ROOT/'src/vlc_hle.cpp']
    if args.scene_hle:
        scene_source=ROOT/'src/scene_hle.cpp'
        if args.scene_small:
            text=scene_source.read_text(encoding='utf-8')
            before='template<bool quad> static int execute_loop('
            assert text.count(before)==1
            scene_source=build/'scene_compact.cpp'
            scene_source.write_text(text.replace(before,'template<bool quad> __attribute__((optimize("Os"))) static int execute_loop('),encoding='utf-8')
        sources+=[scene_source]
    if args.adpcm_cache:sources+=[ROOT/'src/spu_adpcm_cache.c']
    if args.fast_adpcm:sources+=[ROOT/'src/spu_adpcm_fast.c']
    if args.delay_hle:sources+=[ROOT/'src/delay_hle.cpp']
    if args.spu_profile:sources+=[ROOT/'src/spu_profile.c']
    if args.fast_spu:sources+=[ROOT/'src/spu_fast.c']
    if args.audio_turbo:sources+=[ROOT/'src/spu_turbo.c']
    if args.clock_test:sources+=[ROOT/'src/clock_control.c',ROOT/'src/clock_run.cpp']
    if args.cpu_mhz!=336:sources+=[ROOT/'src/clock_control.c',ROOT/'src/runtime_clock.cpp']
    sources += [core/(p+'.cpp') for p in ['r3000a','misc','plugins','psxmem','psxhw','psxcounters',
        'psxdma','psxbios','psxhle','psxevents','psxinterpreter','mdec','decode_xa','cdrom','sio','pad','gte']]
    if args.gpulib:sources += [core/'gpu/gpulib/gpu.cpp',core/'gpu/gpu_unai/gpulib_if.cpp',ROOT/'src/vout.cpp']
    else:sources += [core/'gpu/gpu_unai/gpu.cpp']
    sources += [core/'spu/spu_pcsxrearmed'/(p+'.c') for p in ['spu','dma','registers','freeze']]
    if not args.interpreter:
        sources += [core/'recompiler/mips'/p for p in ['recompiler.cpp','mem_mapping.cpp','mips_codegen.cpp']]
    sources += [zlib/(p+'.c') for p in ['adler32','crc32','inflate','inffast','inftrees','uncompr','zutil']]
    if args.phase_profile:
        from prepare_phase import prepare_phase
        sources=prepare_phase(ROOT,build,sources)+[ROOT/'src/phase_profile.cpp']
    def compile(item):
        i,source=item
        obj=build/f'{i:02d}-{source.stem}.o'
        compiler='g++' if source.suffix=='.cpp' else 'gcc'
        lang=['-std=gnu++11','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-fno-use-cxa-atexit'] if compiler=='g++' else []
        if args.lto and source.name in ('libc.c','libc_extra.c'):lang+=['-fno-lto']
        cmd=[tc/f'mipsel-none-elf-{compiler}.exe',*flags,*lang,'-c',source,'-o',obj]
        # Cache includes header and prepared source digests, not just timestamps.
        digest=hashlib.sha256(SOURCE_DATE_EPOCH.encode()+str(cmd).encode()+source.read_bytes()+header_digest).hexdigest()
        stamp=obj.with_suffix('.sha256')
        if not obj.exists() or not stamp.exists() or stamp.read_text()!=digest:
            run(cmd); stamp.write_text(digest)
        return obj
    header_digest=hashlib.sha256(b''.join(p.read_bytes() for folder in includes[:6]
                                         for p in sorted(folder.rglob('*.h')))).digest()
    with ThreadPoolExecutor(max_workers=min(8,os.cpu_count() or 1)) as pool:
        futures=[pool.submit(compile,item) for item in enumerate(sources)]
        objects=[];errors=[]
        for future in futures:
            try: objects.append(future.result())
            except RuntimeError as e: errors.append(str(e))
        if errors: raise RuntimeError('\n'.join(errors))
    elf,raw,bda=build/'PSX.elf',build/'PSX.bin',build/'PSX.bda'
    # Keep the original decoder and real SPU interfaces callable in the exact
    # cache candidate, so numerical/PCM tests do not depend on LTO inlining.
    component_symbols=['h1_spu_adpcm_uncached','h1_ps1_configure','SPUinit','SPUopen','SPUshutdown',
        'SPUwriteRegister','SPUwriteDMAMem','SPUasync'] if args.adpcm_cache or args.fast_adpcm else []
    component_symbols+=['h1_settings_load','h1_settings_save','h1_settings_changed','h1_settings_writable','h1_mapping_assign']
    if args.adpcm_cache:component_symbols+=['h1_spu_adpcm_cached','h1_spu_adpcm_cache_reset']
    if args.fast_adpcm:component_symbols+=['h1_spu_adpcm_fast']
    if args.fast_spu:component_symbols+=['h1_spu_samples_noint','h1_ps1_configure','SPUinit','SPUopen','SPUshutdown','SPUwriteRegister','SPUwriteDMAMem','SPUasync']
    if args.audio_turbo:component_symbols+=['h1_spu_samples_half','h1_spu_samples_quiet','h1_spu_turbo_set','h1_spu_mix_half_mono','h1_spu_finish_mono']
    if args.movie_hle:component_symbols+=['h1_ps1_vlc_hle_admit','h1_ps1_vlc_hle_execute','h1_ps1_movie_io_admit','h1_ps1_movie_io_execute']
    if args.movie_hle:component_symbols+=['h1_ps1_movie_gpu_admit','h1_ps1_movie_gpu_execute']
    if args.movie_hle and args.gpulib:component_symbols+=['_Z8GPU_initv']
    if args.phase_profile:component_symbols+=['h1_phase_enter','h1_phase_leave','h1_phase_frame']
    run([tc/'mipsel-none-elf-g++.exe',*flags,'-nostdlib','-Wl,--gc-sections','-Wl,--build-id=none',
         *[f'-Wl,--undefined={name}' for name in component_symbols],
         f'-Wl,-T,{ROOT/"src/h1.ld"}',f'-Wl,-Map,{build/"PSX.map"}','-o',elf,*objects,'-lgcc'])
    run([tc/'mipsel-none-elf-objcopy.exe','-O','binary',elf,raw])
    sys.path.insert(0,str(sdk))
    from h1_bda.header import HeaderFields,encode_header
    from h1_bda.resources import PAYLOAD_OFFSET,RESOURCE_OFFSET,RESOURCE_SIZES,build_icon_resources
    from h1_bda.validate import validate_bda
    payload=raw.read_bytes(); padding=(-(PAYLOAD_OFFSET+len(payload)))&3
    if args.mxu:
        from mxu_isa import audit
        assert audit(payload),'MXU kernel missing from linked image'
    resources=build_icon_resources(ROOT/'assets/icon.png')
    header=HeaderFields(category=0x47,file_size_minus_4=PAYLOAD_OFFSET+len(payload)+padding-4,
                        payload_offset=PAYLOAD_OFFSET,resource_offset=RESOURCE_OFFSET,resource_sizes=RESOURCE_SIZES)
    data=encode_header(header,title='PSX',build_time='2026-10-17 00:00:00')+resources+payload+bytes(padding)
    bda.write_bytes(data)
    assert validate_bda(bda)['ok']
    symbols={f[2]:int(f[0],16) for line in run([tc/'mipsel-none-elf-nm.exe',elf]).splitlines() if len(f:=line.split())==3}
    metadata={'version':(ROOT/'VERSION').read_text(encoding='ascii').strip(),'application_title':'PSX','file_name':bda.name,'icon_sha256':hashlib.sha256((ROOT/'assets/icon.png').read_bytes()).hexdigest(),'source_date_epoch':int(SOURCE_DATE_EPOCH),'variant':name,'sha256':hashlib.sha256(data).hexdigest(),'retained_component_symbols':component_symbols,
              'size':len(data),'options':vars(args),'symbols':symbols,'hardware_verified':False,'stats_words':33,
              'dependencies':dependencies,'compiler':run([tc/'mipsel-none-elf-gcc.exe','--version']).splitlines()[0],
              'source_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                               for directory in (ROOT/'src',ROOT/'tools') for p in sorted(directory.rglob('*'))
                               if p.is_file() and p.suffix in ('.c','.cpp','.h','.S','.py','.ld')}}
    (build/'PSX.build.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({'bda':str(bda),'sha256':metadata['sha256'],'size':len(data),'size_report':
          run([tc/'mipsel-none-elf-size.exe',elf])},indent=2))

if __name__=='__main__': main()
