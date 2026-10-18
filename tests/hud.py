"""Render the actual BDA's HUD under MIPS: border isolation and rate wrap."""
from pathlib import Path
import argparse,hashlib,json,struct
from PIL import Image
from unicorn.mips_const import *
from smoke import PS1Machine,ROOT


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);args=ap.parse_args()
    meta=json.loads(args.bda.with_suffix('.build.json').read_text())
    assert hashlib.sha256(args.bda.read_bytes()).hexdigest()==meta['sha256']
    out=ROOT/'build/model/hud-408';out.mkdir(parents=True,exist_ok=True)
    reports=[];images={};fb=0x81d00000;size=480*272*4
    baseline=bytearray(struct.pack('<I',0x00224466)*(480*272))
    for y in range(272):
        for x in list(range(59))+list(range(421,480)):struct.pack_into('<I',baseline,(y*480+x)*4,0)
    baseline=bytes(baseline)
    for case in ['30-60-408','30-60-336','tick-counter-wrap','max-rates','unknown-divider']:
        m=PS1Machine(args.bda,(ROOT/'build/test-rom/H1TEST.exe').read_bytes())
        m.word(0xb0000000,0x40662220);m.word(0xb0000010,0x21000520)
        m.write(fb-32,b'\xa5'*32);m.write(fb,baseline);m.write(fb+size,b'\x5a'*32)
        def call(tick,frames,displayed,erased=0):
            m.finished=False;sp=0x83aff000;m.uc.reg_write(UC_MIPS_REG_SP,sp);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
            for reg,v in zip([UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3],[fb,tick,40,frames]):m.uc.reg_write(reg,v)
            m.word(sp+16,displayed);m.word(sp+20,erased)
            m.uc.emu_start(m.symbols['h1_hud_draw'],0,count=1000000);assert m.finished
            assert m.uc.reg_read(UC_MIPS_REG_SP)==sp
            for i,reg in enumerate(m.saved_regs):assert m.uc.reg_read(reg)==0x12340000+i
        if case=='tick-counter-wrap':call(0xfffffff0,0xfffffff0,0xfffffff0);call(24,44,14)
        else:
            call(40,100,50)
            if case=='30-60-336':m.word(0xb0000010,0x1b000520)
            if case=='unknown-divider':m.word(0xb0000000,0x4066222f)
            call(80,100100 if case=='max-rates' else 160,100050 if case=='max-rates' else 80)
        raw=m.read(fb,size)
        assert m.read(fb-32,32)==b'\xa5'*32 and m.read(fb+size,32)==b'\x5a'*32
        for y in range(272):
            assert raw[(y*480+59)*4:(y*480+421)*4]==baseline[(y*480+59)*4:(y*480+421)*4]
            if y>=24:assert raw[y*480*4:(y+1)*480*4]==baseline[y*480*4:(y+1)*480*4]
        images[case]=raw
        path=out/f'{case}.png';Image.frombytes('RGB',(480,272),raw,'raw','BGRX').save(path)
        # An LCD clear must repaint the cached text without another second.
        m.write(fb,baseline)
        if case=='tick-counter-wrap':call(24,44,14,1)
        else:call(80,100100 if case=='max-rates' else 160,100050 if case=='max-rates' else 80,1)
        assert m.read(fb,size)==raw
        reports.append({'case':case,'viewport_untouched':True,'border_only':True,'canaries_intact':True,'erasure_repaint':True,'image':str(path)})
    assert images['tick-counter-wrap']==images['30-60-408']
    assert images['30-60-336']!=images['30-60-408'] and images['unknown-divider']!=images['30-60-408']
    report={'ok':True,'bda_sha256':meta['sha256'],'scope':'actual BDA HUD instructions and CPM register model; not new physical FPS measurements','cases':reports}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
