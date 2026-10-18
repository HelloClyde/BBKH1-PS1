"""Full native SDK VLC flow vs original compiled PS1 JIT and interpreter.

Synthetic guest tables, input and relocated instruction signature. Includes
DC versions, predictions, EOB/escape at all three token positions, secondary
lookup, suspend/end and strict event boundaries. Host time is not H1 FPS.
"""
from pathlib import Path
import argparse,json,random,struct
from vlc_hle_equivalence import CPU
from vlc_full_fixture import FULL

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('bda',type=Path);ap.add_argument('--reference',type=Path,required=True)
    args=ap.parse_args();opt=CPU(args.bda,True);jit=CPU(args.reference,True);interp=CPU(args.reference,False)
    assert not jit.m.metadata['options'].get('vlc_hle'),'the original JIT reference must disable VLC HLE'
    cpus=(opt,jit,interp);base=0x80010000;head=base+0x11c
    table,secondary,source,dest=0x80040000,0x80052000,0x80060000,0x80070000
    code=struct.pack('<137I',*FULL)
    for cpu in cpus:cpu.put(base,code)
    admit=opt.m.symbols.get('h1_ps1_vlc_hle_admit')
    token=opt.call(admit,head) if admit else None
    if admit:assert token
    abi=opt.abi;size,pc_off,cycle_off,io_off=abi[1:5];gpr_off=abi[8]
    rng=random.Random(0x46564c43);handled=declined=stub_checks=0;destinations=set();differences={};multipliers=set()
    entries=(0,0x68,0x88,0xa8,0xb0,0xb4,0xd8,0x108,0x110,0x11c,0x15c,0x178,0x17c,0x1a0,0x200)
    # All non-taken conditional paths terminate at the next unconditional
    # bgez zero. Converted forward CMOV paths retain this linear cycle span.
    spans=[]
    for offset in entries:
        for index,word in enumerate(FULL[offset//4:]):
            if word>>16==0x0401:spans.append(index+2);break
        else:raise AssertionError('unbounded linear block')
    reserve=42 if (opt.m.metadata['options'].get('movie_hle') or opt.m.metadata['options'].get('vlc_batch')) else 96
    assert max(spans)==42 and max(spans)<=reserve
    for case in range(240):
        kind=case%16;count=1+case%3;bits=1+case%16
        normal=[rng.randrange(1,0x7000) for _ in range(3)]
        if kind in (3,4,5):normal[kind-3]=0xfe00
        if kind in (6,7,8):normal[kind-6]=0x7c1f
        extra=(normal[1]|((normal[2] if count==3 else 0)<<16)) if count>1 else 0
        word=(normal[0]<<16)|bits
        if 9<=kind<=11:word=0
        table_bytes=struct.pack('<II',word,extra)*8192
        if kind==12:
            table_bytes=b''.join(struct.pack('<II',0 if i%5==0 else ((0xfe00 if i%7==0 else 0x123)<<16)|bits,0) for i in range(8192))
        secondary_word=((0xfe00 if kind==10 else 0x7c1f if kind==11 else 0x321)<<16)|bits
        dc_tables=b''.join(struct.pack('<HH',rng.randrange(1,7),rng.randrange(9)) for _ in range(512))
        stream=rng.randbytes(1024)
        gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0
        gpr[2]=rng.getrandbits(32);gpr[3]=case%16;gpr[4]=source;gpr[5]=dest+(case%2)*2
        gpr[6]=table;gpr[7]=secondary;gpr[12]=rng.randrange(64)<<10;gpr[13]=(case//16)%7
        gpr[14]=dest+(rng.randrange(1,40)*2 if kind>=3 else 4096)
        entry=head
        bad=''
        if kind==13:bad='alias';gpr[5]=source
        if kind==14:bad='write-disabled'
        if kind==15:bad='output-odd';gpr[5]|=1
        if 160<=case<190:
            bad='';gpr[5]=dest;entry=base+entries[(case-160)%15]
            gpr[8]=table+((gpr[2]>>19)<<3);gpr[9]=(0x123<<16)|bits;gpr[1]=bits
            gpr[11]=0x3450234
        if 190<=case<206:
            bad='';gpr[5]=dest;gpr[13]=case%2
            # First EOB followed by the v2/v3 end sentinel, no movie input.
            gpr[2]=0x7fffffff if gpr[13] else 0x3fffffff
            table_bytes=struct.pack('<II',0xfe000001,0)*8192
        if case>=206:
            bad='invalid-RAM';gpr[5]=dest
            mode=(case-206)%12
            if mode==0:gpr[6]=0x1f801000
            if mode==1:gpr[7]=0x1f801000
            if mode==2:gpr[4]=0x1f801000
            if mode==3:gpr[5]=0x1f801000
            if mode==4:gpr[6]=0x80000000
            if mode==5:gpr[4]=0x801ffffe
            if mode==6:gpr[5]=0x801ffffe
            if mode==7:gpr[5]=table
            if mode==8:gpr[5]=secondary
            if mode==9:gpr[5]=base
            if mode==10:gpr[4]|=1
            if mode==11:gpr[6]|=2
        cycle=1000;delta=rng.choice((1,192,193,256,512,1024,4096,10000))
        if case<48:delta=4096
        if case>=160:delta=4096
        mult=512 if case<112 else rng.choice((256,384,512,600))
        if 'cycle_multiplier' not in opt.m.symbols:mult=512
        multipliers.add(mult)
        for cpu in cpus:
            cpu.call(cpu.clear,base,137)
            state=bytearray(size);struct.pack_into('<34I',state,gpr_off,*gpr)
            for off,v in ((pc_off,entry),(cycle_off,cycle),(io_off,cycle+delta),(abi[5],bad!='write-disabled'),(abi[7],cpu.ram)):
                struct.pack_into('<I',state,off,v)
            struct.pack_into('<I',state,abi[9]+48,0x10900000)
            cpu.m.write(cpu.regs,bytes(state))
            if 'cycle_multiplier' in cpu.m.symbols:cpu.m.word(cpu.m.symbols['cycle_multiplier'],mult)
            cpu.put(table-2048,dc_tables);cpu.put(table,table_bytes);cpu.put(secondary,struct.pack('<I',secondary_word)*512)
            cpu.put(source,stream);cpu.put(dest,b'\xa5'*2048);cpu.due.clear()
        before=opt.m.read(opt.regs,size);memory=opt.m.read(opt.ram,0x200000)
        if token is None:
            # Force real admission while the native path declines writes.
            # Original AC returns to head; restore all state afterward.
            opt.m.word(opt.regs+io_off,cycle+10000);opt.m.word(opt.regs+abi[5],0)
            opt.call(opt.execute,head)
            token=1
            opt.m.write(opt.regs,before);opt.m.write(opt.ram,memory)
        if admit:assert opt.call(admit,entry)==token
        yes=opt.call(opt.m.symbols['h1_ps1_vlc_hle_execute'],entry,token)
        result=opt.m.read(opt.regs,size);after=opt.m.read(opt.ram,0x200000)
        if not yes:
            assert result==before and after==memory,(case,bad,'decline mutated state')
            declined+=1;continue
        assert not bad,(case,bad,'unexpected admission')
        spent=struct.unpack_from('<I',result,cycle_off)[0]-cycle
        target=struct.unpack_from('<I',result,pc_off)[0];destinations.add(hex(target-base))
        assert 0<spent<delta,(case,spent,delta)
        n=0
        while jit.word(jit.regs+cycle_off)<cycle+spent:
            jit.call(jit.execute,target);n+=1;assert n<=512,(case,'did not meet target')
        reference=jit.m.read(jit.regs,size)
        for off,length in ((gpr_off,136),(pc_off,4),(cycle_off,4)):
            assert result[off:off+length]==reference[off:off+length],(case,kind,mult,hex(target-base),off,
                result[off:off+length].hex(),reference[off:off+length].hex(),jit.trace[-30:])
        assert jit.m.read(jit.ram,0x200000)==after,(case,'JIT RAM differs')
        assert not jit.due,(case,'crossed hardware event')
        # Match the interpreter at the same observable decoder continuation.
        # The JIT accounts skipped ALU ops converted to CMOV; its cycles can
        # exceed the interpreter. Values and entire guest RAM must agree.
        n=0
        while True:
            interp.call(interp.execute,target);n+=1;assert n<=512,(case,'interpreter target')
            ref=interp.m.read(interp.regs,size)
            if ref[gpr_off:gpr_off+136]==result[gpr_off:gpr_off+136]:break
        assert interp.m.read(interp.ram,0x200000)==after,(case,'interpreter RAM differs')
        differences.setdefault(mult,set()).add(struct.unpack_from('<I',reference,cycle_off)[0]-interp.word(interp.regs+cycle_off))
        if case%7==0:
            opt.m.write(opt.regs,before);opt.m.write(opt.ram,memory);opt.due.clear()
            opt.call(opt.execute,target)
            stub=opt.m.read(opt.regs,size)
            for off,length in ((gpr_off,136),(pc_off,4),(cycle_off,4)):
                assert stub[off:off+length]==result[off:off+length],(case,'actual JIT stub',off)
            assert opt.m.read(opt.ram,0x200000)==after and not opt.due
            stub_checks+=1
        handled+=1
    for i,word in enumerate(FULL):
        opt.put(base+4*i,struct.pack('<I',word^1));before=opt.m.read(opt.regs,size)
        assert opt.call(opt.m.symbols['h1_ps1_vlc_hle_execute'],head,token)==1
        assert opt.m.read(opt.regs,size)==before
        opt.put(base+4*i,struct.pack('<I',word))
    report={'ok':True,'sha256':opt.m.metadata['sha256'],'reference_sha256':jit.m.metadata['sha256'],
        'reference_vlc_hle_disabled':True,
        'cases':240,'handled':handled,'declined_without_changes':declined,'instruction_mutations_rejected':137,
        'continuations':sorted(destinations),'cycle_multipliers':sorted(multipliers),
        'actual_JIT_stub_checks':stub_checks,
        'largest_conservative_linear_block_instructions':max(spans),'native_event_reserve_instructions':reserve,
        'JIT_minus_interpreter_cycles_by_multiplier':{k:sorted(v) for k,v in differences.items()},
        'checks':['all GPR/HI/LO, PC, cycles and entire 2 MiB RAM vs original compiled JIT',
                  'interpreter GPR/HI/LO and entire RAM; separate CMOV timing accounting',
                  'original guest DC tables, prediction, AC primary/secondary, EOB/escape',
                  'strict event boundary, suspend/end continuations, RAM alias fallback',
                  '137 immutable instruction words; no game name or fixed PC']}
    (args.bda.parent/'vlc-full-equivalence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
