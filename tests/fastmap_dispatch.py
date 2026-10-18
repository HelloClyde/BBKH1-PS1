"""Compare actual full JIT dispatchers on indirect RAM/BIOS branch chains."""
from pathlib import Path
import argparse,json,struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from vlc_hle_equivalence import CPU

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);ap.add_argument('--reference',type=Path,required=True);args=ap.parse_args();results=[]
    pcs=[0xbfc10000+i*64 if i%8==7 else 0x80010000+(i%4)*0x200000+i*64 for i in range(32)]
    for hle in (0,1):
        cpus=[CPU(p,True) for p in (args.reference,args.bda)]
        for cpu in cpus:
            m=cpu.m;sy=m.symbols;m.write(sy['Config']+cpu.abi[6]-4,bytes([hle]))
            for i,pc in enumerate(pcs):
                code=struct.pack('<5I',0x3c098006,0x8d280000+i*4,0x24420001,0x01000008,0)
                if pc>>24==0xbf:m.write(cpu.word(sy['psxR'])+(pc&0x7ffff),code)
                else:cpu.put(pc,code)
            cpu.put(0x80060000,struct.pack('<32I',*(pcs[1:]+pcs[:1])))
        for delta in (256,512,1024,2048):
            snapshots=[];counts=[];dispatchers=[]
            for cpu in cpus:
                m=cpu.m;sy=m.symbols;size,pc_off,cycle_off,io_off=cpu.abi[1:5];state=bytearray(size)
                for off,value in ((pc_off,pcs[0]),(cycle_off,1000),(io_off,5096),(cpu.abi[5],1),(cpu.abi[7],cpu.ram)):
                    struct.pack_into('<I',state,off,value)
                struct.pack_into('<I',state,cpu.abi[9]+48,0x10900000);m.write(cpu.regs,bytes(state));count=[0];events=[0];measuring=[False]
                class Due:
                    def append(self,value):
                        events[0]+=1
                        if events[0]==1:
                            m.word(cpu.regs+io_off,cpu.word(cpu.regs+cycle_off)+delta);count[0]=0;measuring[0]=True
                        else:m.uc.emu_stop()
                cpu.due=Due()
                def step(*unused):
                    if measuring[0]:count[0]+=1
                hook=m.uc.hook_add(UC_HOOK_CODE,step);seen=[];entry_hooks=[]
                for name,address in sy.items():
                    if 'recExecute_' in name and 'return_' in name:
                        def entered(*unused,label=name):seen.append(label)
                        entry_hooks.append(m.uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address))
                m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
                m.uc.emu_start(cpu.word(sy['psxRec']+8),0,count=15_000_000);m.uc.hook_del(hook)
                for entry_hook in entry_hooks:m.uc.hook_del(entry_hook)
                assert events[0]==2 and not m.finished
                assert seen and all(('_indirect_return_' if hle else '_direct_return_') in name for name in seen),seen
                assert all(('_mmap' if m.metadata['options'].get('fast_map') else '_lut') in name for name in seen),seen
                state=m.read(cpu.regs,size)
                snapshots.append((state[cpu.abi[8]:cpu.abi[8]+136],state[pc_off:pc_off+4],state[cycle_off:cycle_off+4],m.read(cpu.ram,0x200000),m.read(cpu.word(sy['psxR']),0x80000)))
                counts.append(count[0])
                dispatchers.append(sorted(set(seen)))
            assert snapshots[0]==snapshots[1],(hle,delta,'full dispatcher state')
            results.append({'hle_bios':bool(hle),'event_delta':delta,'before_instructions':counts[0],'after_instructions':counts[1],'dispatchers':dispatchers})
        for cpu in cpus:
            assert cpu.call(cpu.m.symbols['_Z11psxShutdownv'])==0
            assert not cpu.m.allocations
            if cpu.m.metadata['options'].get('fast_map'):
                st=struct.unpack('<13I',cpu.m.read(cpu.m.symbols['h1_fastmap_stats'],52));assert st[2:4]==(2,0) and st[10]==0 and st[12]==32
    report={'ok':True,'sha256':cpus[1].m.metadata['sha256'],'reference_sha256':cpus[0].m.metadata['sha256'],'cases':len(results),'environment':'actual full MIPS JIT dispatchers + CPU MMU; instruction counts are not physical FPS','checks':['32-target indirect branch chain, all four RAM mirrors and BIOS ROM','direct-return and HLE-safe indirect-return dispatchers','warmed blocks counted between two hardware-event boundaries','all guest GPR/HI/LO, PC, cycles and complete RAM/ROM match','mapping restored and all heap allocations released'],'results':results}
    (args.bda.parent/'fastmap-dispatch.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
