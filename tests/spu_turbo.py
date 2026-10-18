"""Lossy output is expected; decoder, envelopes, IRQ/readback state must match."""
from pathlib import Path
import argparse,hashlib,json,random,struct
from elftools.elf.elffile import ELFFile
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from spu_audio import SPU
from smoke import PS1Machine


def call(m,name,args):
    m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
    for r,v in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),args):m.uc.reg_write(r,v)
    for n,v in enumerate(args[4:]):m.word(0x83aff010+n*4,v)
    m.uc.emu_start(m.symbols[name],0,count=4_000_000)
    assert m.finished and m.uc.reg_read(UC_MIPS_REG_SP)==0x83aff000,name
    return m.uc.reg_read(UC_MIPS_REG_V0)


def type_layout(bda,name):
    with bda.with_suffix('.elf').open('rb') as f:
        dwarf=ELFFile(f).get_dwarf_info()
        for cu in dwarf.iter_CUs():
            for die in cu.iter_DIEs():
                a=die.attributes.get('DW_AT_name')
                if a and a.value==name.encode() and die.tag=='DW_TAG_typedef':
                    die=die.get_DIE_from_attribute('DW_AT_type');break
            else:continue
            break
        else:raise AssertionError(name)
        def fields(die,bias=0):
            result={}
            for member in die.iter_children():
                if member.tag!='DW_TAG_member':continue
                loc=member.attributes.get('DW_AT_data_member_location')
                offset=bias+(loc.value if loc else 0)
                a=member.attributes.get('DW_AT_name')
                if a:result[a.value.decode()]=offset
                else:result.update(fields(member.get_DIE_from_attribute('DW_AT_type'),offset))
            return result
        return die.attributes['DW_AT_byte_size'].value,fields(die)


def semantic_state(s,layout,channel_layout):
    _,members=layout;ch_size,ch_members=channel_layout;m=s.m;spu=m.symbols['spu']
    def word(name):return struct.unpack('<I',m.read(spu+members[name],4))[0]
    scalars={name:word(name) for name in ['cycles_played','decode_pos','decode_dirty_ch',
        'dwNoiseVal','dwNoiseCount','dwNewChannel','dwChannelOn','dwChannelDead','spuAddr']}
    scalars['control_status']=m.read(spu,4).hex()
    channels=[];base=word('spuMemC')
    for n in range(24):
        raw=bytearray(m.read(word('s_chan')+n*ch_size,ch_size))
        for name in ['pCurr','pLoop']:
            off=ch_members[name];p=struct.unpack_from('<I',raw,off)[0]
            struct.pack_into('<I',raw,off,(p-base)&0xffffffff)
        channels.append(bytes(raw))
    return scalars,channels,m.read(word('SB'),24*36*4),m.read(base,0x80000)


def helpers(bda):
    # The exact fast stepper in this same binary is separately checked by
    # spu_samples.py against the original independently compiled upstream macro.
    m=PS1Machine(bda,b'');rng=random.Random(0x54555242)
    # A native callback updates history and can deliberately mutate phase/index.
    folder=bda.parent/'spu-reference';elf_path=folder/'reference.elf';symbols={}
    with elf_path.open('rb') as f:
        elf=ELFFile(f)
        for seg in elf.iter_segments():
            if seg['p_type']=='PT_LOAD':m.write(seg['p_vaddr'],seg.data()+bytes(seg['p_memsz']-seg['p_filesz']))
        for sym in elf.get_section_by_name('.symtab').iter_symbols():symbols[sym.name]=sym['st_value']
    hist,out,pos,idx=0x83000020,0x83010020,0x83020000,0x83020004
    def run(name,count,step,phase,offset,data,mutate):
        m.write(hist-32,data);m.write(out-32,b'\xa5'*(1024*4+64));m.word(pos,phase);m.word(idx,offset)
        for key,value in [('position_ptr',pos),('index_ptr',idx),('calls',0),('seed',0x12345678),('mutate',mutate)]:m.word(symbols[key],value)
        m.write(symbols['trace'],bytes(512*16))
        args=[symbols['callback'],0x1000234,3,count,hist,step,pos,idx]
        if name!='h1_spu_samples_quiet':args.append(out)
        result=call(m,name,args)
        return (result,m.read(hist-32,len(data)),m.read(pos,8),m.read(symbols['calls'],4),
            m.read(symbols['seed'],4),m.read(symbols['trace'],512*16)),m.read(out-32,1024*4+64)
    for case in range(512):
        count=([0,1,2,27,28,29,92,184,441,1024][case%10] if case<80 else rng.randrange(1025))
        step=rng.choice([0,1,0x8000,0x10000,0x3fff0,rng.randrange(0x40000)])
        phase=rng.randrange(65536)+(0x40000 if case%7==0 else 0);offset=rng.randrange(28)
        data=b'\x5a'*32+rng.randbytes(36*4)+b'\xa5'*32
        args=count,step,phase,offset,data,case%2
        state,full=run('h1_spu_samples_noint',*args)
        half_state,half=run('h1_spu_samples_half',*args)
        quiet_state,quiet=run('h1_spu_samples_quiet',*args)
        assert state==half_state==quiet_state,('helper state',case)
        expected=bytearray(b'\xa5'*len(half))
        for n in range(0,count,2):expected[32+n*4:36+n*4]=full[32+n*4:36+n*4]
        assert half==expected and quiet==b'\xa5'*len(quiet),('render mask',case)
    # Independent mono mixing and saturation arithmetic, including odd tails.
    cases=0
    for count in [0,1,2,3,92,184,898]:
        samples=[rng.randrange(-32768,32768) for _ in range(count)]
        left,right=rng.randrange(-16384,16384),rng.randrange(-16384,16384)
        sums=[rng.randrange(-100000,100000) for _ in range(count*2)]
        m.write(hist,struct.pack(f'<{count}i',*samples));m.write(out,b'\xa5'*32+struct.pack(f'<{count*2}i',*sums)+b'\xa5'*32)
        call(m,'h1_spu_mix_half_mono',[out+32,count,left,right,hist])
        expected=sums[:];gain=int((left+right)/2)
        for n in range(0,count,2):
            v=samples[n]*gain>>14
            for k in range(n*2,min((n+2)*2,count*2)):expected[k]+=v
        assert m.read(out,32)==b'\xa5'*32 and m.read(out+32+count*8,32)==b'\xa5'*32
        assert m.read(out+32,count*8)==struct.pack(f'<{count*2}i',*expected)
        pcm=0x83030020;m.write(pcm-32,b'\x5a'*(count*4+64))
        call(m,'h1_spu_finish_mono',[out+32,count,1024,1,pcm])
        expected_pcm=[]
        for n in range(count):
            v=max(-32768,min(32767,int((expected[n*2]+expected[n*2+1])/2)))
            expected_pcm.extend([v,v])
        assert m.read(pcm,count*4)==struct.pack(f'<{count*2}h',*expected_pcm)
        assert m.read(pcm-32,32)==b'\x5a'*32 and m.read(pcm+count*4,32)==b'\x5a'*32
        assert m.read(out+32,count*8)==bytes(count*8)
        cases+=1
    return {'step_cases':512,'mix_finish_cases':cases}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('reference',type=Path);ap.add_argument('bda',type=Path)
    args=ap.parse_args();rng=random.Random(0x50434d);rows=[]
    helper_report=helpers(args.bda)
    layouts=[type_layout(p,'SPUInfo') for p in [args.reference,args.bda]]
    channel_layouts=[type_layout(p,'SPUCHAN') for p in [args.reference,args.bda]]
    for case,voices in enumerate([1,2,4,7,11,14,24,11]):
        machines=[SPU(args.reference),SPU(args.bda),SPU(args.bda)]
        machines[1].call('h1_spu_turbo_set',0)
        irq_traces=[[],[],[]]
        for index,s in enumerate(machines):
            members=layouts[index>0][1];ch_size,ch_members=channel_layouts[index>0]
            spu=s.m.symbols['spu'];s.m.word(spu+members['irqCallback'],0x83140000)
            def irq(uc,address,size,data,s=s,members=members,ch_size=ch_size,ch_members=ch_members,index=index):
                m=s.m;spu=m.symbols['spu']
                word=lambda name:struct.unpack('<I',m.read(spu+members[name],4))[0]
                base=word('spuMemC');channels=word('s_chan')
                snapshot=[word('cycles_played'),word('decode_pos')]
                for ch in range(24):
                    for name in ['spos','iSBPos','pCurr','pLoop']:
                        value=struct.unpack('<I',m.read(channels+ch*ch_size+ch_members[name],4))[0]
                        snapshot.append((value-base)&0xffffffff if name.startswith('p') else value)
                irq_traces[index].append(snapshot)
                uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
            s.m.uc.hook_add(UC_HOOK_CODE,irq,begin=0x83140000,end=0x83140000)
        wave=bytearray()
        for block in range(32):wave.extend(bytes([(block%5)*16+(block%13),4 if block==0 else 3 if block==31 else 0])+rng.randbytes(14))
        total=0
        for s in machines:
            s.m.write(0x83b00000,bytes(wave));s.reg(0x1f801da6,0x1000)
            s.call('SPUwriteDMAMem',0x83b00000,len(wave)//2,0)
            s.reg(0x1f801daa,0xc040 if case in [4,7] else 0xc000)
            s.reg(0x1f801da4,0x1002) # IRQ target inside the ADPCM stream
            s.reg(0x1f801d80,0x3fff);s.reg(0x1f801d82,0x3fff)
            for ch in range(voices):
                base=0x1f801c00+ch*16
                lv=0 if ch==5 else 64 if ch==4 else 0x3fff-ch*77
                rv=0 if ch==5 else 64 if ch==4 else 0x1000+ch*91
                for off,value in [(0,lv),(2,rv),(4,[0x800,0x1000,0x1800,0x3fff][(case+ch)%4]),
                    (6,0x1000),(8,0x000f),(10,0),(14,0x1000)]:s.reg(base+off,value)
            if case==7:s.reg(0x1f801d90,2)
            if case==6:s.reg(0x1f801d94,1<<8) # noise state must also remain exact
            mask=(1<<voices)-1;s.reg(0x1f801d88,mask&65535);s.reg(0x1f801d8a,mask>>16)
        for block in range(48):
            total+=[37,92,184,128][block%4]*768
            for s in machines:
                if block==24:s.reg(0x1f801c04,0x1500,total)
                if block==28 and voices>5:
                    s.reg(0x1f801c50,0x3fff,total);s.reg(0x1f801c52,0x3fff,total)
                if block==36:s.reg(0x1f801d8c,1,total)
                s.call('SPUasync',total,1)
            states=[semantic_state(s,layouts[i>0],channel_layouts[i>0]) for i,s in enumerate(machines)]
            assert states[0]==states[1]==states[2],('SPU state',case,block)
        original,off,on=[b''.join(s.pcm) for s in machines]
        assert original==off and len(original)==len(on) and any(on)
        assert irq_traces[0]==irq_traces[1]==irq_traces[2],('IRQ callback state',case)
        if case in [4,7]:assert irq_traces[0],('IRQ callback was never reached',case)
        samples=struct.unpack(f'<{len(on)//2}h',on)
        assert all(samples[n]==samples[n+1] for n in range(0,len(samples),2))
        counters=struct.unpack('<8I',machines[2].m.read(machines[2].m.symbols['h1_spu_turbo_stats'],32))
        assert counters[0] and counters[1] and counters[7]
        rows.append({'voices':voices,'stereo_frames':len(on)//4,'reference_sha256':hashlib.sha256(original).hexdigest(),
            'turbo_sha256':hashlib.sha256(on).hexdigest(),'state_checks':48,'irq_callbacks':len(irq_traces[0]),'counters':list(counters)})
        for s in machines:s.finish()
    assert sum(row['counters'][2] for row in rows)>0,'quiet path was never tested'
    report={'ok':True,'sha256':machines[2].m.metadata['sha256'],'reference_sha256':machines[0].m.metadata['sha256'],
        'helpers':helper_report,'pcm':rows,'checks':['off mode PCM bit-identical to previous normal build',
        'ADPCM histories, every voice state, ADSR, masks, IRQ status and full 512 KiB SPU RAM identical after every update',
        'FM, noise, voice 1/3 readback, quiet voices and unmute, keyoff, pitch changes, loop boundaries',
        'actual IRQ callback entries and callback-visible per-voice phase/index/addresses identical',
        'same PCM frame count and nonzero mono output; lossy waveform expected','all allocations and handles released']}
    (args.bda.parent/'spu-turbo-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
