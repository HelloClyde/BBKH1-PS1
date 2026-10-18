"""Actual native-key poll with remaps, chords and Enter/Confirm/ALT aliases."""
import argparse,json
from pathlib import Path
from smoke import PS1Machine,ROOT
from pause_menu import call,state

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);a=ap.parse_args()
    m=PS1Machine(a.bda,b'');m.write(0x83000000,b'A:\\PS1\\map.exe\0');call(m,'h1_settings_load',0x83000000)
    read_name=next(k for k in m.symbols if k.startswith('_Z8pad_readi'))
    poll_name=next(k for k in m.symbols if k.startswith('_Z10pad_updatev'))
    def mask(*bits):return 0xffff^sum(1<<b for b in bits)
    def press(keys):
        m.physical_keys=set(keys);m.events=[(9,k) for k in keys];call(m,poll_name)
    def read(player=0):return call(m,read_name,player)&0xffff
    press([16,17,37,25]);assert read()==mask(14,15,4,3) and read(1)==0xffff
    m.physical_keys.clear();assert read()==0xffff
    assert call(m,'h1_mapping_assign',14,3)==1
    press([3,16,17]);assert read()==mask(14,15)
    m.physical_keys={16,17};assert read()==mask(15),'Old Cross key must stop producing Cross'
    m.physical_keys.clear();assert read()==0xffff
    assert call(m,'h1_mapping_assign',3,39)==1
    assert call(m,'h1_mapping_assign',15,25)==1
    press([25]);assert read()==mask(15),'Enter must not also press Confirm mapping'
    press([39]);assert read()==mask(3),'Confirm must not also press Enter mapping'
    m.physical_keys.clear();assert read()==0xffff
    assert call(m,'h1_mapping_assign',13,26)==1
    assert call(m,'h1_mapping_assign',12,28)==1
    press([26]);assert read()==mask(13)
    press([28]);assert read()==mask(12)
    press([40,35]);assert read()==mask(7,5)
    before=state(m)
    for key in [0,5,11,12,13,24,31,41,43,44,45]:assert call(m,'h1_mapping_assign',14,key)==0 and state(m)==before
    for bit in [1,2,16,0xffffffff]:assert call(m,'h1_mapping_assign',bit,3)==0 and state(m)==before
    # Drive the real frame-boundary menu path, closing it with Z still held.
    call(m,'h1_settings_load',0x83000000);m.physical_keys.clear();m.events=[(10,k) for k in range(1,43)];call(m,poll_name);read()
    m.gui_active=True;m.word(m.symbols['h1_ps1_stats']+8,3);m.word(m.symbols['h1_ps1_stats']+16,0)
    m.events=[(9,31),(10,31),(9,16)]
    frame_name=next(k for k in m.symbols if k.startswith('_Z14pl_frame_limitv'));call(m,frame_name)
    assert m.physical_keys=={16} and read()==0xffff,'Menu confirmation must not leak Cross into the game'
    m.physical_keys.clear();assert read()==0xffff
    m.physical_keys={16};assert read()==mask(14),'Cross must work again after release and press'
    m.gui_active=False
    report={'ok':True,'sha256':m.metadata['sha256'],'checks':['default simultaneous controls and player-2 neutral',
        'remapping replaces old physical assignment without losing other held buttons',
        'Enter/Confirm and Left/Right ALT alias identities do not create phantom buttons',
        'reserved frontend/FN/power and invalid PS1 buttons rejected without mutation',
        'menu confirm stays blocked until release, then responds to a new game press']}
    out=ROOT/'build/verification';out.mkdir(exist_ok=True);(out/'mapping.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
