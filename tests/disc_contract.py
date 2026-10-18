"""Exercise the compiled H1 disc reader with original in-memory sectors."""
from pathlib import Path
import json,struct,sys
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine,ROOT

def main():
    bda=Path(sys.argv[1]);m=PS1Machine(bda,b'')
    sy=m.symbols
    def symbol(name):
        return sy[next(k for k in sy if k.startswith(f'_Z{len(name)}{name}'))]
    def call(address,*args):
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for r,v in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),args):m.uc.reg_write(r,v)
        m.uc.emu_start(address,0,count=2_000_000)
        assert m.finished,hex(m.uc.reg_read(UC_MIPS_REG_PC))
        return m.uc.reg_read(UC_MIPS_REG_V0)
    scratch=0x83000000
    def open_disc(path):
        m.write(scratch,path.encode('gbk')+b'\0');call(symbol('SetIsoFile'),scratch)
        return call(symbol('CDR_open'))
    def read(lba):
        minute,rem=divmod(lba,4500);second,frame=divmod(rem,75)
        bcd=lambda v:(v//10)*16+v%10
        m.write(scratch+512,bytes(map(bcd,(minute,second,frame))))
        rc=call(symbol('CDR_readTrack'),scratch+512)
        getter=struct.unpack('<I',m.read(sy['CDR_getBuffer'],4))[0]
        return rc,m.read(call(getter),2340)
    def raw(value,mode=2):
        sector=bytearray([value]*2352);sector[15]=mode
        return bytes(sector)
    m.files['A:\\PS1\\raw.bin']=b''.join(raw(i) for i in range(40))
    assert open_disc('A:\\PS1\\raw.bin')==0
    for i in (0,1,31,32,39,0):
        rc,sector=read(150+i);assert rc==0 and sector[12:2060]==bytes([i])*2048
    assert read(190)[0]==0xffffffff
    # Crossing a cache window and seeking backwards must preserve data.
    assert struct.unpack('<I',m.read(sy['h1_ps1_stats']+48,4))[0]>=3
    m.files['A:\\PS1\\data.iso']=b''.join(bytes([i+90])*2048 for i in range(3))
    assert open_disc('A:\\PS1\\data.iso')==0
    for i in range(3):
        rc,sector=read(150+i);assert rc==0 and sector[3]==2 and sector[12:2060]==bytes([i+90])*2048
    m.files['A:\\PS1\\mode1.bin']=raw(71,1)
    assert open_disc('A:\\PS1\\mode1.bin')==0
    rc,sector=read(150);assert rc==0 and sector[3]==2 and sector[4:12]==bytes(8) and sector[12:2060]==bytes([71])*2048
    # A separate-file audio pregap belongs to its audio file. TOC still reports
    # INDEX 01, while reads on INDEX 00 must not run past the previous data file.
    m.files['A:\\PS1\\数据.bin']=raw(11)+raw(12)
    m.files['A:\\PS1\\music.bin']=raw(21)+raw(22)+raw(23)+raw(24)
    cue='FILE "数据.bin" BINARY\n TRACK 01 MODE2/2352\n INDEX 01 00:00:00\nFILE "music.bin" BINARY\n TRACK 02 AUDIO\n INDEX 00 00:00:00\n INDEX 01 00:00:01\n'
    m.files['A:\\PS1\\disc.cue']=cue.encode('gbk')
    assert open_disc('A:\\PS1\\disc.cue')==0
    for lba,value in ((151,12),(152,21),(153,22),(155,24)):
        rc,sector=read(lba);assert rc==0 and sector[12]==value,(lba,rc,sector[:16])
    assert call(symbol('CDR_getTD'),2,scratch+1024)==0
    assert m.read(scratch+1024,3)==bytes((3,2,0))
    # Queue-full CDDA must retry the same sector, including across cycle rebase.
    abi=struct.unpack('<10I',m.read(sy['h1_ps1_abi'],40));cycle=sy['psxRegs']+abi[3]
    received=[];accept=[False]
    def cdda(uc,address,size,data):
        received.append(m.read(uc.reg_read(UC_MIPS_REG_A0),2352))
        uc.reg_write(UC_MIPS_REG_V0,0x676f if accept[0] else 0x7761)
        uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
    m.uc.hook_add(UC_HOOK_CODE,cdda,begin=sy['SPUplayCDDAchannel'],end=sy['SPUplayCDDAchannel'])
    m.word(cycle,10000);m.write(scratch+512,bytes((0,2,3)))
    call(symbol('CDR_play'),scratch+512)
    m.word(cycle,10000+33868800//75)
    call(sy['h1_ps1_disc_pump']);assert received==[raw(22)]
    call(sy['h1_ps1_disc_adjust'],10000);m.word(cycle,33868800//75)
    accept[0]=True;call(sy['h1_ps1_disc_pump']);assert received==[raw(22),raw(22)]
    m.word(cycle,2*(33868800//75));call(sy['h1_ps1_disc_pump']);assert received[-1]==raw(23)
    # Shared-file INDEX mapping, incomplete and unsupported CUE rejection.
    m.files['A:\\PS1\\shared.bin']=raw(31)+raw(32)+raw(33)+raw(34)
    m.files['A:\\PS1\\shared.cue']=b'FILE "shared.bin" BINARY\nTRACK 01 MODE2/2352\nINDEX 01 00:00:00\nTRACK 02 AUDIO\nINDEX 00 00:00:02\nINDEX 01 00:00:03\n'
    assert open_disc('A:\\PS1\\shared.cue')==0
    assert read(152)[1][12]==33 and read(153)[1][12]==34
    for invalid in ('FILE "shared.bin" BINARY\nTRACK 01 MODE2/2352\n',cue+'PREGAP 00:02:00\n',cue.replace('MODE2/2352','MODE2/2336')):
        m.files['A:\\PS1\\bad.cue']=invalid.encode('gbk');assert open_disc('A:\\PS1\\bad.cue')==0xffffffff
    call(symbol('CDR_close'));assert not m.handles and not m.allocations
    report={'ok':True,'sha256':m.metadata['sha256'],'environment':'compiled MIPS + H1 service models',
            'checks':['BIN cache boundaries/backward seek','ISO 2048','MODE1 normalization','multi-file CUE','GBK paths','INDEX 00 pregap/INDEX 01 TOC','shared-file CUE','CDDA backpressure/rebase','malformed CUE rejection','no leaks']}
    (bda.parent/'disc-contract.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
