"""Streaming PCM output against an independent time-interval integration oracle.

Direct calls use a non-LTO BDA. The output stays below the firmware submission
threshold, so this isolates sample arithmetic/state rather than service timing.
"""
from pathlib import Path
import argparse,json,random,struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine

def trunc_div(value,divisor):return -(abs(value)//divisor) if value<0 else value//divisor

def reference(stereo,rate):
    mono=[trunc_div(l+r,2) for l,r in stereo];duration=len(mono)*32000
    result=[]
    for start in range(0,duration-rate+1,rate):
        end=start+rate;value=0;index=start//32000
        while index*32000<end:
            value+=mono[index]*(min(end,(index+1)*32000)-max(start,index*32000));index+=1
        result.append(trunc_div(value,rate))
    start=len(result)*rate;value=0;index=start//32000
    while index<len(mono):
        value+=mono[index]*((index+1)*32000-max(start,index*32000));index+=1
    return result,duration%rate,value

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);args=ap.parse_args()
    m=PS1Machine(args.bda,b'');sy=m.symbols;rng=random.Random(0x41554449);cases=0;cost=[]
    assert 'gba_audio_write' in sy,'use a non-LTO build with callable gba_audio_write'
    source=0x83000000
    def call(frames,trace=False):
        steps=[0]
        def step(*unused):steps[0]+=1
        hook=m.uc.hook_add(UC_HOOK_CODE,step) if trace else None
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        m.uc.reg_write(UC_MIPS_REG_A0,source);m.uc.reg_write(UC_MIPS_REG_A1,frames)
        m.uc.emu_start(sy['gba_audio_write'],0,count=1_000_000)
        if hook is not None:m.uc.hook_del(hook)
        assert m.finished and m.uc.reg_read(UC_MIPS_REG_V0)==frames
        return steps[0]
    for rate in (44100,48000,32000,22050,11025,32768,65536):
        for fixture in range(24):
            n=min((3500*rate)//32000,rng.randrange(1,2201))
            pairs=([(32767,32767),(-32768,-32768),(32767,-32768),(0,0)]*(n//4+1))[:n] if fixture<4 else [
                (rng.randrange(-32768,32768),rng.randrange(-32768,32768)) for _ in range(n)]
            for name,value in (('active',1),('paused',0),('playing',0),('rate',rate),('used',0),('queued',0),('phase',0),('accumulator',0)):
                m.word(sy[name],value)
            canary=b'\xa5'*16384;m.write(sy['samples'],canary)
            offset=0;chunks=0
            while offset<n:
                count=min(n-offset,rng.choice((1,2,3,31,64,127,512)));part=pairs[offset:offset+count]
                raw=b''.join(struct.pack('<hh',*p) for p in part);m.write(source,raw)
                call(count);assert m.read(source,len(raw))==raw
                offset+=count;chunks+=1
                expected,phase,accumulator=reference(pairs[:offset],rate)
                data=struct.pack('<'+'h'*len(expected),*expected)
                assert m.read(sy['samples'],16384)==data+canary[len(data):],(rate,fixture,offset)
                for name,value in (('used',len(expected)),('queued',len(expected)),('phase',phase),('accumulator',accumulator&0xffffffff)):
                    assert struct.unpack('<I',m.read(sy[name],4))[0]==value,(rate,fixture,name)
            assert chunks;cases+=1
    for rate in (44100,48000):
        for name,value in (('rate',rate),('used',0),('queued',0),('phase',0),('accumulator',0)):
            m.word(sy[name],value)
        m.write(source,struct.pack('<hh',32767,-12345)*882)
        cost.append({'rate':rate,'input_frames':882,'native_instructions':call(882,True)})
    report={'ok':True,'sha256':m.metadata['sha256'],'cases':cases,'native_instruction_counts':cost,
        'checks':['independent output-centric interval integration','signed rounding and full int16 range',
            'random streaming chunk boundaries','all persistent phase/accumulator state','source unchanged and whole output canaries',
            '44100,48000,32000,22050,11025,32768,65536 source rates']}
    (args.bda.parent/'audio-resample-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
