"""Actual MIPS config I/O: alternating slots, CRC, per-game paths and short writes."""
import argparse,json,struct,zlib
from pathlib import Path
from smoke import PS1Machine,ROOT
from pause_menu import call,state

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);a=ap.parse_args()
    m=PS1Machine(a.bda,b'');scratch=0x83000000
    def load(name):m.write(scratch,name.encode('gbk')+b'\0');call(m,'h1_settings_load',scratch)
    def change(volume):m.write(m.symbols['h1_settings']+45,bytes([volume,1]));call(m,'h1_settings_changed')
    def save():return call(m,'h1_settings_save')
    def slots():return sorted(p for p in m.files if '\\cfg-' in p)
    load('B:\\PS1\\测试.exe');initial=state(m);change(55);assert save()==0
    first=slots()[0];old=m.files[first];assert zlib.crc32(old[:-4])==struct.unpack('<I',old[-4:])[0]
    change(80);assert save()==0;assert len(slots())==2
    second=next(p for p in slots() if p!=first);new=m.files[second]
    load('b:/ps1/测试.EXE');assert state(m)[45]==80
    damaged=bytearray(new);damaged[60]^=1;m.files[second]=bytes(damaged)
    load('B:\\PS1\\测试.exe');assert state(m)[45]==55 and call(m,'h1_settings_writable')==1
    # A partial write to the inactive slot must not destroy the last good slot.
    original=m.fwrite
    def short(ptr,size,count,handle,*args):
        if '\\cfg-' in m.handles[handle][0]:return m.handles[handle][2].write(m.read(ptr,size*count//2))
        return original(ptr,size,count,handle,*args)
    # Service dispatch stores the original bound callable; replace just this fixture.
    stubs=[p for p,fn in m.callbacks.items() if fn==m.fwrite];assert len(stubs)==1
    m.callbacks[stubs[0]]=short;change(90);assert save()==0xffffffff
    assert m.files[first]==old
    load('B:\\PS1\\测试.exe');assert state(m)[45]==55
    m.callbacks[stubs[0]]=original
    change(65);assert save()==0;load('B:\\PS1\\测试.exe');assert state(m)[45]==65
    # Corrupt both slots: use defaults, preserve both files and refuse writes.
    before={p:b'broken-config' for p in slots()};m.files.update(before)
    load('B:\\PS1\\测试.exe');assert state(m)==initial and call(m,'h1_settings_writable')==0
    change(40);assert save()==0xffffffff and all(m.files[p]==data for p,data in before.items())
    load('B:\\PS1\\other.exe');assert state(m)==initial and call(m,'h1_settings_writable')==1
    # Valid CRC but foreign path (hash collision) must never be overwritten.
    own_slots=slots();load('B:\\PS1\\测试.exe')
    foreign=bytearray(old);foreign[68:68+240]=b'other'.ljust(240,b'\0');foreign[-4:]=struct.pack('<I',zlib.crc32(foreign[:-4]))
    m.files[first]=bytes(foreign);m.files.pop(second,None)
    load('B:\\PS1\\测试.exe');assert call(m,'h1_settings_writable')==0
    change(35);assert save()==0xffffffff and m.files[first]==bytes(foreign)
    assert not m.handles and not m.allocations
    report={'ok':True,'sha256':m.metadata['sha256'],'checks':['two alternating full-size CRC records','ASCII case/slash canonicalization with GBK path',
        'corrupt newest slot falls back to last valid config','short write preserves previous valid slot','both corrupt slots stay unchanged',
        'per-game isolation','foreign-path CRC-valid record protected','all file handles and buffers released']}
    out=ROOT/'build/verification';out.mkdir(exist_ok=True);(out/'settings.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
