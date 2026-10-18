"""Exact public BDA: pause/resume, cancel, clock restore and PCM cleanup."""
import argparse,json,struct
from smoke import PS1Machine,ROOT

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=__import__('pathlib').Path);args=ap.parse_args()
    guest=(ROOT/'build/test-rom/H1TEST.exe').read_bytes();reports=[]
    class Runtime(PS1Machine):
        def __init__(self,*a,**kw):self.paused=self.resumed=False;super().__init__(*a,**kw);self.stop_after=120
        def event(self,code,key,*a):
            frame=struct.unpack('<I',self.read(self.symbols['h1_ps1_stats']+16,4))[0]
            if frame>=30 and not self.paused:
                self.events.extend(((9,31),(10,31)));self.paused=True
            elif self.paused and not self.audio_active and not self.resumed:
                self.events.extend(((9,31),(10,31)));self.resumed=True
            return super().event(code,key,*a)
    m=Runtime(args.bda,guest,path='A:\\PS1\\测试.exe');m.run()
    assert m.paused and m.resumed and len(m.audio_submissions)>=2
    st=struct.unpack('<52I',m.read(m.symbols['h1_clock_stats'],208))
    assert st[2:4]==(2,0) and 408 in m.clock_model['rates']
    assert m.system_volume==37
    reports.append('GBK selector, pause/resume, PCM quiesce before PLL writes, 408 MHz transition and original clock restore')
    class Cancel(PS1Machine):
        def select_file(self,directory,extension,output,*a):self.write(output,b'\0');return 0
    m=Cancel(args.bda,guest);m.run();assert m.gui_opens==1 and not m.clock_model['writes']
    reports.append('selector cancel restores desktop drawing without clock writes')
    class Refuse(PS1Machine):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw);self.stop_after=6
            self.clock_model['registers'][0x10000000]|=1
    m=Refuse(args.bda,guest);m.run();assert not m.clock_model['writes']
    st=struct.unpack('<52I',m.read(m.symbols['h1_clock_stats'],208));assert st[2]==3
    reports.append('unsupported clock configuration continues at original frequency without MMIO writes')
    report={'ok':True,'sha256':m.metadata['sha256'],'scope':'actual release MIPS + H1 services/register models; no firmware/device execution','checks':reports}
    out=ROOT/'build/verification';out.mkdir(parents=True,exist_ok=True)
    (out/'runtime.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
