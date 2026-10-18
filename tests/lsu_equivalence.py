"""Folded singleton LSU vs original JIT and real compiled PS1 interpreter.

Exercise RAM mirrors, signed immediates, base/destination aliases, signed and
unsigned reads, stores, non-RAM fallback, merge operations and self-modifying
code. Counts measured on warmed compiled code are not physical H1 FPS.
"""
from pathlib import Path
import argparse,json,random,struct
from unicorn import UC_HOOK_CODE
from vlc_hle_equivalence import CPU

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('bda',type=Path);ap.add_argument('--reference',type=Path,required=True)
    args=ap.parse_args();opt=CPU(args.bda,True);ref=CPU(args.reference,True);interp=CPU(args.reference,False)
    cpus=(opt,ref,interp);head=0x80010000;abi=opt.abi;size,pc_off,cycle_off,io_off=abi[1:5];gpr_off=abi[8]
    rng=random.Random(0x4c535546);opcodes=(0x20,0x21,0x23,0x24,0x25,0x28,0x29,0x2b)
    labels=('LB','LH','LW','LBU','LHU','SB','SH','SW');cost=[];cases=0
    zero=bytes(0x200000);scratch=bytes(0x10000);rom=rng.randbytes(0x80000)
    def setup(cpu,gpr,code,memory,hw=scratch):
        cpu.call(cpu.clear,head,16);cpu.call(cpu.clear,0x80080000,16)
        cpu.m.write(cpu.ram,memory);cpu.put(head,code)
        cpu.m.write(cpu.word(cpu.m.symbols['psxH']),hw)
        cpu.m.write(cpu.word(cpu.m.symbols['psxR']),rom)
        state=bytearray(size);struct.pack_into('<34I',state,gpr_off,*gpr)
        for off,value in ((pc_off,head),(cycle_off,1000),(io_off,1000000),(abi[5],1),(abi[7],cpu.ram)):
            struct.pack_into('<I',state,off,value)
        struct.pack_into('<I',state,abi[9]+48,0x10900000)
        cpu.m.write(cpu.regs,bytes(state));cpu.due.clear()
        return bytes(state)
    def inspect(cpu):
        state=cpu.m.read(cpu.regs,size)
        return (state[gpr_off:gpr_off+136],state[pc_off:pc_off+4],state[cycle_off:cycle_off+4],
                cpu.m.read(cpu.ram,0x200000),cpu.m.read(cpu.word(cpu.m.symbols['psxH']),0x10000))
    for case in range(640):
        if case%128==0:print(f'LSU cases={case}',flush=True)
        which=case%8;op=opcodes[which];width=1 if op in (0x20,0x24,0x28) else 2 if op in (0x21,0x25,0x29) else 4
        imm=rng.choice((-32768,-4096,-128,-1,0,1,4,127,4096,32767))
        mode='RAM';segment=(0,0x80000000,0xa0000000)[case%3]
        if case<512:
            offset=rng.randrange(0x800000)&~(width-1)
            if case%5==0:offset=((case%4)<<21)+(0 if case%2 else 0x1ffffc)
            effective=segment+offset
        else:
            mode=('scratch','ROM','unmapped','IRQ')[case%4]
            effective={'scratch':0x1f800200+(case%32)*4,'ROM':0xbfc01200+(case%32)*4,
                       'unmapped':0x1e000200+(case%32)*4,'IRQ':0x1f801070}[mode]
        base=4;rt=4 if case%11==0 and which<5 else 0 if case%13==0 else 6
        gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0;gpr[base]=(effective-imm)&0xffffffff
        instruction=(op<<26)|(base<<21)|(rt<<16)|(imm&65535)
        code=struct.pack('<5I',instruction,0,(rt<<21)|(10<<11)|0x21,0x08000000|((head>>2)&0x3ffffff),0x256b0001)
        memory=bytearray(zero)
        if mode=='RAM':
            address=effective&0x1fffff;memory[address:address+width]=rng.randbytes(width)
        hw=bytearray(scratch)
        if mode=='scratch':hw[effective&65535:(effective&65535)+width]=rng.randbytes(width)
        for cpu in cpus:setup(cpu,gpr,code,bytes(memory),bytes(hw));cpu.call(cpu.execute,head)
        assert inspect(opt)==inspect(ref),(case,labels[which],mode,'original JIT')
        # IRQ writes can reschedule event fields; all observable memory and
        # registers still agree. Interpreter and JIT use this same PC boundary.
        assert inspect(opt)==inspect(interp),(case,labels[which],mode,'interpreter')
        assert not opt.due and not ref.due,(case,'unexpected event')
        if case<8:
            counts=[]
            for cpu in (ref,opt):
                # The first call warmed every code block. Restore input state
                # and RAM without clearing JIT pointers, excluding compilation.
                state=bytearray(cpu.m.read(cpu.regs,size));struct.pack_into('<34I',state,gpr_off,*gpr)
                for off,value in ((pc_off,head),(cycle_off,1000),(io_off,1000000)):
                    struct.pack_into('<I',state,off,value)
                cpu.m.write(cpu.regs,bytes(state));cpu.m.write(cpu.ram,bytes(memory));cpu.put(head,code)
                count=[0]
                def step(*unused):count[0]+=1
                h=cpu.m.uc.hook_add(UC_HOOK_CODE,step);cpu.call(cpu.execute,head);cpu.m.uc.hook_del(h)
                counts.append(count[0])
            cost.append({'opcode':labels[which],'effective_address':hex(effective),'immediate':imm,'before':counts[0],'after':counts[1]})
        cases+=1
    # Consecutive accesses retain the original series path. Include a final
    # load overwriting the base, after a store needing that original base for
    # code invalidation, and a NOP honoring the PS1 load delay.
    for n in range(64):
        ea=(0,0x80000000,0xa0000000)[n%3]+((n%4)<<21)+0x60020
        imm=(-32768,-128,128,32752)[n%4];last=4 if n%2 else 8
        gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0;gpr[4]=(ea-imm)&0xffffffff
        words=[(0x23<<26)|(4<<21)|(6<<16)|(imm&65535),
               (0x2b<<26)|(4<<21)|(7<<16)|((imm+4)&65535),
               (0x25<<26)|(4<<21)|(last<<16)|((imm+10)&65535),0,
               (6<<21)|(last<<16)|(10<<11)|0x21,0x08000000|((head>>2)&0x3ffffff),0]
        code=struct.pack('<7I',*words);memory=bytearray(zero);memory[0x60000:0x60080]=rng.randbytes(128)
        for cpu in cpus:setup(cpu,gpr,code,bytes(memory));cpu.call(cpu.execute,head)
        assert inspect(opt)==inspect(ref)==inspect(interp),(n,'series fallback')
        cases+=1
    # Merge operations retain upstream code. Verify every byte offset with
    # signed immediate and source/base aliases rather than assuming fallback.
    for op in (0x22,0x26,0x2a,0x2e):
        for n in range(16):
            ea=0x80060020+(n%4);imm=(-32768,-7,7,32767)[n%4]
            gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0;gpr[4]=(ea-imm)&0xffffffff
            code=struct.pack('<5I',(op<<26)|(4<<21)|(6<<16)|(imm&65535),0,0x00c05021,
                             0x08000000|((head>>2)&0x3ffffff),0x256b0001)
            memory=bytearray(zero);memory[0x60000:0x60060]=rng.randbytes(96)
            for cpu in cpus:setup(cpu,gpr,code,bytes(memory));cpu.call(cpu.execute,head)
            assert inspect(opt)==inspect(ref)==inspect(interp),(hex(op),n,'merge fallback')
            cases+=1
    # Compile a target, modify it with the folded store, then run that target
    # again without explicit invalidation. Its new opcode must be recompiled.
    target=0x80080000;smc=0
    for op in (0x28,0x29,0x2b):
        for n in range(16):
            imm=(-32768,-128,128,32767)[n%4];ea=(0,0x80000000,0xa0000000)[n%3]+0x80000+(n%4)*0x200000
            gpr=[0]*34;gpr[4]=(ea-imm)&0xffffffff;gpr[6]=0x24020063 if op==0x2b else 99;gpr[31]=head
            code=struct.pack('<4I',(op<<26)|(4<<21)|(6<<16)|(imm&65535),0,0x08000000|((head>>2)&0x3ffffff),0)
            for cpu in (opt,ref):
                setup(cpu,gpr,code,zero);cpu.put(target,struct.pack('<3I',0x24020001,0x03e00008,0))
                cpu.m.word(cpu.regs+pc_off,target);cpu.call(cpu.execute,head)
                assert cpu.word(cpu.regs+gpr_off+8)==1
                cpu.m.word(cpu.regs+pc_off,head);cpu.call(cpu.execute,head)
                cpu.m.word(cpu.regs+pc_off,target);cpu.call(cpu.execute,head)
                assert cpu.word(cpu.regs+gpr_off+8)==99,(hex(op),n,'stale compiled target')
            assert inspect(opt)==inspect(ref),(hex(op),n,'SMC state')
            smc+=1
    # ADDU(constant, unknown) creates the upstream fuzzy RAM inference. It
    # omits the full runtime address check. Preserve that entire path, even
    # when a signed displacement crosses its inferred region. Such edge
    # cases exercise upstream assumptions, so compare them to the old JIT;
    # ordinary same-region cases also agree with the interpreter.
    fuzzy=0
    for n in range(64):
        op=opcodes[n%8];width=1 if op in (0x20,0x24,0x28) else 2 if op in (0x21,0x25,0x29) else 4
        imm=(-32768,-128,128,32764)[n%4]
        base=(0x60020 if n<32 else (0x10,0x1ffff0)[n%2])&~(width-1)
        gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0;gpr[4]=base
        words=[0x3c058000,0x00a42021,(op<<26)|(4<<21)|(6<<16)|(imm&65535),0,
               0x00c05021,0x08000000|((head>>2)&0x3ffffff),0]
        code=struct.pack('<7I',*words);memory=bytearray(zero)
        effective=(0x80000000+base+imm)&0xffffffff
        address=effective&0x1fffff;memory[address:address+width]=rng.randbytes(width)
        for cpu in cpus:setup(cpu,gpr,code,bytes(memory));cpu.call(cpu.execute,head)
        assert inspect(opt)==inspect(ref),(n,'fuzzy base fallback')
        if n<32:assert inspect(opt)==inspect(interp),(n,'fuzzy same-region interpreter')
        fuzzy+=1
    report={'ok':True,'sha256':opt.m.metadata['sha256'],'reference_sha256':ref.m.metadata['sha256'],
        'cases':cases,'self_modifying_cases':smc,'fuzzy_address_cases':fuzzy,'native_instruction_counts':cost,
        'checks':['all GPR/HI/LO, PC, cycles, full 2 MiB RAM and 64 KiB hardware/scratch memory',
                  'real compiled PS1 interpreter and original MIPS JIT',
                  'all RAM aliases and mirrors; effective address crosses 2 MiB boundary',
                  'signed byte/halfword, unsigned reads, stores, base/destination aliases and zero destination',
                  'scratchpad, ROM, unmapped memory and IRQ MMIO fallback',
                  'consecutive access series, final load overwriting original base, merge operations unchanged',
                  'byte/halfword/word self-modifying stores',
                  'fuzzy RAM inference retains upstream JIT path, including signed-offset region edges']}
    (args.bda.parent/'lsu-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
