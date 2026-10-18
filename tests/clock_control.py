"""Compiled JZ4740 clock backend: allowed rates, staged clocks and rollback."""
from pathlib import Path
import json,struct,subprocess
from elftools.elf.elffile import ELFFile
from unicorn import *
from unicorn.mips_const import *
ROOT=Path(__file__).resolve().parents[1]
BASE={0x10000000:0x40662220,0x10000010:0x1b000520,0x10000020:0,
      0x10000060:4,0x10000064:36,0x10000068:13,0x1000006c:6,0x10000074:4,
      0x13010080:0x05aa3211,0x13010084:0x83,0x1301008c:30}
BASE.update({0x13050000:0x980,0x13050030:0x20000c0d,0x13050034:0xb0,0x13050040:0x57bbc0,0x13050050:0})


def main():
    folder=ROOT/'build/clock-control-model';folder.mkdir(parents=True,exist_ok=True)
    elf_path=folder/'clock.elf';tc=Path(__import__('os').environ.get('H1_GNU_BIN',ROOT/'.tools/toolchain/bin'))
    cmd=[tc/'mipsel-none-elf-gcc.exe','-EL','-march=mips32','-mabi=32','-msoft-float','-mno-abicalls','-G0',
        '-fno-pic','-O3','-ffreestanding','-fno-builtin','-nostdlib','-g',
        '-Wl,-Ttext,0x83100000','-Wl,-Tdata,0x83110000','-Wl,--section-start,.bss=0x83120000',
        '-Wl,-e,h1_clock_open','-o',elf_path,ROOT/'src/clock_control.c','-lgcc']
    p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);assert p.returncode==0,p.stdout+p.stderr
    cases=['384','408','refused_420','wrong_cpu_divider','pll_usb_source','wrong_sd_clock','invalid_rate','lock_timeout','target_readback_failure','restore_readback_failure']
    reports=[]
    for case in cases:
        u=Uc(UC_ARCH_MIPS,UC_MODE_MIPS32|UC_MODE_LITTLE_ENDIAN);u.mem_map(0,64*1024*1024)
        u.mem_map(0x10000000,4096);u.mem_map(0x13010000,4096);u.mem_map(0x13050000,4096)
        read=lambda a,n:bytes(u.mem_read(a&0x1fffffff,n));write=lambda a,b:u.mem_write(a&0x1fffffff,b)
        regs=dict(BASE);pending=[None];polls=[0];writes=[];finished=[];symbols={};restoring=[False]
        if case=='wrong_cpu_divider':regs[0x10000000]|=1
        if case=='pll_usb_source':regs[0x10000000]|=1<<29
        if case=='wrong_sd_clock':regs[0x10000068]=7
        with elf_path.open('rb') as f:
            elf=ELFFile(f)
            for seg in elf.iter_segments():
                if seg['p_type']=='PT_LOAD':write(seg['p_vaddr'],seg.data()+bytes(seg['p_memsz']-seg['p_filesz']))
            for sym in elf.get_section_by_name('.symtab').iter_symbols():symbols[sym.name]=sym['st_value']
        for a,v in regs.items():write(a,struct.pack('<I',v))
        u.reg_write(UC_MIPS_REG_CP0_STATUS,1)
        def memory_read(uc,access,address,size,value,data):
            a=address&0x1fffffff
            if a==0x10000010 and pending[0] is not None:
                polls[0]+=1
                if polls[0]>=4 and not (case=='lock_timeout' and (pending[0]^BASE[a])&0xffff0000):
                    regs[a]|=0x400;pending[0]=None
            if a in regs:write(a,int(regs[a]).to_bytes(size,'little'))
        def memory_write(uc,access,address,size,value,data):
            a=address&0x1fffffff;writes.append([a,size,value])
            assert a in [0x10000000,0x10000010,0x10000020,0x10000064,0x10000068,0x1000006c,0x13010088,0x1301008c,0x13050030,0x13050034,0x13050040,0x13050050],hex(a)
            assert size==(2 if a in (0x13010088,0x1301008c) else 4)
            if a==0x10000020 and value&0x400:assert not regs[0x13050030]&8,'LCD clock gated while DMA active'
            if a==0x13050030 and value&16:
                regs[0x13050034]|=1;value&=~8
            if a in [0x10000064,0x10000068,0x1000006c]:assert regs[0x10000020]&0x4480==0x4480,'device divider changed without gating'
            if a==0x10000000:assert not ((value^BASE[a])&~(0x1fffff|(1<<22))),'changed external clock source'
            if a==0x10000010:
                assert value&0x300==0x100,'disabled or bypassed PLL'
                mhz=12*((value>>23)+2)/(((value>>18)&31)+2)
                assert 336<=mhz<=420
                c=regs[0x10000000];divs=[1,2,3,4,6,8,12,16,24,32]
                h,m,p=[mhz/divs[c>>shift&15] for shift in [4,12,8]]
                assert max(h,m,p)<=112 and h==m and h/p==int(h/p)
                assert mhz/((c>>16&31)+1)<=48 and mhz/(regs[0x10000064]+1)<=336/37
                assert mhz/(regs[0x10000068]+1)<=24 and mhz/(regs[0x1000006c]+1)<=48
                assert (regs[0x1301008c]+1)/(mhz/divs[c>>12&15]) <=31/112+1e-10
                if (value^regs[a])&0xfffffb00:
                    assert value&255==255,'runtime PLL settling interval was not lengthened'
                    assert regs[0x10000020]&0x60==0x60,'audio clocks were not gated'
                    pending[0]=value;polls[0]=0
                else:value|=regs[a]&0x400
            if a==0x10000064 and ((case=='target_readback_failure' and value!=36) or (case=='restore_readback_failure' and restoring[0] and value==36)):
                return
            regs[a]=value
        def code(uc,a,size,data):
            if a==0x80001ff0:finished.append(True);uc.emu_stop()
        u.hook_add(UC_HOOK_MEM_READ,memory_read,begin=0x10000000,end=0x13050fff)
        u.hook_add(UC_HOOK_MEM_WRITE,memory_write,begin=0x10000000,end=0x13050fff)
        u.hook_add(UC_HOOK_CODE,code,begin=0x80001ff0,end=0x80001ff0)
        def call(name,arg=0):
            finished.clear();u.reg_write(UC_MIPS_REG_SP,0x83aff000);u.reg_write(UC_MIPS_REG_RA,0x80001ff0);u.reg_write(UC_MIPS_REG_A0,arg)
            u.emu_start(symbols[name],0,count=30_000_000);assert finished,name
            assert u.reg_read(UC_MIPS_REG_SP)==0x83aff000 and u.reg_read(UC_MIPS_REG_CP0_STATUS)==1
            return u.reg_read(UC_MIPS_REG_V0)
        rate=int(case) if case.isdecimal() else 400 if case=='invalid_rate' else 420 if case=='refused_420' else 384
        opened=call('h1_clock_open',rate)
        if case in ['384','408','restore_readback_failure']:
            assert opened==1,(case,opened);restoring[0]=True;closed=call('h1_clock_close')
            assert closed==(case!='restore_readback_failure')
        else:assert opened==0,(case,opened)
        values=list(struct.unpack('<52I',read(symbols['h1_clock_stats'],208)))
        if case in ['refused_420','wrong_cpu_divider','pll_usb_source','wrong_sd_clock','invalid_rate']:assert not writes and values[2]==3
        elif case=='restore_readback_failure':assert values[2]==4 and values[3]&8
        else:
            assert values[2]==2,(case,values)
            assert all((regs[a] & (~0x400 if a==0x10000010 else ~0x80 if a==0x13010084 else 0xffffffff))==
                       (v & (~0x400 if a==0x10000010 else ~0x80 if a==0x13010084 else 0xffffffff)) for a,v in BASE.items() if a!=0x13050034),(case,regs)
        reports.append({'case':case,'opened':opened,'state':values[2],'error':values[3],'mmio_writes':len(writes),'pll_polls':values[7]})
    report={'ok':True,'scope':'actual compiled clock backend with documented register behavior model; not physical MHz/stability/FPS',
        'cases':reports,'checks':['no bus/memory/device clock exceeds original throughout modeled transitions',
        'no voltage, USB/I2S/SSI source, SDRAM timings or PLL enable/disable changes','proper 16-bit SDRAM refresh register accesses',
        'external clock sources and CP0 status retained','unsupported config refuses without writes',
        'PLL lock timeout and readback mismatch roll back; failed restore remains an error']}
    (folder/'model.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
