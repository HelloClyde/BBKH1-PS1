"""Exact ADPCM memoization vs the unchanged compiled upstream decoder."""
from pathlib import Path
import argparse,hashlib,json,random,struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_SP,UC_MIPS_REG_RA,UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3
from smoke import PS1Machine,ROOT

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);args=ap.parse_args()
    m=PS1Machine(args.bda,b'');sy=m.symbols;rng=random.Random(0x41445043)
    def call(name,*values):
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for reg,value in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),values):m.uc.reg_write(reg,value)
        m.uc.emu_start(sy[name],0,count=1_000_000);assert m.finished,name
    def stats():return struct.unpack('<6I',m.read(sy['h1_spu_adpcm_stats'],24))
    if 'h1_spu_adpcm_cache_reset' in sy:call('h1_spu_adpcm_cache_reset')
    assert stats()==(0,0,0,0,0,0);checks=0
    base=0x83b00000;dest=base+0x100;source=base+0x802
    def check(arena,predictor,shift,src=source):
        nonlocal checks
        m.write(base,arena);call('h1_spu_adpcm_uncached',dest,src,predictor,shift);expected=m.read(base,len(arena))
        m.write(base,arena);call('h1_spu_adpcm_cached',dest,src,predictor,shift)
        assert m.read(base,len(arena))==expected,(checks,predictor,shift,hex(src));checks+=1
    for case in range(1024):
        predictor=case%16;shift=(case//16)%16;arena=bytearray(rng.randbytes(4096))
        if case%7==0:struct.pack_into('<ii',arena,0x100+26*4,0,0)
        if case%11==0:arena[0x802:0x810]=bytes(14)
        arena=bytes(arena);check(arena,predictor,shift);previous=stats()[1]
        check(arena,predictor,shift);assert stats()[1]==previous+1
        changed=bytearray(arena);changed[0x802+(case%14)]^=1;check(bytes(changed),predictor,shift)
        check(arena,predictor,shift^1)
        if predictor==0 or predictor>4:
            check(arena,predictor,shift);previous=stats()[1]
            changed=bytearray(arena);changed[0x100+26*4:0x100+28*4]=rng.randbytes(8)
            check(bytes(changed),predictor,shift);assert stats()[1]==previous+1
        else:
            changed=bytearray(arena);changed[0x100+26*4:0x100+28*4]=rng.randbytes(8);check(bytes(changed),predictor,shift)
    for offset in (-8,-4,0,2,4,20,96,100,104,108,110):
        for predictor in range(5):
            before=stats()[3];check(rng.randbytes(4096),predictor,8,dest+offset);assert stats()[3]==before+1
    for predictor in range(16):
        before=stats()[3];check(rng.randbytes(4096),predictor,8,source+1);assert stats()[3]==before+1
    # Same direct-mapped index, different bytes and histories: no stale hit.
    for _ in range(32):
        arena=rng.randbytes(4096);check(arena,2,7,source);check(arena,3,9,source+1024);check(arena,2,7,source)
    costs=[];arena=bytes(4096)
    for predictor in (0,1,2,4,15):
        counts=[]
        for name in ('h1_spu_adpcm_uncached','h1_spu_adpcm_cached'):
            m.write(base,arena);call('h1_spu_adpcm_cached',dest,source,predictor,8);m.write(base,arena)
            count=[0]
            def step(*unused):count[0]+=1
            hook=m.uc.hook_add(UC_HOOK_CODE,step);call(name,dest,source,predictor,8);m.uc.hook_del(hook);counts.append(count[0])
        costs.append({'predictor':predictor,'uncached_instructions':counts[0],'hit_instructions':counts[1]})
    def body(text,name):
        start=text.index('{',text.index(name+'('));end=start+1;depth=1
        while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
        return text[start:end]
    original=(ROOT/'third_party/pcsx4all/src/spu/spu_pcsxrearmed/spu.c').read_text()
    prepared=(args.bda.parent/'core/spu/spu_pcsxrearmed/spu.c').read_text()
    original_body=body(original,'decode_block_data');assert body(prepared,'h1_spu_adpcm_uncached')==original_body
    report={'ok':True,'sha256':m.metadata['sha256'],'cases':checks,'stats':stats(),'cache_bytes':64*140,
        'original_decoder_body_sha256':hashlib.sha256(original_body.encode()).hexdigest(),'original_decoder_body_unchanged':True,
        'hot_hit_costs':costs,'checks':['all 16 predictors and 16 shifts, arbitrary int32 histories','repeat hits and each encoded byte participates in the key',
            'history-dependent predictors retain both full seed integers','zero-coefficient predictors safely share across different seeds',
            'overlapping input/output and odd source alignment bypass cache','key/index collisions and overwritten source bytes','entire destination, source and canaries match original compiled decoder'],
        'environment':'actual compiled MIPS numeric decoder; instruction counts are not physical FPS'}
    (args.bda.parent/'adpcm-cache-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
