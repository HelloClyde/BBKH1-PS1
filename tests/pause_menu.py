"""Run the actual BDA touch menu: guest freeze, drag ownership, settings and exit."""
import argparse,hashlib,json,struct
from pathlib import Path
from PIL import Image
from unicorn.mips_const import *
from smoke import PS1Machine,ROOT

def tap(x,y):return [(11,x,y),(8,x,y)]
def key(k):return [(9,k),(10,k)]
def words(m):return struct.unpack('<8I',m.read(m.symbols['h1_ps1_menu_stats'],32))
def call(m,name,*args):
    m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
    for r,v in zip([UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3],args):m.uc.reg_write(r,v)
    m.uc.emu_start(m.symbols[name],0,count=2_000_000);assert m.finished,name
    return m.uc.reg_read(UC_MIPS_REG_V0)
def state(m):return m.read(m.symbols['h1_settings'],56)

class Menu(PS1Machine):
    def __init__(self,*a,exit_menu=False,**kw):
        super().__init__(*a,**kw);self.stop_after=90;self.opened=False;self.idle=0;self.frozen=None
        self.actions=([(9,24),(8,330,210),(10,24)]+ # Opening touch and its synthetic Escape are swallowed.
            [(11,330,210),(8,5,5)]+ # Drag off EXIT cancels.
            tap(100,210)+tap(400,250)+ # About and touch Back.
            tap(330,80)+tap(100,114)+key(11)+key(3)+tap(330,250)+ # Cross=E; F is reserved.
            tap(100,145)+[(11,38,234),(0,441,234),(0,300,234),(8,300,130)]+ # held pen moves without GUI events.
            key(35)+key(40)+tap(100,70)+tap(100,70)+tap(100,145)+tap(100,108)+tap(100,180)+
            tap(330,145)+tap(100,70)+tap(100,106)+tap(100,142)+tap(100,210)+
            tap(330 if exit_menu else 100,210 if exit_menu else 80))
        self.watched=None;self.pictures={};self.volume_trace=[];self.menu_events=0
        self.word(0x800026c0,0x80001900);self.callbacks[0x80001900]=self.coordinates
        self.write(0x80001900,struct.pack('<6I',0x27bdffa8,0xafbf0050,0,0,0x00a0b821,0x0080b021));self.position=(330,210)
    def coordinates(self,x,y,*a):
        self.write(x,struct.pack('<H',self.position[0]));self.write(y,struct.pack('<H',self.position[1]))
        self.uc.reg_write(UC_MIPS_REG_PC,self.uc.reg_read(UC_MIPS_REG_RA));return 0
    def event(self,code,key,*a):
        frame=struct.unpack('<I',self.read(self.symbols['h1_ps1_stats']+16,4))[0];st=words(self)
        if frame>=30 and not self.opened:self.opened=True;event=(11,0)
        elif st[1]:
            assert not self.audio_active and not self.audio_queue,'Menu must stop/cancel native PCM'
            assert frame==30,'Guest frames advanced in menu'
            if self.watched is None:
                abi=struct.unpack('<10I',self.read(self.symbols['h1_ps1_abi'],40))
                ram=struct.unpack('<I',self.read(self.symbols['psxM'],4))[0]
                self.watched=[(self.symbols['psxRegs'],abi[1]),(ram,4096)]
            current=[self.read(p,n) for p,n in self.watched]
            if self.frozen is None:self.frozen=current
            assert current==self.frozen,'Guest registers/RAM changed during paused UI'
            page,cursor,capture=st[2:5]
            picture={0:'root',1:'mapping',2:'sound',3:'display',4:'about',5:'discs'}[page]
            if picture not in self.pictures:self.pictures[picture]=self.read(0x82000000,480*272*4)
            self.volume_trace.append(self.system_volume)
            if self.idle<12:self.idle+=1;event=(-1,-1)
            else:
                assert self.actions,'Menu did not close as scripted'
                action=self.actions.pop(0);self.menu_events+=1
                if action[0] in [0,8,11]:self.position=action[1:];event=(-1,-1) if action[0]==0 else (action[0],0)
                else:event=action
        else:return super().event(code,key,*a)
        self.word(code,event[0]);self.word(key,event[1]);return 0

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);a=ap.parse_args()
    guest=(ROOT/'build/test-rom/H1TEST.exe').read_bytes();m=Menu(a.bda,guest);m.run()
    assert m.opened and not m.actions and len(m.pictures)==5
    settings=state(m);assert settings[3]==15 and settings[16]==0 # E owns Cross, Z no longer does.
    assert list(settings[45:53])==[65,1,0,2,1,1,0,0],list(settings[45:53])
    assert 0 in m.volume_trace and 100 in m.volume_trace and 65 in m.volume_trace
    assert m.system_volume==37 and m.volume_changes[-1]==37,'Device volume must restore on exit'
    files={p:d for p,d in m.files.items() if '\\cfg-' in p};assert len(files)==1
    second=PS1Machine(a.bda,guest,files=m.files);second.stop_after=6;second.run();assert state(second)==settings
    assert 65 in second.volume_changes and second.system_volume==37
    out=ROOT/'build/verification/pause-menu';out.mkdir(parents=True,exist_ok=True)
    for name,data in m.pictures.items():Image.frombytes('RGB',(480,272),data,'raw','BGRX').save(out/(name+'.png'))
    exiting=Menu(a.bda,guest,exit_menu=True);exiting.run()
    assert struct.unpack('<I',exiting.read(exiting.symbols['h1_ps1_stats']+16,4))[0]==30 and words(exiting)[6]==1
    report={'ok':True,'sha256':hashlib.sha256(a.bda.read_bytes()).hexdigest(),'environment':'actual compiled MIPS + H1 service/register models; no physical device test',
        'menu_events':m.menu_events,'checks':['touch opens pause, opening release and synthetic Escape consumed',
        'guest CPU/RAM and frame count frozen with PCM stopped','drag off button cancels',
        '14-button mapping screen, reserved key rejected, Cross remapped to E',
        'volume drag polls held pen, clamps 0..100, release cannot activate underlying button',
        'volume/mute/quality/turbo/GPU/LCD/HUD settings and per-game reopen',
        'resume runs guest again; explicit exit restores clocks and original volume without resource leaks']}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
