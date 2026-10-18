"""Private SDK stream/DMA gateways vs original MIPS JIT.

MMIO is observed through the real core entry points with deterministic status;
physical FF7 subsequently verifies actual DMA/MDEC and visible playback.
"""
from pathlib import Path
import argparse,json,random,struct,hashlib
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from vlc_hle_equivalence import CPU

def pair(w,i):return ((w[i]&65535)<<16)+struct.unpack('<h',struct.pack('<H',w[i+1]&65535))[0]
def fingerprint(w):
    norm=set()
    for i in range(len(w)-1):
        if w[i]>>26==15 and w[i+1]>>26 in (9,35,43) and ((w[i]>>16)&31)==((w[i+1]>>21)&31):norm.update((i,i+1))
    a=2166136261;b=0
    for i,v in enumerate(w):
        if i in norm:v&=0xffff0000
        if v>>26==3:v&=0xfc000000
        a=((a^v)*16777619)&0xffffffff;b=(b*33+v)&0xffffffff
    return a,b
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--snapshot',type=Path,required=True)
    args=ap.parse_args();raw=args.snapshot.read_bytes();opt=CPU(args.bda,True);jit=CPU(args.reference,True);cpus=(opt,jit)
    for cpu in cpus:
        cpu.io={};cpu.writes=[]
        def rd(uc,address,size,data,cpu=cpu):
            a=uc.reg_read(UC_MIPS_REG_A0);assert a in cpu.io,hex(a)
            uc.reg_write(UC_MIPS_REG_V0,cpu.io[a]);uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
        def wr(uc,address,size,data,cpu=cpu):
            a=uc.reg_read(UC_MIPS_REG_A0);v=uc.reg_read(UC_MIPS_REG_A1);assert a in cpu.io,hex(a)
            cpu.writes.append((a,v,cpu.word(cpu.regs+cpu.abi[3])));cpu.io[a]=v
            uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
        for name,hook in (('_Z11psxHwRead32j',rd),('_Z12psxHwWrite32jj',wr)):
            at=cpu.m.symbols[name];cpu.m.uc.hook_add(UC_HOOK_CODE,hook,begin=at,end=at)
    abi=opt.abi;size,pc_off,cycle_off,io_off=abi[1:5];gpr_off=abi[8];rng=random.Random(0x4d444543)
    admit=opt.m.symbols['h1_ps1_movie_io_admit'];run=opt.m.symbols['h1_ps1_movie_io_execute']
    head=0x80010000;helper=head+0x1000;globals_at=0x80030000;buffer=0x80080000;table=0x80040000
    handled=declined=stubs=mutations=negative=0;reports=[];write_cases=0
    full_mmio_hooks=not any(c.m.metadata['options'].get('lto') for c in cpus)
    definitions=((0,49,(0x852a4dd9,0xedadc33a)),(1,37,(0x10f08a28,0x11e2f8d1)),(2,36,(0x57fc96ef,0x2a4a306c)))
    for kind,n,signature in definitions:
        matches=[]
        for off in range(0,len(raw)-196,4):
            first=struct.unpack_from('<I',raw,off)[0]
            if first!=(0x00803821 if kind==0 else 0x27bdffe0):continue
            w=list(struct.unpack_from('<'+str(n)+'I',raw,off))
            if fingerprint(w)==signature:matches.append((off,w))
        assert len(matches)==1,(kind,len(matches));oldhead,words=matches[0];sync=[]
        if kind:
            oldhelper=(words[5]&0x3ffffff)<<2;sync=list(struct.unpack_from('<38I',raw,oldhelper&0x1fffff));words[5]=0x0c000000|((helper>>2)&0x3ffffff)
        slots={}
        for w in (words,sync):
            for i in range(len(w)-1):
                if w[i]>>26!=15 or w[i+1]>>26 not in (9,35,43) or ((w[i]>>16)&31)!=((w[i+1]>>21)&31):continue
                old=pair(w,i)
                if old not in slots:slots[old]=globals_at+len(slots)*4
                p=slots[old];w[i]=(w[i]&0xffff0000)|((p+0x8000)>>16);w[i+1]=(w[i+1]&0xffff0000)|(p&65535)
        payload=struct.pack('<'+str(n)+'I',*words);helper_data=struct.pack('<38I',*sync) if kind else b''
        for cpu in cpus:
            cpu.m.write(cpu.ram,bytes(0x200000))
            cpu.put(head,payload)
            if kind:cpu.put(helper,helper_data)
        token=opt.call(admit,head);assert token,(kind,'admission')
        globals_values={new:struct.unpack_from('<I',raw,old&0x1fffff)[0] for old,new in slots.items()}
        if not kind:
            index_addr=pair(words,1);table_addr=pair(words,3);mode_addr=pair(words,12);total_addr=pair(words,33)
        for case in range(64):
            mult=(256,384,512,600)[case%4]
            if any('cycle_multiplier' not in c.m.symbols for c in cpus):mult=512
            gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0;gpr[4]=buffer;gpr[5]=64+(case%4)*32;gpr[29]=0x801ff000;gpr[31]=0x80018000
            delta=1 if case%9==0 else 4096;entry=head;encoded=token
            values=dict(globals_values);status=0
            if not kind:
                gpr[4]=0x80050000;gpr[5]=0x80050004
                index=case%4;values.update({index_addr:index,table_addr:table,mode_addr:(case//4)%2,total_addr:17})
                tags=[(case//8)%4]*4;tags[index]=(0,1,2,4)[case%4]
            elif case>=40:
                stage=1+case%2;entry=helper+(48 if stage==1 else 104);encoded=opt.call(admit,entry);assert encoded
                status=0x20000000 if kind==1 else 0x01000000;gpr[3]=status;gpr[4]=0xffffffff;gpr[2]=rng.getrandbits(32)
            gte=rng.randbytes(256)
            for cpu in cpus:
                cpu.call(cpu.clear,head,n);cpu.call(cpu.clear,helper,38);cpu.due.clear();cpu.writes=[]
                cpu.io={0x1f8010f0:0xd003,0x1f801080:0,0x1f801084:0,0x1f801088:0,0x1f801820:0,0x1f801824:0,
                    0x1f801090:0,0x1f801094:0,0x1f801098:0}
                cpu.io[0x1f801824 if kind==1 else 0x1f801098]=status
                for address,v in values.items():cpu.put(address,struct.pack('<I',v))
                cpu.put(buffer,struct.pack('<I',0x38000040)+rng.randbytes(256)) if cpu is opt else None
                if cpu is jit:cpu.put(buffer,opt.m.read(opt.ram+(buffer&0x1fffff),260))
                cpu.put(0x801fefc0,b'\xa5'*256)
                if not kind:
                    for i,tag in enumerate(tags):cpu.put(table+i*32,struct.pack('<I',0x12340000|tag))
                    cpu.put(0x80050000,b'\xa5'*8)
                else:cpu.put(gpr[29]+16,struct.pack('<I',case%5))
                state=bytearray(size);struct.pack_into('<34I',state,gpr_off,*gpr)
                for off,v in ((pc_off,entry),(cycle_off,1000),(io_off,1000+delta),(abi[5],1),(abi[7],cpu.ram)):
                    struct.pack_into('<I',state,off,v)
                state[abi[9]+128:abi[9]+384]=gte
                struct.pack_into('<I',state,abi[9]+48,0x10900000);cpu.m.write(cpu.regs,bytes(state))
                if 'cycle_multiplier' in cpu.m.symbols:cpu.m.word(cpu.m.symbols['cycle_multiplier'],mult)
            before=opt.m.read(opt.regs,size);memory=opt.m.read(opt.ram,0x200000)
            if case==2:seed=(before,memory,dict(opt.io))
            yes=opt.call(run,entry,encoded);result=opt.m.read(opt.regs,size);after=opt.m.read(opt.ram,0x200000)
            if not yes:
                assert result==before and after==memory,('decline',kind,case);declined+=1;continue
            spent=opt.word(opt.regs+cycle_off)-1000;target=opt.word(opt.regs+pc_off);assert 0<spent<delta
            steps=0
            while jit.word(jit.regs+cycle_off)<1000+spent:
                jit.call(jit.execute,target);steps+=1;assert steps<4096,(kind,case,'converge')
            reference=jit.m.read(jit.regs,size)
            for off,length in ((gpr_off,136),(pc_off,4),(cycle_off,4),(abi[9],384)):
                assert result[off:off+length]==reference[off:off+length],(kind,case,mult,off,result[off:off+length].hex(),reference[off:off+length].hex(),jit.trace[-6:])
            assert after==jit.m.read(jit.ram,0x200000),('RAM',kind,case)
            assert opt.writes==jit.writes and opt.io==jit.io,('MMIO',kind,case,opt.writes,jit.writes)
            if opt.writes:write_cases+=1
            if full_mmio_hooks and kind and entry==head:assert opt.writes,('missing DMA submit coverage',kind,case)
            assert not jit.due;handled+=1
            if case%13==0:
                opt.m.write(opt.regs,before);opt.m.write(opt.ram,memory);opt.io=dict(jit.io);opt.writes=[]
                # Queue and busy-loop stubs avoid replaying an already-used DMA status.
                if not kind or case>=40:
                    opt.call(opt.execute,target);assert opt.m.read(opt.regs,size)[gpr_off:gpr_off+136]==result[gpr_off:gpr_off+136];stubs+=1
        for bad in range(8):
            state,mem,io=seed;opt.m.write(opt.regs,state);opt.m.write(opt.ram,mem);opt.io=dict(io);opt.writes=[]
            def reg(n,v):opt.m.word(opt.regs+gpr_off+n*4,v)
            if not kind:
                if bad==0:reg(4,0x1f801000)
                if bad==1:reg(5,0x1f801000)
                if bad==2:reg(4,0x80050001)
                if bad==3:reg(5,0x80050002)
                if bad==4:reg(4,head)
                if bad==5:reg(5,head)
                if bad==6:opt.put(table_addr,struct.pack('<I',0x1f801000))
                if bad==7:opt.put(table_addr,struct.pack('<I',0x807fffc0))
            else:
                if bad==0:reg(4,0x1f801000)
                if bad==1:reg(4,buffer+2)
                if bad==2:reg(4,0x801ffffc)
                if bad==3:reg(5,0xffffffff)
                if bad==4:reg(29,0x1f800100)
                if bad==5:reg(29,head+64)
                if bad==6:reg(4,0x801fefc0)
                if bad==7:opt.put(pair(sync,1),struct.pack('<I',0x1f801000))
            before=opt.m.read(opt.regs,size);memory=opt.m.read(opt.ram,0x200000)
            assert opt.call(run,head,token)==0,('invalid argument accepted',kind,bad)
            assert opt.m.read(opt.regs,size)==before and opt.m.read(opt.ram,0x200000)==memory and not opt.writes,('invalid mutation',kind,bad)
            negative+=1
        for at,w in ((head,words),(helper,sync)):
            for i,v in enumerate(w):
                opt.put(at+i*4,struct.pack('<I',v^1));opt.m.word(opt.regs+pc_off,head)
                before=opt.m.read(opt.regs,size);memory=opt.m.read(opt.ram,0x200000)
                assert opt.call(run,head,token)==1
                assert opt.m.read(opt.regs,size)==before and opt.m.read(opt.ram,0x200000)==memory
                opt.put(at+i*4,struct.pack('<I',v));mutations+=1
        reports.append({'stage':('ready stream queue','MDEC input DMA','MDEC output DMA')[kind],'cases':64})
    report={'ok':True,'sha256':opt.m.metadata['sha256'],'reference_sha256':jit.m.metadata['sha256'],
        'private_snapshot_sha256':hashlib.sha256(raw).hexdigest(),'cases':192+negative,'handled':handled,'declined':declined,'invalid_argument_cases':negative,
        'actual_JIT_stubs':stubs,'instruction_mutations_rejected':mutations,'stages':reports,
        'complete_MMIO_hooks':full_mmio_hooks,'observed_MMIO_write_cases':write_cases,
        'checks':['all GPR/HI/LO, CP0/GTE, PC, exact JIT cycles and entire RAM',
            'ordered real-core MMIO writes with original guest cycle timestamps' if full_mmio_hooks else 'partial MMIO hook observation only: LTO may inline core calls; DMA coverage also requires non-LTO tests and physical playback',
            'relocated SDK code/globals','ready/reset/empty queue and ordered writes','DMA idle submit and event-bounded busy polling',
            'fractional cycle multipliers, strict event boundary, no-mutation decline','code mutations reject immutable tokens']}
    (args.bda.parent/'movie-io-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
