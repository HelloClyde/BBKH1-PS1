"""Reproducible H1 adaptation; upstream checkouts are never edited."""
from pathlib import Path
import shutil

def replace(path, old, new):
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise RuntimeError(f'Patch context changed: {path}: {old[:80]}')
    path.write_text(text.replace(old, new), encoding='utf-8')

def prepare(source, target, profile=False, gpulib=False, idle=False,detail=False,fast_spans=False,mdec_profile=False,mdec_lut=False,mxu=False,video_hle=False,vlc_hle=False,spu_profile=False,fast_spu=False,fast_lsu=False,delay_hle=False,fast_map=False,scene_hle=False,adpcm_cache=False,fast_adpcm=False):
    shutil.copytree(source / 'src', target, dirs_exist_ok=True)
    rec = target / 'recompiler/mips/recompiler.cpp'
    replace(rec, '#define RECMEM_SIZE         (12 * 1024 * 1024)',
            '#define RECMEM_SIZE (H1_CODE_CACHE_MIB * 1024 * 1024)')
    replace(rec, 'static u8 recMemBase[RECMEM_SIZE] __attribute__((aligned(4)));',
            'static u8 *recMemBase;')
    replace(rec, 'static int recInit()\n{',
            'static int recInit()\n{\n\tif (!recMemBase) recMemBase = (u8*)malloc(RECMEM_SIZE);\n'
            '\tif (!recMemBase) return -1;')
    # recReset dereferences the allocation: validate before calling it.
    replace(rec, '\trecReset();\n\n\tif (recRAM == NULL',
            '\tif (!recRAM || !recROM) { free(recRAM); free(recROM); free(recMemBase);'
            ' recRAM=recROM=NULL; recMemBase=NULL; return -1; }\n'
            '\trecReset();\n\n\tif (recRAM == NULL')
    replace(rec, '\tpsx_mem_mapped = rec_mem_mapped = false;',
            '\tif (!rec_mem_mapped) { free(recRAM); free(recROM); }\n'
            '\trecRAM=recROM=NULL; free(recMemBase); recMemBase=NULL;\n'
            '\tpsx_mem_mapped = rec_mem_mapped = false;')
    # Keep the assembly dispatcher; cancellation is checked at event boundaries.
    replace(rec, '#include <stddef.h>', '#include <stddef.h>\n#include "h1_port.h"')
    if idle:
        replace(rec,'\t// Number of discardable instructions we are currently skipping', '''
    unsigned idle_token=h1_ps1_idle_admit(oldpc);
    if (idle_token) {
        LI32(MIPSREG_A0,oldpc);
        LI32(MIPSREG_A1,idle_token);
        JAL(h1_ps1_idle_execute);
        NOP();
        host_ra_reg_has_block_retaddr=false;
        u32 *idle_fallback=recMem;
        BEQ(MIPSREG_V0,0,0);
        NOP();
        LW(MIPSREG_V0,PERM_REG_1,off(pc));
        rec_recompile_end_part1();
        rec_recompile_end_part2(false);
        fixup_branch(idle_fallback);
        LW(MIPSREG_V0,PERM_REG_1,off(pc));
    }
\t// Number of discardable instructions we are currently skipping''')
    if video_hle:
        replace(rec,'#include "h1_port.h"','#include "h1_port.h"\n#include "video_hle.h"')
        replace(rec,'\t// Number of discardable instructions we are currently skipping', '''
    unsigned video_token=h1_ps1_video_hle_admit(oldpc);
    if (video_token) {
        LI32(MIPSREG_A0,oldpc);
        LI32(MIPSREG_A1,video_token);
        JAL(h1_ps1_video_hle_execute);
        NOP();
        host_ra_reg_has_block_retaddr=false;
        u32 *video_fallback=recMem;
        BEQ(MIPSREG_V0,0,0);
        NOP();
        LW(MIPSREG_V0,PERM_REG_1,off(pc));
        rec_recompile_end_part1();
        rec_recompile_end_part2(false);
        fixup_branch(video_fallback);
        LW(MIPSREG_V0,PERM_REG_1,off(pc));
    }
\t// Number of discardable instructions we are currently skipping''')
    if vlc_hle:
        replace(rec,'#include "h1_port.h"','#include "h1_port.h"\n#include "vlc_hle.h"')
        replace(rec,'\t// Number of discardable instructions we are currently skipping', '''
    unsigned vlc_token=h1_ps1_vlc_hle_admit(oldpc);
    if (vlc_token) {
        LI32(MIPSREG_A0,oldpc);
        LI32(MIPSREG_A1,vlc_token);
        JAL(h1_ps1_vlc_hle_execute);
        NOP();
        host_ra_reg_has_block_retaddr=false;
        u32 *vlc_fallback=recMem;
        BEQ(MIPSREG_V0,0,0);
        NOP();
        LW(MIPSREG_V0,PERM_REG_1,off(pc));
        rec_recompile_end_part1();
        rec_recompile_end_part2(false);
        fixup_branch(vlc_fallback);
        LW(MIPSREG_V0,PERM_REG_1,off(pc));
    }
\t// Number of discardable instructions we are currently skipping''')
    if scene_hle:
        replace(rec,'#include "h1_port.h"','#include "h1_port.h"\n#include "scene_hle.h"')
        replace(rec,'\t// Number of discardable instructions we are currently skipping', '''
    unsigned scene_token=h1_ps1_scene_hle_admit(oldpc);
    if (scene_token) {
        LI32(MIPSREG_A0,oldpc);LI32(MIPSREG_A1,scene_token);
        JAL(h1_ps1_scene_hle_execute);NOP();
        host_ra_reg_has_block_retaddr=false;
        u32 *scene_fallback=recMem;BEQ(MIPSREG_V0,0,0);NOP();
        LW(MIPSREG_V0,PERM_REG_1,off(pc));
        rec_recompile_end_part1();rec_recompile_end_part2(false);
        fixup_branch(scene_fallback);LW(MIPSREG_V0,PERM_REG_1,off(pc));
    }
\t// Number of discardable instructions we are currently skipping''')
    # Replace Linux memory mapping with no-op fallbacks (never map firmware RAM).
    if delay_hle:
        replace(rec,'#include "h1_port.h"','#include "h1_port.h"\n#include "delay_hle.h"')
        replace(rec,'\t// Number of discardable instructions we are currently skipping', '''
    unsigned delay_token=h1_ps1_delay_hle_admit(oldpc);
    if (delay_token) {
        LI32(MIPSREG_A0,oldpc);LI32(MIPSREG_A1,delay_token);
        JAL(h1_ps1_delay_hle_execute);NOP();
        host_ra_reg_has_block_retaddr=false;
        u32 *delay_fallback=recMem;BEQ(MIPSREG_V0,0,0);NOP();
        LW(MIPSREG_V0,PERM_REG_1,off(pc));
        rec_recompile_end_part1();rec_recompile_end_part2(false);
        fixup_branch(delay_fallback);LW(MIPSREG_V0,PERM_REG_1,off(pc));
    }
\t// Number of discardable instructions we are currently skipping''')
    mapping='int rec_mmap_psx_mem(){return -1;}\nvoid rec_munmap_psx_mem(){}\n'
    if fast_map:
        replace(rec,'#include "mem_mapping.h"','#define USE_VIRTUAL_RECRAM_MAPPING\n#include "mem_mapping.h"')
        mapping+='''#include "fastmap.h"
#include <stdlib.h>
#include <sys/cachectl.h>
int rec_mmap_rec_mem(){
 const h1_fastmap_api api={malloc,free,cacheflush};
 return h1_fastmap_open(&api)?0:-1;
}
void rec_munmap_rec_mem(){h1_fastmap_close();}
'''
    else:mapping+='int rec_mmap_rec_mem(){return -1;}\nvoid rec_munmap_rec_mem(){}\n'
    (target / 'recompiler/mips/mem_mapping.cpp').write_text(mapping,encoding='utf-8')
    if fast_lsu:
        lsu=target/'recompiler/mips/rec_lsu.cpp.h'
        replace(lsu,'\t\tconst bool emit_address_range_check = emit_indirect;', '''
        const bool emit_address_range_check = emit_indirect;
        // One normal load/store: mask the final effective address, not the
        // unadjusted base. This handles 2 MiB mirrors directly and removes
        // the old same-region check. Unaligned merge ops and series retain
        // their original paths. Only fold with the full runtime range check;
        // a fuzzy RAM base alone does not prove base+immediate stays in RAM.
        // Range checks, MMIO and SMC stay enabled.
        const u32 h1_op=OPCODE_AT(pc-4)>>26;
        const bool h1_fold=!psx_mem_mapped && emit_address_range_check && count==1 &&
            ((h1_op>=0x20 && h1_op<=0x25 && h1_op!=0x22) ||
             h1_op==0x28 || h1_op==0x29 || h1_op==0x2b);
''')
        replace(lsu,'\t\tif (!psx_mem_mapped)\n#endif\n\t\t{',
                    '\t\tif (!psx_mem_mapped && !h1_fold)\n#else\n        if (!h1_fold)\n#endif\n\t\t{')
        replace(lsu,'\t\tconst u32 converted_base_reg = emitAddressConversion(op_rs, rs, TEMP_1, TEMP_2);  // <BD slot>', '''
        // The range-check path already calculated A0 = base + immediate.
        // Its branch delay slot is filled by the conversion's first load.
        const u32 converted_base_reg = emitAddressConversion(op_rs,h1_fold?MIPSREG_A0:rs,TEMP_1,TEMP_2);
''')
        replace(lsu,'\t\t\tconst s16 op_imm = _fImm_(opcode);\n\t\t\tconst u32 op_rt  = _fRt_(opcode);',
                    '\t\t\tconst s16 op_imm = h1_fold ? 0 : _fImm_(opcode);\n\t\t\tconst u32 op_rt  = _fRt_(opcode);')
    gpu = target / 'gpu/gpu_unai/gpu.cpp'
    replace(gpu, 'static u16 GPU_FrameBuffer[(FRAME_BUFFER_SIZE*2 + 4096)/2] __attribute__((aligned(32)));',
            'static u16 *GPU_FrameBuffer;')
    replace(gpu, 'long GPU_init(void)\n{',
            'long GPU_init(void)\n{\n'
            '\tif (!GPU_FrameBuffer) GPU_FrameBuffer=(u16*)calloc(1,FRAME_BUFFER_SIZE*2+4096);\n'
            '\tif (!GPU_FrameBuffer) return -1;')
    replace(gpu, 'long GPU_shutdown(void)\n{',
            'long GPU_shutdown(void)\n{\n\tfree(GPU_FrameBuffer); GPU_FrameBuffer=NULL;')
    text = gpu.read_text(encoding='utf-8')
    start = text.index('static void gpuVideoOutput(')
    brace = text.index('{', start)
    end, depth = brace+1, 1
    while depth:
        depth += (text[end]=='{') - (text[end]=='}')
        end += 1
    text = text[:start] + 'static void gpuVideoOutput(void) { h1_ps1_present(); }' + text[end:]
    text = text.replace('#include "port.h"', '#include "port.h"\n#include "h1_port.h"')
    gpu.write_text(text, encoding='utf-8')
    if gpulib:
        replace(target/'gpu/gpulib/gpu.cpp',
                '  if (gpu.frameskip.set) {\n    if (!gpu.frameskip.frame_ready)',
                '  if (gpu.frameskip.set && gpu.frameskip.allow) {\n    if (!gpu.frameskip.frame_ready)')
    if profile:
        if gpulib:gpu=target/'gpu/gpulib/gpu.cpp'
        text=gpu.read_text(encoding='utf-8')
        text=text.replace('long GPU_dmaChain(', 'static long h1_dma_inner(')
        text+='''
#include "h1_sdk.h"
#include "h1_port.h"
long GPU_dmaChain(uint32_t *p,uint32_t start) {
 unsigned tick=h1_raw_tick_80hz();
 long result=h1_dma_inner(p,start);
 h1_ps1_stats.gpu_ticks+=h1_raw_tick_80hz()-tick;
 ++h1_ps1_stats.gpu_calls;
 return result;
}
'''
        gpu.write_text(text,encoding='utf-8')
        spu=target/'spu/spu_pcsxrearmed/spu.c'
        replace(spu, 'void CALLBACK SPUasync(unsigned int cycle, unsigned int flags)',
                'static void h1_spu_inner(unsigned int cycle, unsigned int flags)')
        with spu.open('a',encoding='utf-8') as f:
            f.write('''
#include "h1_sdk.h"
#include "h1_port.h"
void SPUasync(unsigned int cycle,unsigned int flags) {
 unsigned tick=h1_raw_tick_80hz();
 h1_spu_inner(cycle,flags);
 h1_ps1_stats.spu_ticks+=h1_raw_tick_80hz()-tick;
 ++h1_ps1_stats.spu_calls;
}
''')
    if fast_spu:
        spu=target/'spu/spu_pcsxrearmed/spu.c'
        replace(spu,'make_do_samples(noint, , fa = SB[29], , ChanBuf[ns] = fa, SB[29] = fa)', '''
#include "spu_fast.h"
static noinline int do_samples_noint(
 int (*decode_f)(void *,int,int *),void *ctx,
 int ch,int ns_to,int *SB,int sinc,int *spos,int *sbpos)
{
 return h1_spu_samples_noint(decode_f,ctx,ch,ns_to,SB,sinc,spos,sbpos,ChanBuf);
}
''')
    if adpcm_cache or fast_adpcm:
        spu=target/'spu/spu_pcsxrearmed/spu.c'
        header='spu_adpcm_fast.h' if fast_adpcm else 'spu_adpcm_cache.h'
        helper='h1_spu_adpcm_fast' if fast_adpcm else 'h1_spu_adpcm_cached'
        replace(spu,'static void decode_block_data(int *dest, const unsigned char *src, int predict_nr, int shift_factor)',
            '#include "'+header+'"\nvoid h1_spu_adpcm_uncached(int *dest, const unsigned char *src, int predict_nr, int shift_factor)')
        replace(spu,'static int decode_block(void *unused, int ch, int *SB)', '''static void decode_block_data(int *dest, const unsigned char *src, int predict_nr, int shift_factor)
{
 HELPER(dest,src,predict_nr,shift_factor);
}
static int decode_block(void *unused, int ch, int *SB)'''.replace('HELPER',helper))
    if spu_profile:
        spu=target/'spu/spu_pcsxrearmed/spu.c'
        text=spu.read_text(encoding='utf-8')
        text='#include "spu_profile.h"\n'+text
        # Wrappers surround actual function bodies, including every early
        # return. Only diagnostic builds alter these call/inlining boundaries.
        specs=[
            ('static void decode_block_data(int *dest, const unsigned char *src, int predict_nr, int shift_factor)',
             'dest,src,predict_nr,shift_factor','HSP_ADPCM',64),
            ('static void mix_chan(int *SSumLR, int count, int lv, int rv)',
             'SSumLR,count,lv,rv','HSP_MIX',16),
            ('static void do_channels(int ns_to)','ns_to','HSP_CHANNELS',1),
            ('void do_samples(unsigned int cycles_to, int do_direct)','cycles_to,do_direct','HSP_SYNTH',1),
            ('static void do_samples_finish(int *SSumLR, int ns_to,\n int silentch, int decode_pos)',
             'SSumLR,ns_to,silentch,decode_pos','HSP_FINISH',1),
            ('void schedule_next_irq(void)','','HSP_IRQ',1),
        ]
        for signature,arguments,kind,stride in specs:
            name=signature.split('(')[0].split()[-1];inner='h1_profile_inner_'+name
            start=text.index(signature+'\n{');brace=text.index('{',start);end=brace+1;depth=1
            while depth:
                depth+=(text[end]=='{')-(text[end]=='}');end+=1
            body=text[start:end].replace(signature,signature.replace(name,inner,1),1)
            extra='h1_spu_profile_voices(spu.dwChannelOn|spu.dwNewChannel);' if name=='do_channels' else ''
            wrapper='\n'+signature+' {\n '+extra+'\n H1_SPU_BEGIN(tick,'+kind+','+str(stride)+');\n '+inner+'('+arguments+');\n H1_SPU_END('+kind+',tick);\n}\n'
            text=text[:start]+body+wrapper+text[end:]
        spu.write_text(text,encoding='utf-8')
        adsr=target/'spu/spu_pcsxrearmed/adsr.c'
        replace(adsr,'static int MixADSR(ADSRInfoEx *adsr, int ns_to)',
                'static int h1_profile_inner_MixADSR(ADSRInfoEx *adsr, int ns_to)')
        with adsr.open('a',encoding='utf-8') as f:
            f.write('''
static int MixADSR(ADSRInfoEx *adsr,int ns_to) {
 H1_SPU_BEGIN(tick,HSP_ADSR,16);
 int result=h1_profile_inner_MixADSR(adsr,ns_to);
 H1_SPU_END(HSP_ADSR,tick);return result;
}
''')
        xa=target/'spu/spu_pcsxrearmed/xa.c'
        replace(xa,'INLINE void MixXA(int *SSumLR, int ns_to, int decode_pos)',
                'INLINE void h1_profile_inner_MixXA(int *SSumLR, int ns_to, int decode_pos)')
        with xa.open('a',encoding='utf-8') as f:
            f.write('''
static void MixXA(int *SSumLR,int ns_to,int decode_pos) {
 H1_SPU_BEGIN(tick,HSP_XA,1);h1_profile_inner_MixXA(SSumLR,ns_to,decode_pos);
 H1_SPU_END(HSP_XA,tick);
}
''')
    if mdec_lut:
        # Rounded signed 32-bit values have precisely 4096 (8-bit conversion)
        # or 512 (5-bit conversion) possible upper-bit patterns. Cover every
        # pattern, including wrapped overflow; never approximate the IDCT.
        tables=''
        for suffix,bits,bias,maximum in [('8',12,128,255),('5',9,16,31)]:
            values=[]
            for i in range(1<<bits):
                signed=i if i<(1<<(bits-1)) else i-(1<<bits)
                values.append(str(max(0,min(maximum,signed+bias))))
            tables+='static const u8 h1_mdec_clamp'+suffix+'['+str(1<<bits)+']={\n'
            tables+='\n'.join(','.join(values[i:i+32])+',' for i in range(0,len(values),32))+'\n};\n'
        mdec=target/'mdec.cpp'
        replace(mdec,'#define CLAMP_SCALE8(a)   (CLAMP8(SCALE8(a)))',tables+
                '#define CLAMP_SCALE8(a) h1_mdec_clamp8[((u32)(a)+0x80000u)>>20]')
        replace(mdec,'#define CLAMP_SCALE5(a)   (CLAMP5(SCALE5(a)))',
                '#define CLAMP_SCALE5(a) h1_mdec_clamp5[((u32)(a)+0x400000u)>>23]')
    if mxu:
        mdec=target/'mdec.cpp'
        replace(mdec,'static void yuv2rgb24(int *blk, u8 *image) {', '''extern "C" void h1_mdec_row24_mxu(const int *cr,const int *y,u8 *image);
static void yuv2rgb24(int *blk, u8 *image) {
 if (!Config.Mdec) {
  for (unsigned row=0;row<8;++row)
   h1_mdec_row24_mxu(blk+8*row,blk+128+(row%4)*16+(row/4)*128,image+96*row);
  return;
 }''')
    if mdec_profile:
        mdec=target/'mdec.cpp'
        replace(mdec,'#include "mdec.h"','''#include "mdec.h"
#include "h1_port.h"
#include "h1_sdk.h"
extern "C" { volatile uint32_t h1_mdec_profile[4][2] __attribute__((used,externally_visible)); }
struct H1MdecTimer {
 unsigned kind,start;
 explicit H1MdecTimer(unsigned k):kind(k),start(h1_raw_tick_80hz()){}
 ~H1MdecTimer(){if(h1_ps1_stats.state==3){
  ++h1_mdec_profile[kind][0];h1_mdec_profile[kind][1]+=h1_raw_tick_80hz()-start;
 }}
};''')
        for kind,signature in enumerate([
            'void psxDma1(u32 adr, u32 bcr, u32 chcr) {',
            'static void idct(int *block,int used_col) {',
            'static inline void yuv2rgb15(int *blk, unsigned short *image) {',
            'static void yuv2rgb24(int *blk, u8 *image) {']):
            replace(mdec,signature,signature+'\n H1MdecTimer h1_profile_timer('+str(kind)+');')
    if fast_spans:
        inner=target/'gpu/gpu_unai/gpu_inner.h'
        replace(inner,'#define  CF_LIGHT     ((CF>> 0)&1) // Lighting',
                '#include "raster_fast.h"\n#include "raster_poly4.h"\n#define  CF_LIGHT     ((CF>> 0)&1) // Lighting')
        for signature,color in [
            ('static void gpuTileSpanFn(u16 *pDst, u32 count, u16 data)','data'),
            ('static void gpuPolySpanFn(const gpu_unai_t &gpu_unai, u16 *pDst, u32 count)','gpu_unai.PixelData')]:
            allowed='!CF_MASKCHECK' if 'Tile' in signature else '!CF_TEXTMODE && !CF_GOURAUD && !CF_MASKCHECK'
            replace(inner,signature+'\n{',signature+'\n{\n'
                ' if('+allowed+' && count>=8) {\n'
                '  if(!CF_BLEND){h1_ps1_fill16(pDst,count,'+color+'|(CF_MASKSET?0x8000:0));return;}\n'
                '#ifndef GPU_UNAI_USE_ACCURATE_BLENDING\n'
                '  if(CF_BLENDMODE==0){h1_ps1_blend16(pDst,count,'+color+',CF_MASKSET);return;}\n'
                '#endif\n }')
        signature='static void gpuSpriteSpanFn(u16 *pDst, u32 count, u8* pTxt, u32 u0)'
        replace(inner,signature+'\n{',signature+'\n{\n'
            ' if(CF_TEXTMODE==1 && !CF_LIGHT && !CF_BLEND && !CF_MASKCHECK && !CF_MASKSET && count>=8 &&\n'
            ' h1_ps1_sprite4(pDst,count,pTxt,u0,gpu_unai.TextureWindow[2],gpu_unai.CBA))return;')
        signature='static void gpuPolySpanFn(const gpu_unai_t &gpu_unai, u16 *pDst, u32 count)'
        replace(inner,signature+'\n{',signature+'\n{\n'
            ' if(CF==32 && gpu_unai.v_inc==0 && count>=8){h1_ps1_poly4_horizontal(gpu_unai,pDst,count);return;}')
    if detail:
        inner=target/'gpu/gpu_unai/gpu_inner.h'
        replace(inner,'#define  CF_LIGHT     ((CF>> 0)&1) // Lighting',
                '#include "profile_detail.h"\n#define  CF_LIGHT     ((CF>> 0)&1) // Lighting')
        for kind,signature,count in [
            (0,'static void gpuPolySpanFn(const gpu_unai_t &gpu_unai, u16 *pDst, u32 count)','count'),
            (1,'static void gpuSpriteSpanFn(u16 *pDst, u32 count, u8* pTxt, u32 u0)','count'),
            (2,'static void gpuTileSpanFn(u16 *pDst, u32 count, u16 data)','count'),
            (3,'static u8* gpuPixelSpanFn(u8* pDst, uintptr_t data, ptrdiff_t incr, size_t len)','len')]:
            replace(inner,signature+'\n{',signature+'\n{\n h1_ps1_raster_count('+str(kind)+',CF,'+count+');')
        gte=target/'gte.cpp'
        wrappers='\n#include "profile_detail.h"\n#include "h1_sdk.h"\n'
        operations=[('RTPS',0x01),('RTPT',0x30),('MVMVA',0x12),('NCLIP',0x06),('AVSZ3',0x2d),('AVSZ4',0x2e),
            ('SQR',0x28),('NCCS',0x1b),('NCCT',0x3f),('NCDS',0x13),('NCDT',0x16),('OP',0x0c),('DCPL',0x29),
            ('GPF',0x3d),('GPL',0x3e),('DPCS',0x10),('DPCT',0x2a),('NCS',0x1e),('NCT',0x20),('CC',0x1c),('INTPL',0x11),('CDP',0x14)]
        arguments={'MVMVA','SQR','OP','DCPL','GPF','GPL','DPCS','INTPL'}
        for name,opcode in operations:
            params='u32 gteop' if name in arguments else 'void';args='gteop' if name in arguments else ''
            replace(gte,'void gte'+name+'('+params+') {','static void h1_gte'+name+'_inner('+params+') {')
            wrappers+='void gte'+name+'('+params+') {\n'
            wrappers+=' if(h1_ps1_stats.state!=3){h1_gte'+name+'_inner('+args+');return;}\n'
            wrappers+=' unsigned start=h1_raw_tick_80hz();h1_gte'+name+'_inner('+args+');\n'
            wrappers+=' ++h1_gte_stats['+str(opcode)+'][0];h1_gte_stats['+str(opcode)+'][1]+=h1_raw_tick_80hz()-start;\n}\n'
        with gte.open('a',encoding='utf-8') as f:f.write(wrappers)
    spu=target/'spu/spu_pcsxrearmed/spu.c'
    replace(spu,'static void SetupStreams(void)','static int SetupStreams(void)')
    replace(spu,' spu.XAEnd   = spu.XAStart + 44100;',
            ' if (!spu.pSpuBuffer || !spu.SSumLR || !spu.XAStart) return -1;\n'
            ' spu.XAEnd   = spu.XAStart + 44100;')
    replace(spu,' spu.CDDAEnd   = spu.CDDAStart + 16384;',
            ' if (!spu.CDDAStart) return -1;\n spu.CDDAEnd   = spu.CDDAStart + 16384;')
    replace(spu,' ClearWorkingState();\n}', ' ClearWorkingState();\n return 0;\n}')
    replace(spu,' SetupStreams();                                       // prepare streaming',
            ' if (SetupStreams()<0) return -1;')
    replace(spu,' spu.spuAddr = 0;',
            ' if (!spu.spuMemC || !spu.s_chan || !spu.rvb || !spu.SB) return -1;\n spu.spuAddr = 0;')
    # Use fixed presentation skipping; preserve CPU, timers, VRAM primitives.
    # Skipping rendering can break VRAM readbacks, so default only skips LCD copies.
    misc = target / 'misc.cpp'
    text = misc.read_text(encoding='utf-8')
    text=text.replace('int block = *((int*)b);',
                      'int block = (u8)b[0] | ((u8)b[1]<<8) | ((u8)b[2]<<16) | ((u32)(u8)b[3]<<24);')
    start = text.index('// zlib_open()')
    end = text.index('static const char PcsxHeader', start)
    text = text[:start] + '''
static void *state_open(const char *p, boolean w) { return fopen(p,w?"wb":"rb"); }
static int state_read(void *f,void *b,u32 n) { return fread(b,1,n,(FILE*)f); }
static int state_write(void *f,const void *b,u32 n) { return fwrite(b,1,n,(FILE*)f); }
static long state_seek(void *f,long o,int w) { return fseek((FILE*)f,o,w)?-1:ftell((FILE*)f); }
static int state_close(void *f) { return fclose((FILE*)f); }
int freeze_rw(void *f,enum FreezeMode m,void *b,unsigned n) {
 return (m==FREEZE_LOAD?state_read(f,b,n):state_write(f,b,n))==(int)n?0:-1;
}
struct PcsxSaveFuncs SaveFuncs={state_open,state_read,state_write,state_seek,state_close,-1,-1};
''' + text[end:]
    misc.write_text(text, encoding='utf-8')
    # BIOS loading and standard paths use H1's backslash separator.
    mem = target / 'psxmem.cpp'
    replace(mem, '#include <dirent.h>', '// no POSIX directory API required')
    text=mem.read_text(encoding='utf-8')
    start=text.index('void psxMemReset()')
    end=text.index('void psxMemShutdown()',start)
    text=text[:start]+'''void psxMemReset() {
    memstats_reset();
    memset(psxM,0,0x200000); memset(psxP,0,0x10000); memset(psxR,0,0x80000);
    if (!Config.HLE) {
        char path[MAXPATHLEN];
        snprintf(path,sizeof path,"%s\\\\%s",Config.BiosDir,Config.Bios);
        FILE *f=fopen(path,"rb");
        if (!f || fread(psxR,1,0x80000,f)!=0x80000) Config.HLE=TRUE;
        if(f)fclose(f);
    }
}

'''+text[end:]
    mem.write_text(text,encoding='utf-8')
    cpu=target/'r3000a.cpp'
    replace(cpu, '#include "r3000a.h"', '#include "r3000a.h"\n#include "h1_port.h"')
    replace(cpu, 'void psxBranchTest()\n{',
            'void psxBranchTest()\n{\n\th1_ps1_check_stop();')
    events=target/'psxevents.cpp'
    replace(events,'\tpsxRegs.cycle = 0;',
            '\th1_ps1_disc_adjust(psxRegs.cycle);\n\tpsxRegs.cycle = 0;')
    text=events.read_text(encoding='utf-8')
    events.write_text('extern "C" void h1_ps1_disc_adjust(unsigned);\n'+text,encoding='utf-8')
    return target
