"""Exact fast ADPCM arithmetic vs the original compiled numeric decoder."""
from pathlib import Path
import argparse,hashlib,json,random,struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_SP,UC_MIPS_REG_RA,UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3
from smoke import PS1Machine,ROOT

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);args=ap.parse_args()
    m=PS1Machine(args.bda,b'');sy=m.symbols;rng=random.Random(0x46414450)
    def call(name,*values):
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for reg,value in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),values):m.uc.reg_write(reg,value)
        m.uc.emu_start(sy[name],0,count=1_000_000);assert m.finished,name
    base=0x83b00000;dest=base+0x100;source=base+0x802;checks=0
    def check(arena,predictor,shift,src=source):
        nonlocal checks
        m.write(base,arena);call('h1_spu_adpcm_uncached',dest,src,predictor,shift);expected=m.read(base,len(arena))
        m.write(base,arena);call('h1_spu_adpcm_fast',dest,src,predictor,shift)
        assert m.read(base,len(arena))==expected,(checks,predictor,shift,hex(src));checks+=1
    for shift in range(16):
        for byte in range(256):
            arena=bytearray(4096);arena[0x802:0x810]=bytes([byte])*14
            check(bytes(arena),0,shift)
    for case in range(4096):
        arena=bytearray(rng.randbytes(4096));predictor=case%16;shift=(case//16)%16
        if case%7==0:struct.pack_into('<ii',arena,0x100+26*4,0,0)
        if case%11==0:struct.pack_into('<ii',arena,0x100+26*4,-2147483648,2147483647)
        check(bytes(arena),predictor,shift,source+(case%3==0))
    for offset in (-8,-4,0,1,2,4,20,96,100,104,108,110):
        for predictor in range(5):check(rng.randbytes(4096),predictor,8,dest+offset)
    costs=[]
    for predictor in (0,1,2,3,4,15):
        counts=[]
        for name in ('h1_spu_adpcm_uncached','h1_spu_adpcm_fast'):
            m.write(base,bytes(4096));count=[0]
            def step(*unused):count[0]+=1
            hook=m.uc.hook_add(UC_HOOK_CODE,step);call(name,dest,source,predictor,8);m.uc.hook_del(hook);counts.append(count[0])
        costs.append({'predictor':predictor,'before_instructions':counts[0],'after_instructions':counts[1]})
    def body(text,name):
        start=text.index('{',text.index(name+'('));end=start+1;depth=1
        while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
        return text[start:end]
    original=(ROOT/'third_party/pcsx4all/src/spu/spu_pcsxrearmed/spu.c').read_text()
    prepared=(args.bda.parent/'core/spu/spu_pcsxrearmed/spu.c').read_text();old=body(original,'decode_block_data')
    assert body(prepared,'h1_spu_adpcm_uncached')==old
    report={'ok':True,'sha256':m.metadata['sha256'],'cases':checks,'original_decoder_body_unchanged':True,
        'original_decoder_body_sha256':hashlib.sha256(old.encode()).hexdigest(),'native_block_costs':costs,
        'checks':['all 256 input bytes at all 16 shift values','all 16 predictors; arbitrary full int32 histories and boundaries',
            '32-bit multiply wrap and each individual arithmetic rounding preserved','odd source addresses and overlapping input/output',
            'all 28 outputs, source bytes and canaries match actual original compiled decoder'],
        'environment':'actual MIPS numeric kernels; host instruction counts are not physical FPS'}
    (args.bda.parent/'adpcm-fast-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
