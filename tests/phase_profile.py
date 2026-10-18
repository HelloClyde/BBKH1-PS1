"""Actual MIPS exclusive-clock accounting across nesting and frame bins."""
from pathlib import Path
import argparse,json,struct,sys
from vlc_hle_equivalence import CPU
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from phase_profile_data import decode,window,BYTES
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);args=ap.parse_args()
    cpu=CPU(args.bda,True);m=cpu.m;sy=m.symbols
    clock=cpu.word(cpu.word(0x83c00004)+0x6d8)
    now=[10];m.callbacks[clock]=lambda *a:now[0]
    m.word(sy['h1_ps1_stats']+8,3);m.word(sy['h1_ps1_stats']+16,1000)
    frame=sy['h1_phase_frame'];enter=sy['h1_phase_enter'];leave=sy['h1_phase_leave'];p=0x83afe000
    cpu.call(frame,1000)
    now[0]=15;outer=cpu.call(enter,16);assert outer==0
    now[0]=19;inner=cpu.call(enter,19);assert inner==16
    now[0]=21;m.word(p,inner);cpu.call(leave,p)
    now[0]=25;m.word(p,outer);cpu.call(leave,p)
    now[0]=30;cpu.call(frame,1100)
    now[0]=40;cpu.call(frame,12000)
    report=decode(m.read(sy['h1_phase_state'],32),m.read(sy['h1_phase_bins'],BYTES),40)
    rows={r['name']:r['raw_ticks'] for r in window(report,1000,1100)['phases']}
    assert rows['CPU/JIT/other']==10 and rows['SPU synthesis']==8 and rows['PCM output']==2,rows
    assert report['raw_ticks']==30 and report['recording']==0
    before=m.read(sy['h1_phase_bins'],BYTES)
    now[0]=100;assert cpu.call(enter,0)==0xffffffff;cpu.call(leave,p)
    assert m.read(sy['h1_phase_bins'],BYTES)==before
    checks=['nested scopes exclusive','per-frame bin boundary','total equals clock delta','finite final freeze','no writes after freeze']
    if 'h1_phase_cpu_samples' in sy:
        other=CPU(args.bda,True);z=other.m;zs=z.symbols;clock=other.word(other.word(0x83c00004)+0x6d8)
        z.callbacks[clock]=lambda *a:now[0]
        z.word(zs['h1_ps1_stats']+8,3);z.word(zs['h1_ps1_stats']+16,6500)
        z.word(zs['psxRegs']+other.abi[2],0x80012340)
        now[0]=10;other.call(zs['h1_phase_frame'],6500)
        now[0]=15;previous=other.call(zs['h1_phase_enter'],16)
        now[0]=20;z.word(p,previous);other.call(zs['h1_phase_leave'],p)
        z.word(zs['psxRegs']+other.abi[2],0x80022340)
        now[0]=30;previous=other.call(zs['h1_phase_enter'],4)
        now[0]=35;z.word(p,previous);other.call(zs['h1_phase_leave'],p)
        now[0]=40;other.call(zs['h1_phase_frame'],12000)
        meta=struct.unpack('<4I',z.read(zs['h1_phase_cpu_meta'],16))
        rows={key&~1:ticks for key,ticks,count in struct.iter_unpack('<III',z.read(zs['h1_phase_cpu_samples'],1024*12)) if key}
        assert meta[:3]==(20,3,0) and rows=={0x80012340:5,0x80022340:15},(meta,rows)
        checks.append('cooperative CPU boundary bins: correct PCs, exclusive ticks, no dropped samples')
    result={'ok':True,'sha256':m.metadata['sha256'],'checks':checks}
    (args.bda.parent/'phase-profile-equivalence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
