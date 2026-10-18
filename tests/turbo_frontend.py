"""Actual frontend T/H controls switch lossy/full audio without losing PCM."""
from pathlib import Path
import argparse,json,re,struct
from smoke import PS1Machine,ROOT
from spu_turbo import type_layout


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);args=ap.parse_args()
    _,fields=type_layout(args.bda,'SPUConfig')
    header=(ROOT/'sdk/sdk/include/h1_input.h').read_text()
    keycodes={name:int(re.search(r'#define H1_KEY_'+name+r'\s+(\d+)',header)[1]) for name in ['T','H']}
    class Frontend(PS1Machine):
        def __init__(self,*a,**kw):
            self.stage=0;self.observations=[];super().__init__(*a,**kw);self.stop_after=120
        def event(self,code,key,*a):
            frame=struct.unpack('<I',self.read(self.symbols['h1_ps1_stats']+16,4))[0]
            thresholds=[10,20,30,40,50]
            if self.stage<len(thresholds) and frame>=thresholds[self.stage]:
                mode=struct.unpack('<I',self.read(self.symbols['h1_spu_turbo_mode'],4))[0]
                cfg=self.symbols['spu_config']
                reverb=struct.unpack('<I',self.read(cfg+fields['iUseReverb'],4))[0]
                interp=struct.unpack('<I',self.read(cfg+fields['iUseInterpolation'],4))[0]
                self.observations.append([frame,mode,reverb,interp])
                if self.stage<4:
                    k=keycodes[['T','T','H','H'][self.stage]]
                    self.events.extend(((9,k),(10,k)))
                self.stage+=1
            return super().event(code,key,*a)
    m=Frontend(args.bda,(ROOT/'build/test-rom/H1TEST.exe').read_bytes());m.run()
    assert [row[1:] for row in m.observations]==[[1,0,0],[0,0,0],[1,0,0],[1,1,2],[1,0,0]],m.observations
    assert m.audio_submissions and m.system_volume==37
    report={'ok':True,'sha256':m.metadata['sha256'],'observations_frame_mode_reverb_interpolation':m.observations,
        'checks':['T off/on and H quality on/off through actual native input events',
            'PCM remains enabled and volume preserved','normal exit releases all resources']}
    (args.bda.parent/'turbo-frontend.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
