"""Exact stack countdown batching vs compiled R3000 interpreter/original JIT."""
from pathlib import Path
import argparse,json,random,struct
from vlc_hle_equivalence import CPU

def words(a,b,c,offset):
    imm=offset&65535
    return [0x8fa00000|(a<<16)|imm,0x8fa00000|(b<<16)|imm,0,
            0x2400ffff|(b<<21)|(c<<16),0x1400fffb|(a<<21),0xafa00000|(c<<16)|imm]

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);ap.add_argument('--reference',type=Path,required=True)
    args=ap.parse_args();opt=CPU(args.bda,True);ref=CPU(args.reference,True);interp=CPU(args.reference,False);cpus=(opt,ref,interp)
    abi=opt.abi;size,pc_off,cyc_off,io_off=abi[1:5];reg_off=abi[8]
    rng=random.Random(0x44454c59);zero=bytes(0x200000);handled=declined=stubs=0
    for case in range(256):
        a,b,c=((2,24,25),(3,8,9),(5,6,7),(8,12,13))[case%4];disp=(0,4,-4,-32768)[case%4]
        head=(0,0x80000000,0xa0000000)[case%3]+0x10000
        slot=(0,0x80000000,0xa0000000)[(case//3)%3]+((case%4)<<21)+0x60020
        p=words(a,b,c,disp);code=struct.pack('<8I',*p,0x08000000|((head>>2)&0x3ffffff),0)
        value=rng.choice((0,1,2,8,0x7fffffff,0x80000000,0xffffffff,100000))
        mult=512 if case<128 or 'cycle_multiplier' not in opt.m.symbols else rng.choice((256,384,512,600))
        cost=(6*mult)>>8;delta=rng.choice((0,1,cost-1,cost,cost+1,2*cost,2*cost+1,513,1024))
        mode='' if case<192 else ('write-disabled','MMIO','scratch','unaligned','code-alias','event-due','cycle-wrap','normal')[case%8]
        if mode=='MMIO':slot=0x1f801070
        if mode=='scratch':slot=0x1f800200
        if mode=='unaligned':slot|=1
        if mode=='code-alias':slot=head+4*(case%6)
        if mode=='event-due':delta=0
        cycle=0xfffffff0 if mode=='cycle-wrap' else 1000
        regs=[rng.getrandbits(32) for _ in range(34)];regs[0]=0;regs[29]=(slot-disp)&0xffffffff
        for cpu in cpus:
            cpu.call(cpu.clear,head,8);cpu.m.write(cpu.ram,zero);cpu.put(head,code)
            if not mode or mode in ('normal','write-disabled','event-due','cycle-wrap'):cpu.put(slot,struct.pack('<I',value))
            state=bytearray(size);struct.pack_into('<34I',state,reg_off,*regs)
            for off,v in ((pc_off,head),(cyc_off,cycle),(io_off,(cycle+delta)&0xffffffff),(abi[5],mode!='write-disabled'),(abi[7],cpu.ram)):
                struct.pack_into('<I',state,off,v)
            struct.pack_into('<I',state,abi[9]+48,0x10900000);cpu.m.write(cpu.regs,bytes(state))
            if 'cycle_multiplier' in cpu.m.symbols:cpu.m.word(cpu.m.symbols['cycle_multiplier'],mult)
            cpu.due.clear()
        token=opt.call(opt.m.symbols['h1_ps1_delay_hle_admit'],head);assert token,(case,'admission')
        before=opt.m.read(opt.regs,size);memory=opt.m.read(opt.ram,0x200000)
        result=opt.call(opt.m.symbols['h1_ps1_delay_hle_execute'],head,token)
        after=opt.m.read(opt.regs,size);ram_after=opt.m.read(opt.ram,0x200000)
        if not result:
            assert before==after and memory==ram_after,(case,'fallback changed state');declined+=1;continue
        n=(struct.unpack_from('<I',after,cyc_off)[0]-cycle)//cost
        assert n>0 and n<=value and n*cost<delta and n<=65536
        for cpu in (ref,interp):
            for _ in range(n):cpu.call(cpu.execute,head)
            state=cpu.m.read(cpu.regs,size)
            fields=[(reg_off,136),(pc_off,4)]+([(cyc_off,4)] if cpu is ref or mult==512 else [])
            for off,length in fields:
                assert after[off:off+length]==state[off:off+length],(case,mult,n,off,after[off:off+length].hex(),state[off:off+length].hex())
            assert cpu.m.read(cpu.ram,0x200000)==ram_after,(case,'RAM')
            if cpu is ref or mult==512:assert not cpu.due,(case,'event boundary')
        if case%7==0:
            opt.m.write(opt.regs,before);opt.m.write(opt.ram,memory);opt.call(opt.execute,head)
            state=opt.m.read(opt.regs,size)
            for off,length in ((reg_off,136),(pc_off,4),(cyc_off,4)):assert after[off:off+length]==state[off:off+length],(case,'actual JIT stub',off)
            assert opt.m.read(opt.ram,0x200000)==ram_after and not opt.due;stubs+=1
        handled+=1
    # The token cannot accept any changed instruction; callers are returned
    # at the same PC and the old compiled entry is invalidated for fallback.
    mutations=0
    for i in range(6):
        opt.put(head+i*4,struct.pack('<I',p[i]^1));before=opt.m.read(opt.regs,size)
        assert opt.call(opt.m.symbols['h1_ps1_delay_hle_execute'],head,token)==1
        assert opt.m.read(opt.regs,size)==before
        assert not opt.call(opt.m.symbols['h1_ps1_delay_hle_admit'],head)
        opt.put(head+i*4,struct.pack('<I',p[i]));mutations+=1
    for a,b,c in ((0,24,25),(29,24,25),(2,29,25),(2,24,29),(2,2,25),(2,24,2),(2,24,24)):
        opt.put(head,struct.pack('<6I',*words(a,b,c,0)))
        assert not opt.call(opt.m.symbols['h1_ps1_delay_hle_admit'],head)
    assert not opt.call(opt.m.symbols['h1_ps1_delay_hle_admit'],0x801fffec)
    report={'ok':True,'sha256':opt.m.metadata['sha256'],'reference_sha256':ref.m.metadata['sha256'],
        'cases':256,'handled':handled,'declined_without_changes':declined,'instruction_mutations_rejected':mutations,
        'actual_JIT_stub_checks':stubs,'checks':['all GPR/HI/LO, PC, cycles and entire 2 MiB RAM vs original JIT',
        'interpreter GPR/HI/LO/PC/RAM; cycles also exact at its fixed multiplier 512',
        'RAM aliases/mirrors and signed stack offsets','zero and unsigned wraparound counters','strict event boundaries and cycle wrap fallback',
        'code/stack aliases, scratch/MMIO, alignment and write isolation fallback','six immutable words, no fixed game/BIOS PC']}
    (args.bda.parent/'delay-hle-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
