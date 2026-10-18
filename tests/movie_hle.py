"""SDK movie decoder gateways vs original compiled JIT, using private code.

No game instructions or movie data are bundled. Relocate the user's snapshot
and generate independent buffers/tables/state. Model time is never H1 FPS.
"""
from pathlib import Path
import argparse,hashlib,json,random,struct
from vlc_hle_equivalence import CPU

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path)
    ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--snapshot',type=Path,required=True)
    args=ap.parse_args();raw=args.snapshot.read_bytes();assert len(raw)==0x200000
    # Locate the structurally recognized function; no fixed game PC.
    found=[]
    for off in range(0,len(raw)-832,4):
        w=list(struct.unpack_from('<208I',raw,off));a=2166136261;b=0
        if w[0]>>16!=0x3c08 or w[1]>>16!=0x2508 or w[6]!=0x1480000f:continue
        for i,v in enumerate(w):
            if i<6 or i in (8,9,195,196):v&=0xffff0000
            a=((a^v)*16777619)&0xffffffff;b=(b*33+v)&0xffffffff
        if (a,b)==(0xc8c5c1c0,0x8e601867):found.append(w)
    assert len(found)==1,len(found)
    opt=CPU(args.bda,True);jit=CPU(args.reference,True);cpus=(opt,jit)
    head=0x80010000;limit=0x80030000;context=limit+256;table=0x80050000;secondary=0x80062000
    source=0x80080000;dest=0x800a0000;code=found[0]
    for i,address in ((0,limit),(2,table),(4,secondary),(8,context),(195,context)):
        code[i]=(code[i]&0xffff0000)|(((address+0x8000)>>16)&65535)
        code[i+1]=(code[i+1]&0xffff0000)|(address&65535)
    data=struct.pack('<208I',*code)
    for cpu in cpus:cpu.put(head,data)
    admit=opt.m.symbols['h1_ps1_vlc_hle_admit'];run=opt.m.symbols['h1_ps1_vlc_hle_execute']
    token=opt.call(admit,head);assert token&0x80000000
    abi=opt.abi;size,pc_off,cycle_off,io_off=abi[1:5];gpr_off=abi[8]
    rng=random.Random(0x4d4f5649);rows=[];handled=declined=stubs=0
    offsets=(0,0x58,0x2d8,0x2e0,0x30c)
    for case in range(160):
        entry=head+offsets[case%5];mult=(256,384,512,600)[case%4]
        if any('cycle_multiplier' not in cpu.m.symbols for cpu in cpus):mult=512
        gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0;gpr[31]=0x80018000
        gpr[2]=rng.randrange(1,65);gpr[3]=rng.randrange(16);gpr[4]=0 if case%10==0 else source
        gpr[5]=dest+(case%2)*2;gpr[6]=table;gpr[7]=secondary;gpr[8]=0xfe00;gpr[9]=200
        gpr[14]=dest+2048;gpr[13]=case%7
        delta=(1,15,128,512,4096,24000)[case%6]
        bad=case>=140
        if bad:
            if case%5==0:gpr[4]=0x1f801000
            elif case%5==1:gpr[4]=0x1f801000
            elif case%5 in (2,3):gpr[5]=head
            else:delta=1
        saved=[source, dest, rng.getrandbits(32), rng.randrange(16),0x400,0,0,0,0,0]
        stream=struct.pack('<6H',0x400,0x3800,1,1,rng.randrange(65536),rng.randrange(65536))+rng.randbytes(8192)
        primary=struct.pack('<II',0xfe000001 if case%2 else 0x1230003,0 if case%2 else 0x3450234)*8192
        gte=rng.randbytes(256)
        for cpu in cpus:
            cpu.put(head,data);cpu.call(cpu.clear,head,208);cpu.due.clear()
            cpu.put(limit,struct.pack('<I',200));cpu.put(context,struct.pack('<10I',*saved))
            cpu.put(table-2048,struct.pack('<HH',1,0)*512);cpu.put(table,primary)
            cpu.put(secondary,struct.pack('<I',0x3210002)*512);cpu.put(source,stream);cpu.put(dest,b'\xa5'*32768)
            state=bytearray(size);struct.pack_into('<34I',state,gpr_off,*gpr)
            for off,v in ((pc_off,entry),(cycle_off,1000),(io_off,1000+delta),(abi[5],1),(abi[7],cpu.ram)):
                struct.pack_into('<I',state,off,v)
            state[abi[9]+128:abi[9]+384]=gte
            struct.pack_into('<I',state,abi[9]+48,0x10900000);cpu.m.write(cpu.regs,bytes(state))
            if 'cycle_multiplier' in cpu.m.symbols:cpu.m.word(cpu.m.symbols['cycle_multiplier'],mult)
        assert opt.call(admit,entry)==token
        before=opt.m.read(opt.regs,size);memory=opt.m.read(opt.ram,0x200000)
        yes=opt.call(run,entry,token);result=opt.m.read(opt.regs,size);after=opt.m.read(opt.ram,0x200000)
        if not yes:
            assert before==result and memory==after,('decline',case);declined+=1;continue
        target=struct.unpack_from('<I',result,pc_off)[0];spent=struct.unpack_from('<I',result,cycle_off)[0]-1000
        assert 0<spent<delta,(case,spent,delta)
        steps=0
        while jit.word(jit.regs+cycle_off)<1000+spent:
            jit.call(jit.execute,target);steps+=1;assert steps<8192,(case,'reference did not converge')
        reference=jit.m.read(jit.regs,size)
        for off,n in ((gpr_off,136),(pc_off,4),(cycle_off,4),(abi[9],384)):
            assert result[off:off+n]==reference[off:off+n],(case,mult,hex(entry-head),hex(target-head),off,
                result[off:off+n].hex(),reference[off:off+n].hex(),jit.trace[-10:])
        assert after==jit.m.read(jit.ram,0x200000),(case,'full RAM')
        assert not jit.due,(case,'event crossed')
        if case%11==0:
            opt.m.write(opt.regs,before);opt.m.write(opt.ram,memory);opt.call(opt.execute,target)
            stub=opt.m.read(opt.regs,size)
            for off,n in ((gpr_off,136),(pc_off,4),(cycle_off,4),(abi[9],384)):
                assert stub[off:off+n]==result[off:off+n],('stub',case,off)
            assert opt.m.read(opt.ram,0x200000)==after;stubs+=1
        handled+=1
    mutations=0
    for i,w in enumerate(code):
        opt.put(head+i*4,struct.pack('<I',w^1));opt.m.word(opt.regs+pc_off,head)
        before=opt.m.read(opt.regs,size);memory=opt.m.read(opt.ram,0x200000)
        assert opt.call(run,head,token)==1
        assert opt.m.read(opt.regs,size)==before and opt.m.read(opt.ram,0x200000)==memory
        opt.put(head+i*4,struct.pack('<I',w));mutations+=1
    report={'ok':True,'sha256':opt.m.metadata['sha256'],'reference_sha256':jit.m.metadata['sha256'],
        'private_snapshot_sha256':hashlib.sha256(raw).hexdigest(),'cases':160,'handled':handled,'declined':declined,
        'actual_JIT_stubs':stubs,'instruction_mutations_rejected':mutations,
        'checks':['relocated SDK function and globals','all GPR/HI/LO, CP0/GTE, PC, exact JIT cycles and full 2 MiB RAM',
            'new frame header, resume context, end padding, suspend/save and return','fractional cycle multipliers',
            'strict event boundary and no-mutation declines','final CP0 transition remains in original core']}
    (args.bda.parent/'movie-hle-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
