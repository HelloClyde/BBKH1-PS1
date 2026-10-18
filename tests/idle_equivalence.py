"""Compare wait batching against the actual upstream R3000 interpreter.

Executes cross-compiled MIPS functions. Checks registers, stack timeout, PC,
cycles and first due event boundary across randomized scheduler deadlines.
"""
from pathlib import Path
import json,random,struct,sys
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine,ROOT

def main():
    bda=Path(sys.argv[1]);m=PS1Machine(bda,(ROOT/'build/test-rom/H1TEST.exe').read_bytes())
    sy=m.symbols
    abi=struct.unpack('<10I',m.read(sy['h1_ps1_abi'],40))
    _,size,pc_off,cycle_off,io_off,write_off,cpu_off,ram_off,gpr_off,cp0_off=abi
    regs=sy['psxRegs']
    def word(address):return struct.unpack('<I',m.read(address,4))[0]
    def call(address,*args):
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for r,v in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),args):m.uc.reg_write(r,v)
        m.uc.emu_start(address,0,count=2_000_000)
        assert m.finished,hex(m.uc.reg_read(UC_MIPS_REG_PC))
        return m.uc.reg_read(UC_MIPS_REG_V0)
    m.write(sy['Config']+cpu_off,b'\x01')
    assert call(sy['_Z7psxInitv'])==0
    ram=word(sy['psxM']);execute_block=word(sy['psxInt']+12)
    due=[];deadline=[0]
    def branch(uc,address,n,data):
        cycle=word(regs+cycle_off)
        if cycle>=deadline[0]:due.append((cycle,word(regs+pc_off)))
        uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
    m.uc.hook_add(UC_HOOK_CODE,branch,begin=sy['_Z13psxBranchTestv'],end=sy['_Z13psxBranchTestv'])
    head,tail,poll,sp=0x80010080,0x80010000,0x80020000,0x801fffe0
    head_words=[0x3c028002,0x8c420000,0,0x0044102a,0x14400000|(((tail-head-20)//4)&65535),0]
    tail_words=[0x8fa20010,0,0x2442ffff,0xafa20010,0x8fa20010,0,0x14430000|(((head-tail-28)//4)&65535),0]
    def put_guest(a,data):m.write(ram+(a&0x1fffff),data)
    put_guest(head,struct.pack('<6I',*head_words));put_guest(tail,struct.pack('<8I',*tail_words))
    token=call(sy['h1_ps1_idle_admit'],head);assert token>0
    rng=random.Random(471374);batched=declined=0
    for index in range(320):
        state=bytearray(size)
        gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0;gpr[3]=0xffffffff;gpr[4]=10;gpr[29]=sp
        initial_cycle=rng.randrange(0,100000);delta=rng.choice([1,11,12,13,27,28,29,40,41,55,56,57,rng.randrange(60,3000)])
        timeout=rng.choice([0,1,2,3,17,0xffffffff,0x80000000,100000])
        waiting=index%9!=0
        struct.pack_into('<34I',state,gpr_off,*gpr)
        for offset,value in [(pc_off,head),(cycle_off,initial_cycle),(io_off,initial_cycle+delta),(write_off,1),(ram_off,ram)]:struct.pack_into('<I',state,offset,value)
        struct.pack_into('<I',state,cp0_off+12*4,0x10900000)
        put_guest(poll,struct.pack('<I',3 if waiting else 12));put_guest(sp+16,struct.pack('<I',timeout))
        m.write(regs,bytes(state));m.word(sy['cycle_multiplier'],512)
        handled=call(sy['h1_ps1_idle_execute'],head,token)
        optimized=m.read(regs,size);counter=word(ram+((sp+16)&0x1fffff))
        cycles=struct.unpack_from('<I',optimized,cycle_off)[0]-initial_cycle
        if not handled:
            assert optimized==state and counter==timeout
            declined+=1;continue
        assert cycles>0 and cycles%28==0
        iterations=cycles//28
        m.write(regs,bytes(state));put_guest(sp+16,struct.pack('<I',timeout));due.clear();deadline[0]=initial_cycle+delta
        for _ in range(iterations):call(execute_block,head)
        reference=m.read(regs,size)
        assert optimized[gpr_off:gpr_off+136]==reference[gpr_off:gpr_off+136],(index,iterations)
        assert optimized[pc_off:pc_off+4]==reference[pc_off:pc_off+4]
        assert optimized[cycle_off:cycle_off+4]==reference[cycle_off:cycle_off+4]
        assert word(ram+((sp+16)&0x1fffff))==counter
        if due:assert due[0]==(initial_cycle+cycles,head),(delta,cycles,due)
        # No batch consumes the sentinel iteration (the native fallback owns it).
        assert counter!=0xffffffff or timeout==0xffffffff and iterations==0
        batched+=1
    # Altering any branch-delay opcode must prevent admission.
    put_guest(head+20,struct.pack('<I',0x24420001))
    assert call(sy['h1_ps1_idle_admit'],head)==0
    put_guest(head,struct.pack('<6I',*head_words))
    # A runtime change in ANY admitted instruction must deoptimize, rather
    # than execute a stale decoded description or the stale compiled block.
    mutation_checks=0
    for address,words in ((head,head_words),(tail,tail_words)):
        for index,original in enumerate(words):
            put_guest(address+index*4,struct.pack('<I',original^1))
            m.write(regs,bytes(state));put_guest(sp+16,struct.pack('<I',timeout))
            assert call(sy['h1_ps1_idle_execute'],head,token)==1
            assert m.read(regs,size)==state and word(ram+((sp+16)&0x1fffff))==timeout
            put_guest(address+index*4,struct.pack('<I',original));mutation_checks+=1
    # Recompiling the same PC with different valid code must allocate a new
    # token; the old emitted stub must never inherit the replacement's data.
    put_guest(head,struct.pack('<I',head_words[0]+1))
    new_token=call(sy['h1_ps1_idle_admit'],head);assert new_token and new_token!=token
    m.write(regs,bytes(state));put_guest(sp+16,struct.pack('<I',timeout))
    assert call(sy['h1_ps1_idle_execute'],head,token)==1 and m.read(regs,size)==state
    put_guest(head,struct.pack('<I',head_words[0]))
    assert call(sy['h1_ps1_idle_admit'],head)==token
    # Exhausting the admission table must only disable NEW optimizations.
    exhausted=0
    for index in range(140):
        other_head=0x80040080+index*256;other_tail=other_head-128
        put_guest(other_head,struct.pack('<6I',*head_words));put_guest(other_tail,struct.pack('<8I',*tail_words))
        if not call(sy['h1_ps1_idle_admit'],other_head):exhausted+=1
    assert exhausted>0 and call(sy['h1_ps1_idle_admit'],head)==token
    report={'ok':True,'sha256':m.metadata['sha256'],'reference':'actual PCSX4ALL R3000 interpreter, compiled MIPS',
            'cases':320,'batched':batched,'declined_without_state_changes':declined,
            'register_memory_pc_cycle_equivalence':True,'first_due_event_boundary':True,'modified_code_rejected':True,
            'runtime_instruction_mutations_rejected':mutation_checks,'immutable_tokens_after_recompile':True,
            'table_exhaustion_retains_existing_tokens':True}
    (bda.parent/'idle-equivalence.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
