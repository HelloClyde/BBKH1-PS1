"""Boot the project's own ISO from compressed PBP and swap in the real menu."""
import argparse,json,struct
from pathlib import Path
from PIL import Image
from smoke import PS1Machine,ROOT
from pause_menu import Menu,tap
from pbp_fixture import pbp,selftest_disc


def check_guest(machine,frames):
    stats=struct.unpack('<33I',machine.read(machine.symbols['h1_ps1_stats'],132))
    assert stats[2:5]==(5,0,frames),stats
    assert stats[17]==5000*5001//2*51 and stats[22:26]==(17,34,4096,12),stats
    assert machine.audio_submissions


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bda',type=Path);args=parser.parse_args()
    disc=selftest_disc((ROOT/'build/test-rom/H1TEST.exe').read_bytes())
    single=PS1Machine(args.bda,pbp([disc]),path='A:\\PS1\\H1TEST.PBP');single.stop_after=120
    single.run();check_guest(single,120)
    multiple=Menu(args.bda,pbp([disc,disc]),path='A:\\PS1\\MULTI.PBP')
    multiple.actions=[(9,24),(8,330,210),(10,24)]+tap(100,210)+tap(330,75)+tap(400,250)+tap(100,75)
    multiple.run();check_guest(multiple,90)
    assert not multiple.actions and 'discs' in multiple.pictures
    log=multiple.files['A:\\PS1\\h1ps1.log'].decode()
    assert 'PBP discs=2 selected=1' in log and 'PBP_SWITCH disc=2 count=2' in log,log
    out=ROOT/'build/verification/pbp';out.mkdir(parents=True,exist_ok=True)
    for name,data in multiple.pictures.items():
        Image.frombytes('RGB',(480,272),data,'raw','BGRX').save(out/(name+'.png'))
    report={'ok':True,'sha256':single.metadata['sha256'],
        'environment':'exact compiled BDA with H1 service/register models; no physical hardware test',
        'checks':['selector accepts EBOOT.PBP','original ISO9660/PS-X EXE boots from compressed sectors',
                  'arithmetic/self-modifying code/GTE/branch-delay guest checks',
                  'native PCM starts','touch menu selects disc 2 from multi-disc PBP',
                  'guest registers/RAM stay frozen while menu changes the disc',
                  'lid event deferred until resume; guest continues without restart',
                  'all files, allocations, native audio and clock state cleaned up']}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
