"""Profile PS1 block entries in the host model; not physical wall-time FPS.

This observes the real compiled dispatcher without changing the PS1 core.
Private RAM dumps and disassembly remain in build/, outside release packages.
"""
from pathlib import Path
from collections import Counter
import argparse,json,struct,sys
from unicorn import UC_HOOK_CODE,UC_HOOK_BLOCK
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from smoke import PS1Machine

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('bda',type=Path);ap.add_argument('--game',type=Path,required=True);ap.add_argument('--bios',type=Path,required=True)
    ap.add_argument('--start',type=int,default=2400);ap.add_argument('--end',type=int,default=3000)
    ap.add_argument('--snapshot-pc',type=lambda x:int(x,16),help='Save the first matching dispatcher state in the window; private build data')
    ap.add_argument('--window',action='append',default=[],help='Additional START:END windows in one run; replaces --start/--end')
    ap.add_argument('--jit-instructions',action='store_true',help='Count executed native JIT instructions by guest entry; excludes dispatcher/native plugins')
    ap.add_argument('--directory',type=Path,required=True);args=ap.parse_args();args.directory.mkdir(parents=True,exist_ok=True)
    windows=[tuple(map(int,w.split(':'))) for w in args.window] or [(args.start,args.end)]
    assert all(0<=a<b for a,b in windows)
    args.start=min(a for a,b in windows);args.end=max(b for a,b in windows)
    groups=[{'frames':w,'entries':Counter(),'instructions':Counter()} for w in windows]
    class Profile(PS1Machine):
        def rtc_hook(self,uc,addr,size,data):
            self.profile_frame=struct.unpack('<I',self.read(self.symbols['h1_ps1_stats']+16,4))[0]
            self.active=next((g for g in groups if g['frames'][0]<=self.profile_frame<g['frames'][1]),None)
            # Keep the high-frequency hook out of boot and other unobserved
            # frames. Otherwise its Python overhead can exhaust the run budget
            # before reaching a later window, even with no counts recorded.
            if args.jit_instructions and self.active is not None and self.instruction_hook is None:
                self.instruction_hook=self.uc.hook_add(UC_HOOK_BLOCK,compiled_block,begin=0x81000000,end=0x837fffff)
            elif self.active is None and self.instruction_hook is not None:
                self.uc.hook_del(self.instruction_hook);self.instruction_hook=None
            for g in groups:
                if self.profile_frame>=g['frames'][1] and not g.get('saved'):
                    g['saved']=True
                    ordered=[p for p,n in (g['instructions'] if args.jit_instructions else g['entries']).most_common()]
                    result={'environment':'host JIT instruction counts; not physical CPU time','sha256':self.metadata['sha256'],
                        'frame_window':list(g['frames']),'entries':sum(g['entries'].values()),
                        'native_JIT_instructions':sum(g['instructions'].values()),
                        'blocks':[{'pc':f'{p:08x}','entries':g['entries'][p],'native_JIT_instructions':g['instructions'][p]} for p in ordered]}
                    (args.directory/f"window-{g['frames'][0]}-{g['frames'][1]}.json").write_text(json.dumps(result,indent=2)+'\n')
            if self.profile_frame>=args.start and not self.dumped:
                self.dumped=True
                ram=struct.unpack('<I',self.read(self.symbols['psxRegs']+self.abi[7],4))[0]
                (args.directory/'ram.bin').write_bytes(self.read(ram,0x200000))
                (args.directory/'registers.bin').write_bytes(self.read(self.symbols['psxRegs'],self.abi[1]))
            super().rtc_hook(uc,addr,size,data)
    m=Profile(args.bda,args.game.read_bytes(),path='B:\\PS1\\FF7D1.bin',bios=args.bios.read_bytes())
    m.profile_frame=0;m.dumped=False;m.stop_after=args.end;m.active=None;m.guest_pc=None;m.instruction_hook=None
    m.abi=struct.unpack('<10I',m.read(m.symbols['h1_ps1_abi'],40))
    m.scripted=[(1000,25),(1600,16),(1700,37),(1800,18),(2300,18)];m.release_script=[]
    counts=Counter();dispatches=[]
    with args.bda.with_suffix('.elf').open('rb') as f:
        elf=ELFFile(f);symbols=elf.get_section_by_name('.symtab')
        for s in symbols.iter_symbols():
            if 'recExecute_' not in s.name or s['st_info']['type']!='STT_FUNC':continue
            start,n=s['st_value'],s['st_size']
            for offset in range(0,n,4):
                word=struct.unpack('<I',m.read(start+offset,4))[0]
                if word==0x01000008:dispatches.append(start+offset)
    def entry(uc,pc,size,_):
        if m.active is not None:
            guest=struct.unpack('<I',m.read(m.symbols['psxRegs']+m.abi[2],4))[0]
            counts[guest]+=1;m.active['entries'][guest]+=1;m.guest_pc=guest
            if guest==args.snapshot_pc and not getattr(m,'snapshot_saved',False):
                m.snapshot_saved=True
                ram=struct.unpack('<I',m.read(m.symbols['psxRegs']+m.abi[7],4))[0]
                (args.directory/'entry-ram.bin').write_bytes(m.read(ram,0x200000))
                (args.directory/'entry-registers.bin').write_bytes(m.read(m.symbols['psxRegs'],m.abi[1]))
    for address in dispatches:m.uc.hook_add(UC_HOOK_CODE,entry,begin=address,end=address)
    if args.jit_instructions:
        def compiled_block(uc,pc,size,_):
            if m.active is not None and m.guest_pc is not None:m.active['instructions'][m.guest_pc]+=size//4
        # The service model places generated code in its heap, separate from
        # the BDA text at 0x83c00020. Guest instructions are never run directly.
    elapsed=m.run()
    report={'environment':'compiled MIPS dispatcher in Unicorn; counts are not physical time fractions','sha256':m.metadata['sha256'],
            'frame_window':[args.start,args.end],'host_seconds':elapsed,'dispatch_addresses':[hex(a) for a in dispatches],
            'entries':sum(counts.values()),'blocks':[{'pc':f'{pc:08x}','entries':n} for pc,n in counts.most_common()]}
    report['windows']=[]
    for g in groups:
        ordered=[pc for pc,n in (g['instructions'] if args.jit_instructions else g['entries']).most_common()]
        report['windows'].append({'frame_window':list(g['frames']),'entries':sum(g['entries'].values()),
            'native_JIT_instructions':sum(g['instructions'].values()),
            'blocks':[{'pc':f'{pc:08x}','entries':g['entries'][pc],'native_JIT_instructions':g['instructions'][pc]} for pc in ordered]})
    report['instruction_count_scope']='executed compiled guest blocks in the host model; excludes native C plugins, HLE and dispatcher; not physical CPU time'
    (args.directory/'profile.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report|{'blocks':report['blocks'][:40]},indent=2))
if __name__=='__main__':main()
