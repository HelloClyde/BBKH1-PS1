"""SDK video-slice GPU upload vs real JIT and ordered core MMIO calls."""
from pathlib import Path
import argparse,json,random,struct,hashlib
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from vlc_hle_equivalence import CPU
from movie_io import fingerprint,pair

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--snapshot',type=Path,required=True)
    args=ap.parse_args();raw=args.snapshot.read_bytes();found=[]
    for off in range(0,len(raw)-596,4):
        if struct.unpack_from('<I',raw,off)[0]!=0x27bdffc0:continue
        w=list(struct.unpack_from('<149I',raw,off))
        if fingerprint(w)==(0x316ccd5a,0x0eb5dd65):found.append(w)
    assert len(found)==1;w=found[0];head=0x80010000;entry=head+44;slots={};global_at=0x80030000;rect=0x80040000;source=0x80080000
    for i in range(148):
        if w[i]>>26==15 and w[i+1]>>26 in (9,35,43) and ((w[i]>>16)&31)==((w[i+1]>>21)&31):
            old=pair(w,i)
            if old not in slots:slots[old]=global_at+len(slots)*4
            p=slots[old];w[i]=(w[i]&0xffff0000)|((p+0x8000)>>16);w[i+1]=(w[i+1]&0xffff0000)|(p&65535)
    payload=struct.pack('<149I',*w);opt=CPU(args.bda,True);jit=CPU(args.reference,True);cpus=(opt,jit)
    real_gpu=bool(opt.m.metadata['options'].get('gpulib') and opt.m.metadata['options'].get('lto'))
    if real_gpu:assert all(c.m.metadata['options'].get('gpulib') for c in cpus)
    for cpu in cpus:
        cpu.put(head,payload);cpu.io={};cpu.writes=[]
        if real_gpu:
            assert '_Z8GPU_initv' in cpu.m.symbols,'use a reference with callable GPU_init'
            assert cpu.call(cpu.m.symbols['_Z8GPU_initv'])==0
            # Fixed pinned gpulib ABI: cmd_buffer[1024], regs[16], vram, status.
            cpu.gpu=cpu.m.symbols['gpu'];cpu.vram=cpu.word(cpu.gpu+4160);assert cpu.vram
        def rd(uc,at,size,data,cpu=cpu):
            a=uc.reg_read(UC_MIPS_REG_A0);assert a in cpu.io,hex(a)
            uc.reg_write(UC_MIPS_REG_V0,cpu.io[a]);uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
        def wr(uc,at,size,data,cpu=cpu):
            a=uc.reg_read(UC_MIPS_REG_A0);v=uc.reg_read(UC_MIPS_REG_A1);assert a in cpu.io,hex(a)
            cpu.writes.append((a,v,cpu.word(cpu.regs+cpu.abi[3])));cpu.io[a]=v
            uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
        if not real_gpu:
            for name,fn in (('_Z11psxHwRead32j',rd),('_Z12psxHwWrite32jj',wr)):
                a=cpu.m.symbols[name];cpu.m.uc.hook_add(UC_HOOK_CODE,fn,begin=a,end=a)
    abi=opt.abi;size,pc_off,cycle_off,io_off=abi[1:5];gpr_off=abi[8]
    admit=opt.m.symbols['h1_ps1_movie_gpu_admit'];run=opt.m.symbols['h1_ps1_movie_gpu_execute'];token=opt.call(admit,entry);assert token
    rng=random.Random(0x4750554d);handled=declined=0;stubs=0;pixel_cases=0;write_cases=0
    for case in range(96):
        mult=(256,384,512,600)[(case+case//12)%4]
        if any('cycle_multiplier' not in c.m.symbols for c in cpus):mult=512
        width=(16,24,32,48,64,128)[case%6];height=(224,240,272)[case%3];delta=4096;status=0x14802000
        mode=case%12
        if mode==0:width=-16
        if mode==1:width=1025
        if mode==2:height=-1
        if mode==3:width=15;height=3
        if mode==4:status=0
        if mode==5:delta=1
        gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0;gpr[17]=rect;gpr[18]=source;gpr[29]=0x801ff000;gpr[31]=0x80018000
        pixels=rng.randbytes(128*272*2);stack=rng.randbytes(64);gte=rng.randbytes(256)
        for cpu in cpus:
            cpu.call(cpu.clear,head,149);cpu.due.clear();cpu.writes=[]
            if real_gpu:
                cpu.call(cpu.m.symbols['_Z15GPU_writeStatusj'],0)
                cpu.m.word(cpu.gpu+4164,status);cpu.m.write(cpu.vram,b'\xa5'*0x100000)
                hw=cpu.word(cpu.m.symbols['psxH']);cpu.m.write(hw,bytes(0x10000));cpu.m.word(hw+0x10f0,0x800)
                # Core-owned nBUSY is a timing bit, deliberately not copied
                # from the renderer by gpuSyncPluginSR(). Seed both halves.
                cpu.m.word(hw+0x1814,status)
            cpu.io={0x1f801814:status,0x1f801810:0,0x1f8010a0:0,0x1f8010a4:0,0x1f8010a8:0}
            for old,new in slots.items():
                value={0x80062a54:1024,0x80062a56:512,0x80062b24:0x1f801814,0x80062b20:0x1f801810,
                    0x80062b28:0x1f8010a0,0x80062b2c:0x1f8010a4,0x80062b30:0x1f8010a8}[old]
                cpu.put(new,struct.pack('<I',value))
            cpu.put(rect,struct.pack('<4h',rng.randrange(512) if cpu is opt else xy[0],rng.randrange(256) if cpu is opt else xy[1],width,height))
            if cpu is opt:xy=struct.unpack('<2h',cpu.m.read(cpu.ram+(rect&0x1fffff),4))
            cpu.put(source,pixels);cpu.put(gpr[29],stack)
            state=bytearray(size);struct.pack_into('<34I',state,gpr_off,*gpr)
            for off,v in ((pc_off,entry),(cycle_off,1000),(io_off,1000+delta),(abi[5],1),(abi[7],cpu.ram)):
                struct.pack_into('<I',state,off,v)
            state[abi[9]+128:abi[9]+384]=gte
            struct.pack_into('<I',state,abi[9]+48,0x10900000);cpu.m.write(cpu.regs,bytes(state))
            if 'cycle_multiplier' in cpu.m.symbols:cpu.m.word(cpu.m.symbols['cycle_multiplier'],mult)
        before=opt.m.read(opt.regs,size);memory=opt.m.read(opt.ram,0x200000)
        if case==6:seed=(before,memory,dict(opt.io))
        yes=opt.call(run,entry,token);result=opt.m.read(opt.regs,size);after=opt.m.read(opt.ram,0x200000)
        if not yes:
            assert result==before and after==memory and not opt.writes,('decline',case);declined+=1;continue
        target=opt.word(opt.regs+pc_off);spent=opt.word(opt.regs+cycle_off)-1000;assert 0<spent<delta
        jit.call(jit.execute,target);reference=jit.m.read(jit.regs,size)
        for off,n in ((gpr_off,136),(pc_off,4),(cycle_off,4),(abi[9],384)):
            assert result[off:off+n]==reference[off:off+n],(case,mult,off,result[off:off+n].hex(),reference[off:off+n].hex(),jit.trace[-10:])
        assert after==jit.m.read(jit.ram,0x200000),('RAM',case)
        if real_gpu:
            assert opt.m.read(opt.vram,0x100000)==jit.m.read(jit.vram,0x100000),('VRAM',case)
            assert opt.m.read(opt.word(opt.m.symbols['psxH']),0x10000)==jit.m.read(jit.word(jit.m.symbols['psxH']),0x10000),('HW',case)
            if status&0x04000000:
                assert opt.m.read(opt.vram,0x100000)!=b'\xa5'*0x100000,('no real pixels transferred',case,
                    opt.m.read(opt.word(opt.m.symbols['psxH'])+0x10a0,12).hex(),
                    hex(opt.word(opt.word(opt.m.symbols['psxH'])+0x10f0)),opt.m.read(opt.gpu,24).hex(),
                    opt.m.read(opt.gpu+4160,160).hex())
                pixel_cases+=1
        else:
            assert opt.writes==jit.writes and opt.io==jit.io,('MMIO',case,opt.writes,jit.writes)
            if status&0x04000000:assert len(opt.writes)==9,('missing observed GPU MMIO writes',case,opt.writes)
            if opt.writes:write_cases+=1
        assert not jit.due;handled+=1
        if case%13==0:
            opt.m.write(opt.regs,before);opt.m.write(opt.ram,memory);opt.io[0x1f801814]=status;opt.writes=[]
            if real_gpu:
                opt.call(opt.m.symbols['_Z15GPU_writeStatusj'],0);opt.m.word(opt.gpu+4164,status);opt.m.write(opt.vram,b'\xa5'*0x100000)
                hw=opt.word(opt.m.symbols['psxH']);opt.m.write(hw,bytes(0x10000));opt.m.word(hw+0x10f0,0x800)
                opt.m.word(hw+0x1814,status)
            if 'h1_movie_output_bytes' in opt.m.symbols:
                opt.m.word(opt.m.symbols['h1_movie_output_pointer'],source&0x1fffff)
                opt.m.word(opt.m.symbols['h1_movie_output_bytes'],len(pixels))
            old=opt.word(opt.m.symbols['h1_movie_hle_stats']+48);opt.call(opt.execute,target)
            assert opt.m.read(opt.regs,size)[gpr_off:gpr_off+136]==result[gpr_off:gpr_off+136];stubs+=1
            if status&0x04000000:assert opt.word(opt.m.symbols['h1_movie_hle_stats']+48)==old+1,('native stub selection',case,old,opt.word(opt.m.symbols['h1_movie_hle_stats']+48),opt.word(opt.m.symbols['h1_movie_output_pointer']),opt.word(opt.m.symbols['h1_movie_output_bytes']),opt.trace[-8:])
    for bad in range(8):
        state,mem,io=seed;opt.m.write(opt.regs,state);opt.m.write(opt.ram,mem);opt.io=dict(io);opt.writes=[]
        def reg(n,v):opt.m.word(opt.regs+gpr_off+n*4,v)
        if bad==0:reg(17,0x1f801000)
        if bad==1:reg(17,rect+2)
        if bad==2:reg(18,0x1f801000)
        if bad==3:reg(18,source+2)
        if bad==4:reg(18,0x801ffffc)
        if bad==5:reg(29,0x801ffff0)
        if bad==6:reg(18,rect)
        if bad==7:opt.put(pair(w,62),struct.pack('<I',0x1f801810))
        before=opt.m.read(opt.regs,size);memory=opt.m.read(opt.ram,0x200000)
        assert opt.call(run,entry,token)==0,('invalid argument accepted',bad)
        assert opt.m.read(opt.regs,size)==before and opt.m.read(opt.ram,0x200000)==memory and not opt.writes,('invalid mutation',bad)
    for i,v in enumerate(w):
        opt.put(head+i*4,struct.pack('<I',v^1));opt.m.word(opt.regs+pc_off,entry);before=opt.m.read(opt.regs,size)
        assert opt.call(run,entry,token)==1 and opt.m.read(opt.regs,size)==before
        opt.put(head+i*4,struct.pack('<I',v))
    report={'ok':True,'sha256':opt.m.metadata['sha256'],'reference_sha256':jit.m.metadata['sha256'],
        'cases':104,'handled':handled,'declined':declined,'invalid_argument_cases':8,'actual_JIT_stubs':stubs,'instruction_mutations_rejected':149,
        'private_snapshot_sha256':hashlib.sha256(raw).hexdigest(),
        'real_gpu':real_gpu,'real_pixel_transfer_cases':pixel_cases,'observed_MMIO_write_cases':write_cases,
        'checks':['full registers/HI/LO/CP0/GTE, RAM, PC, exact original JIT cycles',
            'real gpulib VRAM/HW equality and positive DMA pixel transfers' if real_gpu else 'ordered GPU command/DMA writes with original cycle timestamps',
            'varied positive rectangles and coordinates','clipping, partial blocks and budget decline without mutation',
            'GPU busy hands original timeout helper the matching state','code mutation invalidation']}
    (args.bda.parent/'movie-gpu-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
