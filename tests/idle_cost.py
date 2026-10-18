"""Count executed native MIPS instructions, not host seconds or hardware FPS."""
from pathlib import Path
import argparse,json,struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine,ROOT

def measure(bda):
    m=PS1Machine(bda,(ROOT/'build/test-rom/H1TEST.exe').read_bytes());sy=m.symbols
    abi=struct.unpack('<10I',m.read(sy['h1_ps1_abi'],40))
    _,size,pc_off,cycle_off,io_off,write_off,cpu_off,ram_off,gpr_off,cp0_off=abi
    regs=sy['psxRegs']
    if 'h1_ps1_idle_admit' not in sy:
        # LTO inlines admission into the recompiler. Observe its real emitted
        # stub executing the original SDK-style probe, with real admission.
        observed=[];trace=[None];native=[0];return_pc=[0];entry=sy['h1_ps1_idle_execute']
        def result():
            state=m.read(regs,size);ram=struct.unpack('<I',m.read(sy['psxM'],4))[0]
            sp=struct.unpack_from('<I',state,gpr_off+29*4)[0]
            return {'gpr':list(struct.unpack_from('<34I',state,gpr_off)),
                    'pc':struct.unpack_from('<I',state,pc_off)[0],'cycle':struct.unpack_from('<I',state,cycle_off)[0],
                    'io_cycle_counter':struct.unpack_from('<I',state,io_off)[0],
                    'counter':struct.unpack('<I',m.read(ram+((sp+16)&0x1fffff),4))[0]}
        def count_instruction(uc,address,length,data):
            if address==return_pc[0]:
                observed[0]['native_mips_instructions']=native[0]
                observed[0]['result']=result()|{'handled':uc.reg_read(UC_MIPS_REG_V0)}
                uc.hook_del(trace[0]);trace[0]=None
            elif address!=entry:native[0]+=1
        def enter(uc,address,length,data):
            if observed:return
            observed.append({'probe':'original SDK wait via real JIT stub','input':result()})
            return_pc[0]=uc.reg_read(UC_MIPS_REG_RA)
            trace[0]=uc.hook_add(UC_HOOK_CODE,count_instruction)
        m.uc.hook_add(UC_HOOK_CODE,enter,begin=entry,end=entry)
        m.stop_after=6;m.run()
        assert len(observed)==1 and 'result' in observed[0] and observed[0]['result']['handled']==1
        return {'sha256':m.metadata['sha256'],'options':m.metadata['options'],'cases':observed}
    def word(a):return struct.unpack('<I',m.read(a,4))[0]
    def call(address,*args):
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for reg,value in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),args):m.uc.reg_write(reg,value)
        m.uc.emu_start(address,0,count=2_000_000)
        assert m.finished
        return m.uc.reg_read(UC_MIPS_REG_V0)
    # Populate a PS1 RAM fixture directly, so LTO need not retain an externally
    # callable psxInit. No firmware callbacks occur inside the measured helper.
    ram=0x81000000;m.word(sy['psxM'],ram)
    head,tail,poll,sp=0x80010080,0x80010000,0x80020000,0x801fffe0
    h=[0x3c028002,0x8c420000,0,0x0044102a,0x14400000|(((tail-head-20)//4)&65535),0]
    t=[0x8fa20010,0,0x2442ffff,0xafa20010,0x8fa20010,0,0x14430000|(((head-tail-28)//4)&65535),0]
    m.write(ram+(head&0x1fffff),struct.pack('<6I',*h));m.write(ram+(tail&0x1fffff),struct.pack('<8I',*t))
    token=call(sy['h1_ps1_idle_admit'],head);assert token
    rows=[];count=[0]
    def instruction(uc,address,size,data):count[0]+=1
    for delta,timeout,waiting in [(1,100000,True),(40,100000,True),(200,100000,True),
        (20000,100000,True),(20000,3,True),(20000,100000,False)]:
        state=bytearray(size);gpr=[0]*34;gpr[3]=0xffffffff;gpr[4]=10;gpr[29]=sp
        struct.pack_into('<34I',state,gpr_off,*gpr)
        for offset,value in ((pc_off,head),(cycle_off,100),(io_off,100+delta),(write_off,1),(ram_off,ram)):
            struct.pack_into('<I',state,offset,value)
        m.write(regs,bytes(state));m.word(sy['cycle_multiplier'],512)
        m.word(ram+(poll&0x1fffff),3 if waiting else 12);m.word(ram+((sp+16)&0x1fffff),timeout)
        count[0]=0;hook=m.uc.hook_add(UC_HOOK_CODE,instruction)
        handled=call(sy['h1_ps1_idle_execute'],head,token);m.uc.hook_del(hook)
        state=m.read(regs,size)
        rows.append({'delta':delta,'timeout':timeout,'waiting':waiting,'native_mips_instructions':count[0],
                     'result':{'handled':handled,'gpr':list(struct.unpack_from('<34I',state,gpr_off)),
                     'pc':struct.unpack_from('<I',state,pc_off)[0],'cycle':struct.unpack_from('<I',state,cycle_off)[0],
                     'counter':word(ram+((sp+16)&0x1fffff))}})
    return {'sha256':m.metadata['sha256'],'options':m.metadata['options'],'cases':rows}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('before',type=Path);ap.add_argument('after',type=Path)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    before,after=measure(args.before),measure(args.after)
    for report in (before,after):report['options'].setdefault('detailed_profile',False)
    assert before['options']==after['options'],'compiler and runtime options must match'
    savings=[]
    for old,new in zip(before['cases'],after['cases']):
        if 'input' in old:assert old['input']==new['input']
        assert old['result']==new['result']
        savings.append(1-new['native_mips_instructions']/old['native_mips_instructions'])
    report={'ok':True,'environment':'Unicorn native MIPS instruction count; not physical FPS',
            'before':before,'after':after,'instruction_reduction_by_case':savings,'all_semantic_results_equal':True}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps({'ok':True,'before_sha256':before['sha256'],'after_sha256':after['sha256'],
                     'instructions_before':[c['native_mips_instructions'] for c in before['cases']],
                     'instructions_after':[c['native_mips_instructions'] for c in after['cases']],
                     'instruction_reduction_by_case':savings},indent=2))
if __name__=='__main__':main()
