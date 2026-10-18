"""Resolve audio.c statics after LTO has renamed duplicate local symbols."""
from pathlib import Path
import hashlib,struct,sys

NAMES=('active','queued','batches','submitted','nonzero','dropped','failures','underruns')

def resolve(bda,meta):
    symbols=meta['symbols']
    candidates={name:{value for key,value in symbols.items()
                      if key==name or key.startswith(name+'.lto_priv.')} for name in NAMES}
    result={name:next(iter(values)) for name,values in candidates.items() if len(values)==1}
    proof={'method':'unique nm symbol','missing':list(set(NAMES)-result.keys())}
    if not proof['missing'] and not meta['options'].get('fast_map'):return result,proof
    # DWARF keeps each local variable's original compilation unit. Do not
    # guess which active.lto_priv.N belongs to audio versus the MMU backend.
    from elftools.elf.elffile import ELFFile
    sdk=Path(__file__).resolve().parents[1]/'sdk'
    sys.path.insert(0,str(sdk))
    from h1_bda.resources import PAYLOAD_OFFSET
    data=bda.read_bytes()
    assert hashlib.sha256(data).hexdigest()==meta['sha256']
    elf_path=bda.with_suffix('.elf')
    with elf_path.open('rb') as stream:
        elf=ELFFile(stream)
        for section in elf.iter_sections():
            if section['sh_flags']&2 and section['sh_type']!='SHT_NOBITS':
                offset=PAYLOAD_OFFSET+section['sh_addr']-0x83c00020
                assert offset>=PAYLOAD_OFFSET and data[offset:offset+section['sh_size']]==section.data(),'ELF differs from BDA'
        # Non-LTO local symbols can have identical names even in nm output;
        # build metadata's name-keyed dictionary cannot represent both.
        table=elf.get_section_by_name('.symtab')
        candidates={name:{item['st_value'] for item in table.iter_symbols()
                          if item.name==name or item.name.startswith(name+'.lto_priv.')} for name in NAMES}
        result={}
        dwarf=elf.get_dwarf_info()
        for cu in dwarf.iter_CUs():
            for die in cu.iter_DIEs():
                if die.tag!='DW_TAG_variable':continue
                original=die
                while 'DW_AT_abstract_origin' in original.attributes:
                    original=original.get_DIE_from_attribute('DW_AT_abstract_origin')
                attrs=original.attributes
                if 'DW_AT_name' not in attrs:continue
                name=attrs['DW_AT_name'].value.decode()
                if name not in NAMES:continue
                unit=original.cu.get_top_DIE().attributes['DW_AT_name'].value.decode().replace('\\','/')
                if not unit.endswith('/src/audio.c'):continue
                location=die.attributes.get('DW_AT_location')
                if location is None or len(location.value)!=5 or location.value[0]!=3:continue
                address=struct.unpack('<I',bytes(location.value[1:]))[0]
                assert address in candidates[name],(name,hex(address),candidates[name])
                assert name not in result or result[name]==address
                result[name]=address
    proof={'method':'source-scoped DWARF; allocated ELF sections match BDA',
           'elf_sha256':hashlib.sha256(elf_path.read_bytes()).hexdigest(),
           'missing':sorted(set(NAMES)-result.keys())}
    assert not proof['missing'],proof
    return result,proof
