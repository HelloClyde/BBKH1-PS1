"""Randomized packet HLE vs actual original JIT and R3000 interpreter.

Requires a user's private PS1 RAM snapshot; no guest instructions, geometry or
RAM are copied into this source or the JSON report. Fixture code is relocated
and all input vertices, packet links, GTE state and streams are synthesized.
"""
from pathlib import Path
import argparse,hashlib,json,random,struct
from unicorn import UC_HOOK_CODE
from vlc_hle_equivalence import CPU

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path)
    ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--snapshot',type=Path,required=True)
    args=ap.parse_args();private=args.snapshot.read_bytes();assert len(private)==0x200000
    opt,jit,interpreter=[CPU(p,j) for p,j in [(args.bda,True),(args.reference,True),(args.reference,False)]]
    cpus=(opt,jit,interpreter);abi=opt.abi;size,pc_off,cycle_off,io_off=abi[1:5];gpr=abi[8]
    admit=opt.m.symbols['h1_ps1_scene_hle_admit'];execute=opt.m.symbols['h1_ps1_scene_hle_execute']
    rng=random.Random(0x53434e45);handled=declined=stubs=mutations=0;cycle_diffs=set();costs=[]
    definitions=[(False,0xadf6c,54,0x10000),(True,0xae054,61,0x10200)]
    for case in range(240):
        quad,source_pc,words,offset=definitions[case%2];pc=(0,0x80000000,0xa0000000)[case%3]+offset+(case%4)*0x200000
        code=list(struct.unpack_from('<%dI'%words,private,source_pc))
        for i,w in enumerate(code):
            if w>>26==2:code[i]=0x08000000|(((pc+(232 if quad else 204))>>2)&0x3ffffff)
        encoded=struct.pack('<%dI'%words,*code)
        state=bytearray(size);state[:pc_off]=rng.randbytes(pc_off);regs=[rng.getrandbits(32) for _ in range(34)];regs[0]=0
        vertex=0x1f800008 if case%5 else 0x80040000
        stream,packet,ordering=0x80030000,0x80080000,0x800a0000
        regs[6]=packet;regs[7]=case%3;regs[8]=stream;regs[16]=vertex;regs[17]=regs[7]+1+case%9
        regs[18]=ordering;regs[19]=0x00ffffff;regs[22]=0xff000000;regs[24]=packet+(32 if quad else 24)
        records=bytearray()
        for i in range(64):
            x,y=rng.randrange(-32768,32768),rng.randrange(-32768,32768)
            records+=struct.pack('<II',(x&65535)|((y&65535)<<16),rng.randrange(0,8000))
        # Include exact wrap/overflow, negative and degenerate NCLIP inputs.
        if case%8 in (0,1,2,3):
            xy=[(0,0),(100,0),(0,100),(100,100)]
            if case%8==1:xy[1],xy[2]=xy[2],xy[1]
            if case%8==2:xy=[(-32768,-32768),(32767,-32768),(-32768,32767),(32767,32767)]
            if case%8==3:xy=[(0,0)]*4
            for i,(x,y) in enumerate(xy):struct.pack_into('<I',records,i*8,(x&65535)|((y&65535)<<16))
        packed=0x03020100 if case<16 else int.from_bytes(bytes(rng.randrange(64) for _ in range(4)),'little')
        if case%17==0 and case>=16:packed=0xff807f00
        stream_data=struct.pack('<I',packed)*96;regs[14]=packed
        mode='' if case<160 else ['event','write-disabled','packet-MMIO','input-MMIO','vertex-MMIO','ordering-MMIO','cursor','packet-input-alias','packet-code-alias','packet-end','vertex-odd','negative-depth'][case%12]
        if mode=='write-disabled':pass
        elif mode=='packet-MMIO':regs[6]=0x1f801810
        elif mode=='input-MMIO':regs[8]=0x1f801000
        elif mode=='vertex-MMIO':regs[16]=0x1f801000
        elif mode=='ordering-MMIO':regs[18]=0x1f801000
        elif mode=='cursor':regs[24]+=4
        elif mode=='packet-input-alias':regs[6]=stream
        elif mode=='packet-code-alias':regs[6]=pc
        elif mode=='packet-end':regs[6]=0x801ffff0
        elif mode=='vertex-odd':regs[16]|=2
        elif mode=='negative-depth':
            for i in range(64):struct.pack_into('<I',records,i*8+4,0xffffff00)
        if mode not in ('cursor',):regs[24]=regs[6]+(32 if quad else 24)
        struct.pack_into('<34I',state,gpr,*regs);struct.pack_into('<I',state,abi[9]+48,0x10900000)
        delta=1 if mode=='event' else rng.choice((255,256,257,300,500,1000,4000,10000))
        if case<4:delta=10000
        for cpu in cpus:
            cpu.call(cpu.clear,pc,words)
            cpu.m.write(cpu.ram,bytes(0x200000));scratch=cpu.word(cpu.m.symbols['psxH']);cpu.m.write(scratch,bytes(65536))
            cpu.put(pc,encoded+struct.pack('<II',0x08000000|(((pc+words*4)>>2)&0x3ffffff),0));cpu.put(stream,stream_data);cpu.put(packet,rng.randbytes(2048) if cpu is opt else packet_bytes)
            if cpu is opt:packet_bytes=cpu.m.read(cpu.ram+(packet&0x1fffff),2048)
            cpu.put(ordering,bytes([0x73])*0x40000)
            if vertex==0x1f800008:cpu.m.write(scratch+8,bytes(records))
            else:cpu.put(vertex,bytes(records))
            s=bytearray(state)
            for off,value in [(pc_off,pc),(cycle_off,1000),(io_off,1000+delta),(abi[5],mode!='write-disabled'),(abi[7],cpu.ram)]:struct.pack_into('<I',s,off,value)
            for i,name in enumerate(('psxM','psxP','psxR','psxH')):struct.pack_into('<I',s,abi[7]+i*4,cpu.word(cpu.m.symbols[name]))
            cpu.m.write(cpu.regs,bytes(s));cpu.due.clear()
        token=opt.call(admit,pc);assert token,(case,'admit')
        before=opt.m.read(opt.regs,size);ram_before=opt.m.read(opt.ram,0x200000);scratch=opt.word(opt.m.symbols['psxH']);scratch_before=opt.m.read(scratch,65536)
        yes=opt.call(execute,pc,token);result=opt.m.read(opt.regs,size);ram_after=opt.m.read(opt.ram,0x200000);scratch_after=opt.m.read(scratch,65536)
        if not yes:
            assert result==before and ram_after==ram_before and scratch_after==scratch_before,(case,'decline mutated state')
            declined+=1;continue
        spent=struct.unpack_from('<I',result,cycle_off)[0]-1000;target=struct.unpack_from('<I',result,pc_off)[0]
        assert 0<spent<delta
        for cpu in (jit,interpreter):
            iterations=0
            while True:
                try:cpu.call(cpu.execute,target)
                except Exception:
                    print('FAILED_REFERENCE',case,quad,mode,cpu is jit,hex(target),spent,'current PC/cycles',hex(cpu.word(cpu.regs+pc_off)),cpu.word(cpu.regs+cycle_off),'trace',jit.trace[-12:]);raise
                iterations+=1;assert iterations<=128,(case,'reference failed to stop')
                actual=cpu.m.read(cpu.regs,size)
                if cpu is jit:
                    if cpu.word(cpu.regs+cycle_off)>=1000+spent:break
                else:
                    a,b=bytearray(actual[:pc_off]),bytearray(result[:pc_off]);a[294:296]=b[294:296]
                    if a==b:break
            for off,length in [(gpr,pc_off),(pc_off,4)]+([(cycle_off,4)] if cpu is jit else []):
                a,b=result[off:off+length],actual[off:off+length]
                if cpu is interpreter and off==gpr:
                    b=bytearray(b);b[294:296]=a[294:296];b=bytes(b) # JIT intentionally skips MFC2 reserved upper-word writeback
                if a!=b:
                    diffs=[(off+i*4,hex(x),hex(y)) for i,(x,y) in enumerate(zip(struct.unpack('<%dI'%(length//4),a),struct.unpack('<%dI'%(length//4),b))) if x!=y]
                    raise AssertionError((case,quad,mode,'jit' if cpu is jit else 'interpreter',diffs,spent,hex(target),jit.trace[-8:]))
            assert cpu.m.read(cpu.ram,0x200000)==ram_after,(case,'RAM',cpu is jit)
            assert cpu.m.read(cpu.word(cpu.m.symbols['psxH']),65536)==scratch_after,(case,'scratch',cpu is jit)
            assert not cpu.due,(case,'crossed event')
        cycle_diffs.add(jit.word(jit.regs+cycle_off)-interpreter.word(interpreter.regs+cycle_off))
        if case%7==0:
            opt.m.write(opt.regs,before);opt.m.write(opt.ram,ram_before);opt.m.write(scratch,scratch_before);opt.due.clear()
            opt.call(opt.execute,target);actual=opt.m.read(opt.regs,size)
            assert actual[:pc_off+4]==result[:pc_off+4] and actual[cycle_off:cycle_off+4]==result[cycle_off:cycle_off+4],(case,'actual JIT admission/stub')
            assert opt.m.read(opt.ram,0x200000)==ram_after and opt.m.read(scratch,65536)==scratch_after and not opt.due
            stubs+=1
        handled+=1
    for quad,source_pc,words,offset in definitions:
        pc=0x80000000+offset;code=list(struct.unpack_from('<%dI'%words,private,source_pc))
        for i,w in enumerate(code):
            if w>>26==2:code[i]=0x08000000|(((pc+(232 if quad else 204))>>2)&0x3ffffff)
        opt.put(pc,struct.pack('<%dI'%words,*code));token=opt.call(admit,pc);assert token
        for i,w in enumerate(code):
            opt.put(pc+i*4,struct.pack('<I',w^1));opt.m.word(opt.regs+pc_off,pc);before=opt.m.read(opt.regs,size)
            assert opt.call(execute,pc,token)==1 and opt.m.read(opt.regs,size)==before,(quad,i,'changed code accepted')
            opt.put(pc+i*4,struct.pack('<I',w));mutations+=1
    # Warmed compiled-MIPS cost for a 64-iteration batch. The original uses
    # ExecuteBlock once per original backedge; this includes its test wrapper
    # and is a local probe, not a whole-game speed estimate.
    for quad,source_pc,words,offset in definitions:
        pc=0x80000000+offset;code=list(struct.unpack_from('<%dI'%words,private,source_pc))
        for i,w in enumerate(code):
            if w>>26==2:code[i]=0x08000000|(((pc+(232 if quad else 204))>>2)&0x3ffffff)
        for clipped in (False,True):
            counts=[];outputs=[]
            for cpu in (jit,opt):
                cpu.call(cpu.clear,0,0x80000);cpu.m.write(cpu.ram,bytes(0x200000))
                cpu.m.write(cpu.word(cpu.m.symbols['psxH']),bytes(65536))
                s=bytearray(size);rs=[0]*34
                for reg,value in [(6,0x80080000),(8,0x80030000),(14,0x03020100),(16,0x1f800008),(17,65),(18,0x800a0000),(19,0xffffff),(22,0xff000000),(24,0x80080000+(32 if quad else 24))]:rs[reg]=value
                struct.pack_into('<34I',s,0,*rs);struct.pack_into('<I',s,264+128+29*4,4096)
                for off,value in [(pc_off,pc),(cycle_off,1000),(io_off,20000),(abi[5],1)]:struct.pack_into('<I',s,off,value)
                for i,name in enumerate(('psxM','psxP','psxR','psxH')):struct.pack_into('<I',s,abi[7]+i*4,cpu.word(cpu.m.symbols[name]))
                vertices=[(0,0),(100,0),(0,100),(100,100)]
                if clipped:vertices[1],vertices[2]=vertices[2],vertices[1]
                vertex_data=b''.join(struct.pack('<II',(x&65535)|((y&65535)<<16),128) for x,y in vertices)
                def reset():
                    cpu.put(pc,struct.pack('<%dI'%words,*code)+struct.pack('<II',0x08000000|(((pc+words*4)>>2)&0x3ffffff),0));cpu.put(0x80030000,struct.pack('<I',0x03020100)*512)
                    cpu.put(0x80080000,bytes(4096));cpu.put(0x800a0000,bytes(0x40000));cpu.m.write(cpu.word(cpu.m.symbols['psxH'])+8,vertex_data)
                    cpu.m.write(cpu.regs,bytes(s));cpu.due.clear()
                def run_batch():
                    if cpu is opt:assert cpu.call(execute,pc,cpu.call(admit,pc))==1
                    else:
                        for _ in range(64):cpu.call(cpu.execute,pc)
                reset();run_batch();reset();count=[0]
                def step(*unused):count[0]+=1
                hook=cpu.m.uc.hook_add(UC_HOOK_CODE,step);run_batch();cpu.m.uc.hook_del(hook)
                counts.append(count[0]);state=cpu.m.read(cpu.regs,size)
                outputs.append((state[:pc_off+4],state[cycle_off:cycle_off+4],cpu.m.read(cpu.ram,0x200000)))
            assert outputs[0]==outputs[1],(quad,clipped,'cost probe state')
            costs.append({'quad':quad,'clipped':clipped,'iterations':64,'before_instructions':counts[0],'after_instructions':counts[1]})
    # Compile a function at a future packet/OT write, mutate it through HLE,
    # then call it again. This verifies actual JIT invalidation, not just RAM.
    invalidation_checks=0
    for ordering_target in (False,True):
        cpu=opt;pc=0x80010000;words=54;code=list(struct.unpack_from('<54I',private,0xadf6c))
        code[30]=0x08000000|((pc+204)>>2&0x3ffffff)
        cpu.call(cpu.clear,0,0x80000);cpu.m.write(cpu.ram,bytes(0x200000));cpu.m.write(cpu.word(cpu.m.symbols['psxH']),bytes(65536))
        cpu.put(pc,struct.pack('<54I',*code)+struct.pack('<II',0x08000000|((pc+216)>>2&0x3ffffff),0))
        helper=0x800a0000 if ordering_target else 0x80080008;reg=8 if ordering_target else 2
        old=0x24000011|(reg<<16);cpu.put(helper,struct.pack('<III',old,0x03e00008,0))
        template=bytearray(size)
        for off,value in [(io_off,100000),(abi[5],1)]:struct.pack_into('<I',template,off,value)
        for i,name in enumerate(('psxM','psxP','psxR','psxH')):struct.pack_into('<I',template,abi[7]+i*4,cpu.word(cpu.m.symbols[name]))
        def call_helper():
            state=bytearray(template);struct.pack_into('<I',state,pc_off,helper);struct.pack_into('<I',state,31*4,0x8001f000)
            cpu.m.write(cpu.regs,bytes(state));cpu.call(cpu.execute,0x8001f000);return cpu.word(cpu.regs+reg*4)
        assert call_helper()==17
        state=bytearray(template);rs=[0]*34
        for r,v in [(6,0x80080000),(8,0x80030000),(14,0x03020100),(16,0x1f800008),(17,2),(18,0x800a0000),(19,0xffffff),(22,0xff000000),(24,0x80080018)]:rs[r]=v
        struct.pack_into('<34I',state,0,*rs);struct.pack_into('<I',state,pc_off,pc)
        cpu.put(0x80030000,struct.pack('<I',0x03020100)*32)
        positions=[0,100,100<<16,0] if ordering_target else [0x24020022,0,0,0]
        cpu.m.write(cpu.word(cpu.m.symbols['psxH'])+8,b''.join(struct.pack('<II',v,0) for v in positions))
        cpu.m.write(cpu.regs,bytes(state));token=cpu.call(admit,pc);assert token and cpu.call(execute,pc,token)==1
        assert call_helper()==(0 if ordering_target else 34),('compiled output was not invalidated',ordering_target)
        invalidation_checks+=1
    full_handled=full_declined=full_stubs=tail_mutations=0
    for case in range(96):
        quad=bool(case%2);original=0xae054 if quad else 0xadf6c;words=61 if quad else 54
        pc=0x80018400 if quad else 0x80018000;tail_pc=pc+(244 if quad else 476)
        code=list(struct.unpack_from('<%dI'%words,private,original))
        for i,w in enumerate(code):
            if w>>26==2:code[i]=0x08000000|((pc+(232 if quad else 204))>>2&0x3ffffff)
        state=bytearray(size);state[:pc_off]=rng.randbytes(pc_off);rs=[rng.getrandbits(32) for _ in range(34)];rs[0]=0
        for r,v in [(6,0x80080000),(7,0),(8,0x80030000),(14,0x03020100),(16,0x1f800008),(17,1+case%8),(18,0x800a0000),(19,0xffffff),(22,0xff000000),(24,0x80080000+(32 if quad else 24)),(29,0x80098000),(30,rs[30]&0xffffff),(31,0x8001f000)]:rs[r]=v
        if case%23==0:rs[29]=0x1f801000
        struct.pack_into('<34I',state,0,*rs);struct.pack_into('<I',state,abi[9]+48,0x10900000)
        stack=rng.randbytes(112);packet_data=rng.randbytes(2048);vdata=bytearray()
        xy=[(0,0),(100,0),(0,100),(100,100)]
        if case%4==1:xy[1],xy[2]=xy[2],xy[1]
        for x,y in xy:vdata+=struct.pack('<II',(x&65535)|((y&65535)<<16),rng.randrange(5000))
        delta=(1,320,321,500,2000,10000)[case%6]
        for cpu in cpus:
            cpu.call(cpu.clear,0,0x80000);cpu.m.write(cpu.ram,bytes(0x200000));cpu.m.write(cpu.word(cpu.m.symbols['psxH']),bytes(65536))
            cpu.put(pc,struct.pack('<%dI'%words,*code));cpu.put(tail_pc,private[0xae148:0xae178])
            if not quad:cpu.put(pc+216,private[0xae044:0xae050])
            cpu.put(0x80030000,struct.pack('<I',0x03020100)*128);cpu.put(0x80080000,packet_data);cpu.put(0x800a0000,bytes([0x73])*0x40000);cpu.put(0x80098000,stack)
            cpu.m.write(cpu.word(cpu.m.symbols['psxH'])+8,bytes(vdata));s=bytearray(state)
            for off,v in [(pc_off,pc),(cycle_off,1000),(io_off,1000+delta),(abi[5],1)]:struct.pack_into('<I',s,off,v)
            for i,name in enumerate(('psxM','psxP','psxR','psxH')):struct.pack_into('<I',s,abi[7]+i*4,cpu.word(cpu.m.symbols[name]))
            cpu.m.write(cpu.regs,bytes(s));cpu.due.clear()
        token=opt.call(admit,pc);assert token
        before=opt.m.read(opt.regs,size);ram=opt.m.read(opt.ram,0x200000)
        yes=opt.call(execute,pc,token);result=opt.m.read(opt.regs,size);after=opt.m.read(opt.ram,0x200000)
        if not yes:
            assert result==before and after==ram;full_declined+=1;continue
        spent=opt.word(opt.regs+cycle_off)-1000;target=opt.word(opt.regs+pc_off);assert 0<spent<delta
        for cpu in (jit,interpreter):
            for _ in range(128):
                cpu.call(cpu.execute,target);actual=cpu.m.read(cpu.regs,size)
                if cpu is jit:
                    if cpu.word(cpu.regs+cycle_off)>=1000+spent:break
                else:
                    a,b=bytearray(actual[:pc_off]),bytearray(result[:pc_off]);a[294:296]=b[294:296]
                    if a==b:break
            else:raise AssertionError((case,'full tail did not stop'))
            for off,length in [(0,pc_off),(pc_off,4)]+([(cycle_off,4)] if cpu is jit else []):
                a,b=result[off:off+length],actual[off:off+length]
                if cpu is interpreter and off==0:b=bytearray(b);b[294:296]=a[294:296];b=bytes(b)
                assert a==b,(case,quad,'full tail state',cpu is jit,off,spent,[(i,hex(x),hex(y)) for i,(x,y) in enumerate(zip(struct.unpack('<%dI'%(length//4),a),struct.unpack('<%dI'%(length//4),b))) if x!=y])
            assert cpu.m.read(cpu.ram,0x200000)==after and not cpu.due,(case,'full tail memory/event')
        if case%7==0:
            opt.m.write(opt.regs,before);opt.m.write(opt.ram,ram);opt.call(opt.execute,target);actual=opt.m.read(opt.regs,size)
            assert actual[:pc_off+4]==result[:pc_off+4] and actual[cycle_off:cycle_off+4]==result[cycle_off:cycle_off+4] and opt.m.read(opt.ram,0x200000)==after
            full_stubs+=1
        full_handled+=1
    for quad in (False,True):
        pc=0x80018400 if quad else 0x80018000;tail_pc=pc+(244 if quad else 476)
        original=0xae054 if quad else 0xadf6c;words=61 if quad else 54
        code=list(struct.unpack_from('<%dI'%words,private,original))
        for i,w in enumerate(code):
            if w>>26==2:code[i]=0x08000000|((pc+(232 if quad else 204))>>2&0x3ffffff)
        opt.put(pc,struct.pack('<%dI'%words,*code))
        opt.put(tail_pc,private[0xae148:0xae178])
        if not quad:opt.put(pc+216,private[0xae044:0xae050])
        token=opt.call(admit,pc);assert token
        locations=list(range(tail_pc,tail_pc+48,4))+([] if quad else list(range(pc+216,pc+228,4)))
        for address in locations:
            word=opt.word(opt.ram+(address&0x1fffff));opt.put(address,struct.pack('<I',word^1));opt.m.word(opt.regs+pc_off,pc);before=opt.m.read(opt.regs,size)
            assert opt.call(execute,pc,token)==1 and opt.m.read(opt.regs,size)==before
            opt.put(address,struct.pack('<I',word));tail_mutations+=1
    report={'ok':True,'sha256':opt.m.metadata['sha256'],'reference_sha256':jit.m.metadata['sha256'],
        'private_fixture_sha256':hashlib.sha256(private).hexdigest(),'cases':240,'handled':handled,'declined_without_changes':declined,
        'instruction_mutations_rejected':mutations,'actual_JIT_stub_checks':stubs,'JIT_minus_interpreter_cycles':sorted(cycle_diffs),
        'native_batch_costs':costs,
        'compiled_output_invalidation_checks':invalidation_checks,
        'function_tail_cases':96,'function_tail_handled':full_handled,'function_tail_declined':full_declined,
        'function_tail_actual_stubs':full_stubs,'tail_instruction_mutations_rejected':tail_mutations,
        'checks':['relocated triangle/quad loops, all RAM mirrors and segments','all GPR/HI/LO, CP0, full raw GTE data/control and PC vs original JIT',
                  'interpreter matches readable state; its MFC2 normalization of reserved OTZ upper 16 bits differs from the original JIT optimization',
                  'exact original JIT cycles; strict event boundary','entire 2 MiB RAM and 64 KiB scratch/MMIO backing','GTE overflow, clipping, negative depths and loop exit',
                  'invalid addresses, output/code/input aliases and write protection decline before mutation','self-modified code rejects immutable token'],
        'environment':'actual compiled MIPS; private fixture; host counts are not physical FPS'}
    (args.bda.parent/'scene-hle-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
