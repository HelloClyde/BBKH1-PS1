"""Use Unicorn's actual MIPS MMU; model only identification and cache services."""
import struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from elftools.elf.elffile import ELFFile

def install(machine,bda):
    m=machine;sy=m.symbols;original_read=m.read;original_write=m.write;identification={};m.fastmap_cache_flushes=[]
    with bda.with_suffix('.elf').open('rb') as f:
        elf=ELFFile(f);symbol=elf.get_section_by_name('.symtab').get_symbol_by_name('h1_fastmap_open')[0]
        for off in range(0,symbol['st_size'],4):
            address=symbol['st_value']+off;w=struct.unpack('<I',original_read(address,4))[0]
            if w>>26==16 and (w>>21)&31==0 and (w>>11)&31 in (15,16):
                identification[address]=w;original_write(address,bytes(4))
    assert len(identification)>=3
    def physical(addr):
        if 0x20000000<=addr<0x20800000 or 0x20c00000<=addr<0x20c80000:
            stats=struct.unpack('<13I',original_read(sy['h1_fastmap_stats'],52))
            assert stats[2]==1,(hex(addr),'virtual table no longer mapped')
            if addr<0x20800000:return stats[8]+((addr-0x20000000)&0x1fffff)
            return stats[9]+addr-0x20c00000
        return addr
    m.read=lambda addr,n:original_read(physical(addr),n)
    m.write=lambda addr,data:original_write(physical(addr),data)
    def hook(uc,address,size,user):
        if address in identification:
            w=identification[address];rd=(w>>11)&31
            value=0x0ad0024f if rd==15 else 0x3e63318a if w&7 else 0x80000483
            uc.reg_write(UC_MIPS_REG_0+((w>>16)&31),value)
        if address==sy['cacheflush']:
            p,n,flags=(uc.reg_read(r) for r in (UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2))
            if flags==3 and n in (0x200000,0x80000):
                m.fastmap_cache_flushes.append((p,n));uc.reg_write(UC_MIPS_REG_V0,0);uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
    m.fastmap_identification_hook=[m.uc.hook_add(UC_HOOK_CODE,hook,begin=address,end=address)
        for address in (*identification,sy['cacheflush'])]
    return {'hardware_identification_modeled':True,'page_masks_and_TLBWI_execute_in_CPU':True}
