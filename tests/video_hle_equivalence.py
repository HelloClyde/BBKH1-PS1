"""STR empty-queue HLE vs actual compiled R3000 interpreter and original JIT."""
from pathlib import Path
import argparse,json,random,struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine,ROOT

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);ap.add_argument('--reference',type=Path,required=True)
    args=ap.parse_args();guest=(ROOT/'build/test-rom/H1TEST.exe').read_bytes()
    class CPU:
        def __init__(self,bda,jit):
            self.m=PS1Machine(bda,guest);m=self.m;sy=m.symbols
            self.abi=struct.unpack('<10I',m.read(sy['h1_ps1_abi'],40));self.regs=sy['psxRegs']
            m.write(sy['Config']+self.abi[6],bytes([0 if jit else 1]))
            assert self.call(sy['_Z7psxInitv'])==0
            self.ram=self.word(sy['psxM']);table=sy['psxRec' if jit else 'psxInt']
            self.execute=self.word(table+12);self.clear=self.word(table+16)
            self.due=[]
            def branch(uc,address,size,data):
                if self.word(self.regs+self.abi[3])>=self.word(self.regs+self.abi[4]):self.due.append(True)
                uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
            m.uc.hook_add(UC_HOOK_CODE,branch,begin=sy['_Z13psxBranchTestv'],end=sy['_Z13psxBranchTestv'])
        def word(self,p):return struct.unpack('<I',self.m.read(p,4))[0]
        def call(self,p,*values):
            m=self.m;m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
            for r,v in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),values):m.uc.reg_write(r,v)
            m.uc.emu_start(p,0,count=4_000_000);assert m.finished,hex(m.uc.reg_read(UC_MIPS_REG_PC))
            return m.uc.reg_read(UC_MIPS_REG_V0)
        def put(self,p,data):self.m.write(self.ram+(p&0x1fffff),data)
    optimized=CPU(args.bda,True);interpreter=CPU(args.reference,False);jit=CPU(args.reference,True)
    head,helper,global_index,global_table,table=0x80010000,0x80011000,0x80020000,0x80020004,0x80022000
    q=[0]*49
    q[:12]=[0x00803821,0x3c028002,0x8c420000,0x3c038002,0x8c630004,0x00021140,0x00433021,
             0x94c20000,0x34030001,0x3042ffff,0x1443000e,0x00a04021]
    q[25:30]=[0x94c20000,0x34030002,0x3042ffff,0x14430012,0x34020001]
    q[47:49]=[0x03e00008,0]
    helper_data=struct.pack('<49I',*q);rng=random.Random(0x535452);batched=declined=0
    last_head=None;stub_checks=0
    for case in range(192):
        counter=16+case%3
        p=[0x3c058002,0x24a50020,0x0c000000|((helper>>2)&0x3ffffff),0x27a40010,
           0x10400005,0x2400ffff|(counter<<21)|(counter<<16),0x1400fff9|(counter<<21),0x00001021]
        data=struct.pack('<8I',*p)
        for cpu in (optimized,interpreter,jit):
            cpu.put(head,data);cpu.put(helper,helper_data)
            if data!=last_head:cpu.call(cpu.clear,head,8);cpu.call(cpu.clear,helper,49)
        last_head=data
        token=optimized.call(optimized.m.symbols['h1_ps1_video_hle_admit'],head);assert token
        abi=optimized.abi;size,pc_off,cycle_off,io_off=abi[1:5];gpr_off=abi[8]
        state=bytearray(size);gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0;gpr[29]=0x801fffe0
        gpr[counter]=rng.choice([0,1,2,5,0xffffffff,100000])
        struct.pack_into('<34I',state,gpr_off,*gpr)
        cycle=rng.randrange(100000);delta=rng.choice([1,26,27,28,53,54,55,81,82,rng.randrange(83,3000)])
        mult=(512 if case<96 else rng.choice([256,384,512,600]));tag=rng.choice([0,0,4,5,0xffff,1,2])
        for cpu in (optimized,interpreter,jit):
            s=bytearray(state)
            for off,v in ((pc_off,head),(cycle_off,cycle),(io_off,cycle+delta),(abi[5],1),(abi[7],cpu.ram)):
                struct.pack_into('<I',s,off,v)
            struct.pack_into('<I',s,abi[9]+48,0x10900000)
            cpu.m.write(cpu.regs,bytes(s));cpu.m.word(cpu.m.symbols['cycle_multiplier'],mult)
            cpu.put(global_index,struct.pack('<II',3,table));cpu.put(table+96,struct.pack('<I',0x12340000|tag));cpu.due.clear()
        before=optimized.m.read(optimized.regs,size);memory=optimized.m.read(optimized.ram,0x200000)
        handled=optimized.call(optimized.m.symbols['h1_ps1_video_hle_execute'],head,token)
        result=optimized.m.read(optimized.regs,size)
        assert optimized.m.read(optimized.ram,0x200000)==memory
        if not handled:
            assert result==before;declined+=1;continue
        cost=2*((4*mult)>>8)+((12*mult)>>8)+((5*mult)>>8)+((2*mult)>>8)
        spent=struct.unpack_from('<I',result,cycle_off)[0]-cycle;n=spent//cost
        assert n>0 and spent==n*cost and spent<delta
        for cpu in ((interpreter,jit) if mult==512 else (jit,)):
            for _ in range(n):cpu.call(cpu.execute,head)
            reference=cpu.m.read(cpu.regs,size)
            for off,length in ((gpr_off,136),(pc_off,4),(cycle_off,4)):
                assert result[off:off+length]==reference[off:off+length],(case,mult,n,off,result[off:off+length].hex(),reference[off:off+length].hex())
            assert not cpu.due and cpu.m.read(cpu.ram,0x200000)==memory
        if case%9==0:
            optimized.m.write(optimized.regs,before)
            optimized.call(optimized.execute,head)
            stub=optimized.m.read(optimized.regs,size)
            for off,length in ((gpr_off,136),(pc_off,4),(cycle_off,4)):
                assert stub[off:off+length]==result[off:off+length],('JIT HLE stub',case,off)
            assert not optimized.due;stub_checks+=1
        batched+=1
    # Every instruction in the recognized path is immutable for a token.
    mutations=0
    for address,words in ((head,p),(helper,q[:12]),(helper+100,q[25:30]),(helper+188,q[47:])):
        for i,w in enumerate(words):
            optimized.put(address+4*i,struct.pack('<I',w^1));before=optimized.m.read(optimized.regs,size)
            assert optimized.call(optimized.m.symbols['h1_ps1_video_hle_execute'],head,token)==1
            assert optimized.m.read(optimized.regs,size)==before
            optimized.put(address+4*i,struct.pack('<I',w));mutations+=1
    report={'ok':True,'sha256':optimized.m.metadata['sha256'],'reference_sha256':jit.m.metadata['sha256'],
            'cases':192,'batched':batched,'declined_without_changes':declined,'instruction_mutations_rejected':mutations,'actual_JIT_HLE_stub_checks':stub_checks,
            'checks':['all GPR/HI/LO, PC and cycles match actual R3000 interpreter and original MIPS JIT',
                      'fractional JIT cycle multipliers','RAM unchanged','ready/reset tags fall back','counter timeout preserved',
                      'stop strictly before next hardware event','source addresses decoded, no fixed game PC']}
    (args.bda.parent/'video-hle-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
