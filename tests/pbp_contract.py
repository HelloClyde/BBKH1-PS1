"""Run the compiled PBP parser, inflater, TOC, CDDA and disc switch contracts."""
from pathlib import Path
import json,struct,sys
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine
from pbp_fixture import pbp,disc_image,sector,BLOCK


def main():
    bda=Path(sys.argv[1]);m=PS1Machine(bda,b'');sy=m.symbols
    def symbol(name):
        if name in sy:return sy[name]
        return sy[next(k for k in sy if k.startswith(f'_Z{len(name)}{name}'))]
    def call(name,*args):
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for reg,value in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),args):m.uc.reg_write(reg,value)
        m.uc.emu_start(symbol(name),0,count=12_000_000)
        assert m.finished,(name,hex(m.uc.reg_read(UC_MIPS_REG_PC)))
        return m.uc.reg_read(UC_MIPS_REG_V0)
    scratch=0x83000000
    path='A:\\PS1\\最终幻想\\EBOOT.PbP'
    def open_image(data):
        m.files[path]=data;m.write(scratch,path.encode('gbk')+b'\0');call('SetIsoFile',scratch)
        return call('CDR_open')
    def read(lba):
        from pbp_fixture import msf
        m.write(scratch+512,msf(lba));rc=call('CDR_readTrack',scratch+512)
        getter=struct.unpack('<I',m.read(sy['CDR_getBuffer'],4))[0]
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        m.uc.emu_start(getter,0,count=1000);assert m.finished
        return rc,m.read(m.uc.reg_read(UC_MIPS_REG_V0),2340)
    def reads():return struct.unpack('<I',m.read(sy['h1_ps1_stats']+44,4))[0]
    def close():
        call('CDR_close');assert not m.handles and not m.allocations
    first=disc_image([sector(i) for i in range(43)],audio_at=(180,182),stored=(1,))
    second=disc_image([sector(i+80) for i in range(25)],data_offset=0x110000)
    assert open_image(pbp([first]))==0
    assert call('h1_ps1_disc_count')==1 and call('h1_ps1_disc_selected')==0
    before=reads()
    for i in (0,15,16,17,31,32,42):
        rc,data=read(150+i);assert rc==0 and data[12:2060]==bytes([i])*2048,(i,rc)
    assert reads()-before==3
    assert read(193)[0]==0xffffffff
    assert read(150)[1][12]==0
    assert call('CDR_getTN',scratch+1024)==0 and m.read(scratch+1024,2)==b'\1\2'
    assert call('CDR_getTD',2,scratch+1024)==0 and m.read(scratch+1024,3)==bytes((32,2,0))
    assert call('CDR_getTD',0,scratch+1024)==0 and m.read(scratch+1024,3)==bytes((43,2,0))
    # Data streaming and CDDA keep independent decompressed blocks.
    abi=struct.unpack('<10I',m.read(sy['h1_ps1_abi'],40));cycle=sy['psxRegs']+abi[3]
    received=[];accept=[False]
    def cdda(uc,address,size,user):
        received.append(m.read(uc.reg_read(UC_MIPS_REG_A0),2352))
        uc.reg_write(UC_MIPS_REG_V0,0x676f if accept[0] else 0x7761);uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
    m.uc.hook_add(UC_HOOK_CODE,cdda,begin=sy['SPUplayCDDAchannel'],end=sy['SPUplayCDDAchannel'])
    m.word(cycle,10000);m.write(scratch+512,bytes((0,2,32)));call('CDR_play',scratch+512)
    m.word(cycle,10000+33868800//75);call('h1_ps1_disc_pump');assert received==[sector(32)]
    read(150);before=reads();call('h1_ps1_disc_pump');assert received[-1]==sector(32) and reads()==before
    accept[0]=True;call('h1_ps1_disc_adjust',10000);m.word(cycle,33868800//75);call('h1_ps1_disc_pump')
    assert received[-1]==sector(32);close()
    multi=pbp([first,second])
    assert open_image(multi)==0 and call('h1_ps1_disc_count')==2
    assert read(150)[1][12]==0
    assert call('h1_ps1_disc_switch',1)==0 and call('h1_ps1_disc_selected')==1
    assert read(150)[1][12]==80 and read(174)[1][12]==104
    assert call('h1_ps1_disc_switch',2)==0xffffffff and read(150)[1][12]==80
    assert call('h1_ps1_disc_switch',0)==0 and read(150)[1][12]==0
    call('CDR_getStatus',scratch+1024);assert m.read(scratch+1028,4)==bytes(4)
    call('h1_ps1_disc_resume');call('CDR_getStatus',scratch+1024)
    assert struct.unpack('<I',m.read(scratch+1028,4))[0]&0x10
    close()
    # Invalid target disc must leave the old file, TOC, index and cache usable.
    bad_multi=bytearray(multi);disc2=struct.unpack_from('<I',bad_multi,0x40+0x204)[0]+0x40
    bad_multi[disc2:disc2+12]=b'BAD IMAGE!!!'
    assert open_image(bytes(bad_multi))==0
    assert call('h1_ps1_disc_switch',1)==0xffffffff
    assert call('h1_ps1_disc_selected')==0 and read(150)[1][12]==0;close()
    assert open_image(pbp([first]*8))==0 and call('h1_ps1_disc_count')==8
    assert call('h1_ps1_disc_switch',7)==0 and read(150)[1][12]==0
    assert call('h1_ps1_disc_switch',8)==0xffffffff;close()
    mutations=[('header',0,b'BAD!'),('PSAR overflow',36,b'\xff'*4),('not PS1',0x40,b'NPUMDIMG0000'),
        ('encrypted',0x440,b'\0PGD'),('BCD',0x40+0x800+17,b'\xfa'),('zero tracks',0x40+0x800+17,b'\0'),
        ('empty block',0x40+0x4004,b'\0\0'),('oversized block',0x40+0x4004,b'\xff\xff'),
        ('block offset',0x40+0x4000,b'\xff'*4),('data offset',0x40+0xbfc,b'\xff'*4)]
    for name,offset,value in mutations:
        image=bytearray(pbp([first]));image[offset:offset+len(value)]=value
        assert open_image(bytes(image))==0xffffffff,name
        assert not m.handles and not m.allocations,name
    for data in (b'',pbp([first])[:30],pbp([first])[:-30]):
        assert open_image(data)==0xffffffff;assert not m.handles and not m.allocations
    corrupt=bytearray(pbp([first]));corrupt[0x40+0x100000:0x40+0x100000+16]=bytes(16)
    assert open_image(bytes(corrupt))==0
    assert read(150)[0]==0xffffffff and read(166)[0]==0
    assert read(150)[0]==0xffffffff # failed inflate must not mark a valid cache block
    close()
    report={'ok':True,'sha256':m.metadata['sha256'],'environment':'actual compiled MIPS + H1 file models; no device benchmark',
        'checks':['raw Deflate and stored blocks','flags, padding and custom data offset','16-sector cache boundaries and backward seeks',
            'two data/CDDA caches and full-queue retries','TOC and audio pregaps','GBK path and mixed-case PBP suffix',
            'multi-disc switch and deferred lid notification','failed switch preserves previous disc','malformed/truncated/encrypted PBP rejection',
            'corrupt compressed data cannot poison cache','all handles and allocations released']}
    (bda.parent/'pbp-contract.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
