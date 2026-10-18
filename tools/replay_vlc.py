"""Compare a private real-game VLC dispatcher snapshot against original JIT.

The snapshot stays in build/. This produces only hashes and equivalence
results; it does not include guest code, movie bytes or private RAM in output.
"""
from pathlib import Path
import argparse,hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from vlc_hle_equivalence import CPU

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('snapshot',type=Path);ap.add_argument('--unit',type=Path,required=True)
    ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--release',type=Path,required=True)
    args=ap.parse_args();unit=CPU(args.unit,True);ref=CPU(args.reference,True);release=CPU(args.release,True)
    cpus=(unit,ref,release);abi=unit.abi;size,pc_off,cycle_off,io_off=abi[1:5];gpr_off=abi[8]
    memory=(args.snapshot/'entry-ram.bin').read_bytes();state=(args.snapshot/'entry-registers.bin').read_bytes()
    assert len(memory)==0x200000 and len(state)==size
    pc=struct.unpack_from('<I',state,pc_off)[0];handled=declined=0
    for cpu in cpus:cpu.m.write(cpu.ram,memory)
    token=unit.call(unit.m.symbols['h1_ps1_vlc_hle_admit'],pc);assert token
    for delta in (1,64,128,192,193,200,256,512,768,1024,2048,4096,8192,16384):
        for cpu in cpus:
            cpu.call(cpu.clear,pc-284,137);cpu.m.write(cpu.ram,memory)
            s=bytearray(state)
            for off,v in ((cycle_off,1000),(io_off,1000+delta),(abi[5],1),(abi[7],cpu.ram)):
                struct.pack_into('<I',s,off,v)
            cpu.m.write(cpu.regs,bytes(s));cpu.due.clear()
        before=unit.m.read(unit.regs,size)
        yes=unit.call(unit.m.symbols['h1_ps1_vlc_hle_execute'],pc,token)
        result=unit.m.read(unit.regs,size);after=unit.m.read(unit.ram,0x200000)
        if not yes:
            assert result==before and after==memory;declined+=1;continue
        target=struct.unpack_from('<I',result,pc_off)[0];cycle=struct.unpack_from('<I',result,cycle_off)[0]
        assert 1000<cycle<1000+delta
        for cpu in (ref,release):
            n=0
            while cpu.word(cpu.regs+cycle_off)<cycle:
                cpu.call(cpu.execute,target);n+=1;assert n<=512
            actual=cpu.m.read(cpu.regs,size)
            for off,length in ((gpr_off,136),(pc_off,4),(cycle_off,4)):
                assert result[off:off+length]==actual[off:off+length],(delta,cpu.m.metadata['sha256'],off)
            assert cpu.m.read(cpu.ram,0x200000)==after and not cpu.due
        handled+=1
    report={'ok':True,'environment':'private real-game state replay in compiled MIPS CPU model; not physical FPS',
        'sha256':release.m.metadata['sha256'],'unit_sha256':unit.m.metadata['sha256'],
        'reference_sha256':ref.m.metadata['sha256'],'snapshot_ram_sha256':hashlib.sha256(memory).hexdigest(),
        'snapshot_state_sha256':hashlib.sha256(state).hexdigest(),'cases':handled+declined,
        'handled':handled,'declined_without_changes':declined,
        'checks':['all GPR/HI/LO, PC, cycles and entire 2 MiB RAM',
                  'real guest Huffman tables and compressed stream',
                  'actual release JIT admission and HLE stub','strict hardware event boundary']}
    (args.release.parent/'vlc-real-replay.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
