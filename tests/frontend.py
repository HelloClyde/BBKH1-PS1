"""Normal build: native PCM pause/resume, Chinese selector path and key chords."""
from pathlib import Path
import argparse,json,struct
from unicorn.mips_const import *
from smoke import PS1Machine,ROOT

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path)
    ap.add_argument('--input-bda',type=Path,required=True,help='Non-LTO build with callable pad_read')
    args=ap.parse_args();bda=args.bda;guest=(ROOT/'build/test-rom/H1TEST.exe').read_bytes()
    class Frontend(PS1Machine):
        def __init__(self,*args,**kwargs):
            self.pause_sent=self.resume_sent=self.pause_boundary=False;super().__init__(*args,**kwargs)
            self.stop_after=120
        def event(self,code,key,*args):
            frame=struct.unpack('<I',self.read(self.symbols['h1_ps1_stats']+16,4))[0]
            if frame>=30 and not self.pause_sent:
                self.events.extend(((9,31),(10,31)));self.pause_sent=True
            if self.pause_sent and not self.audio_active and not self.resume_sent:
                if not self.pause_boundary:
                    self.pause_boundary=True
                    self.write(code,struct.pack('<i',-1));self.write(key,struct.pack('<i',-1));return 0
                self.events.extend(((9,31),(10,31)));self.resume_sent=True
            return super().event(code,key,*args)
    m=Frontend(bda,guest,path='A:\\PS1\\测试.exe');m.run()
    assert m.pause_sent and m.resume_sent and len(m.audio_submissions)>=2
    assert m.system_volume==37 and all(v==37 for v in m.volume_changes)
    st=struct.unpack('<33I',m.read(m.symbols['h1_ps1_stats'],132))
    assert st[2:5]==(5,0,120) and st[32]>0,st
    # Call actual frontend pad_read, separately from the PS1 guest's poll timing.
    keys=PS1Machine(args.input_bda,guest)
    pad=next((v for k,v in keys.symbols.items() if k.startswith('_Z8pad_readi')),None)
    if pad is None:raise AssertionError('pad_read must remain callable for contract testing')
    def read(player=0):
        keys.finished=False;keys.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);keys.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        keys.uc.reg_write(UC_MIPS_REG_A0,player);keys.uc.emu_start(pad,0,count=10000)
        assert keys.finished
        return keys.uc.reg_read(UC_MIPS_REG_V0)&65535
    keys.physical_keys={16,17,37,25} # Cross + Square + Up + Start
    expected=0xffff^((1<<14)|(1<<15)|(1<<4)|(1<<3))
    assert read()==expected and read(1)==0xffff
    keys.physical_keys={16};assert read()==(0xffff^(1<<14))
    keys.physical_keys.clear();assert read()==0xffff
    report={'ok':True,'sha256':m.metadata['sha256'],'environment':'compiled MIPS + H1 service models',
            'input_component_sha256':keys.metadata['sha256'],
            'checks':['GBK selector path','PCM pause/resume','paused time excluded','host volume preserved',
                      'simultaneous keys','individual key release','second controller neutral','all resources released']}
    (bda.parent/'frontend.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
