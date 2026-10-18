"""Execute full H1PS1 BDA and its generated MIPS code with H1 API models."""
from pathlib import Path
import argparse,json,struct,sys,time
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_INVALID
from unicorn.mips_const import UC_MIPS_REG_V0,UC_MIPS_REG_PC,UC_MIPS_REG_RA,UC_MIPS_REG_SP
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/support'))
from mips_smoke import Machine,PAYLOAD_OFFSET

class PS1Machine(Machine):
    def __init__(self,bda,guest,path='A:\\PS1\\H1TEST.exe',bios=None):
        files={path:guest}
        if bios is not None:files['A:\\PS1\\bios.bin']=bios
        super().__init__(bda,files=files,path=path)
        from mxu_lane_model import install
        self.ps1_mxu=install(self,bda.read_bytes()[PAYLOAD_OFFSET:])
        self.metadata=json.loads(bda.with_suffix('.build.json').read_text())
        self.symbols=self.metadata['symbols'];self.rtc_reads=0;self.progress=0
        from clock_model import install as install_clock
        self.clock_model=install_clock(self)
        if self.metadata['options'].get('fast_map'):
            from fastmap_model import install as install_fastmap
            self.fastmap_model=install_fastmap(self,bda)
        addr=self.symbols['h1_ps1_rtc']
        self.uc.hook_add(UC_HOOK_CODE,self.rtc_hook,begin=addr,end=addr)
        self.uc.hook_add(UC_HOOK_MEM_INVALID,self.bad_memory)
    def run(self):
        from clock_model import enable,verify_restored
        enable(self)
        start=time.monotonic()
        self.uc.emu_start(0x83c00020,0,timeout=600_000_000,count=16_000_000_000)
        assert self.finished,f'MIPS did not return, PC={self.uc.reg_read(UC_MIPS_REG_PC):08x}'
        assert self.uc.reg_read(UC_MIPS_REG_V0)==getattr(self,'expected_error',0)
        assert self.uc.reg_read(UC_MIPS_REG_SP)==0x83aff000
        for i,reg in enumerate(self.saved_regs):assert self.uc.reg_read(reg)==0x12340000+i
        assert not self.handles and not self.allocations,(self.handles,self.allocations)
        assert not self.gui_active and self.gui_opens==self.gui_closes
        assert not self.audio_active and not self.audio_initialized and not self.audio_queue
        assert not self.dialogs,self.dialogs
        if self.metadata['options'].get('fast_map'):
            fastmap=struct.unpack('<13I',self.read(self.symbols['h1_fastmap_stats'],52))
            if fastmap[0]:assert fastmap[2:4]==(2,0) and fastmap[10]==0 and fastmap[12]==32,fastmap
            else:assert fastmap[:3]==(0,0,0),fastmap  # cancelled before CPU initialization
        verify_restored(self)
        return time.monotonic()-start
    def bad_memory(self,uc,access,address,size,value,data):
        pc=uc.reg_read(UC_MIPS_REG_PC)
        before=sorted((v,k) for k,v in self.symbols.items() if v<=pc)[-3:]
        print('BAD_MEMORY',hex(pc),hex(address),size,hex(value),before,flush=True)
        print('LOG',self.files.get('A:\\PS1\\h1ps1.log',b''),flush=True)
        return False
    def rtc_hook(self,uc,addr,size,data):
        self.rtc_reads+=1
        frame=struct.unpack('<I',self.read(self.symbols['h1_ps1_stats']+16,4))[0]
        if getattr(self,'stop_after',0) and frame>=self.stop_after:
            self.word(self.symbols['h1_ps1_stats']+60,1)
        if frame//300>self.progress:self.progress=frame//300;print(f'model frames={frame}',flush=True)
        uc.reg_write(UC_MIPS_REG_V0,1791199800+self.rtc_reads//64)
        uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
    def select_file(self,directory,extension,output,*a):
        assert self.string(directory)=='A:\\PS1\\'
        assert self.string(extension)=='exe;bin;iso;cue'
        self.write(output,self.rom_path.encode('gbk')+b'\0');return 0
    def fopen(self,path,mode,*a):
        # Native H1 append opens at EOF; adapt the shared model too.
        p,m=self.string(path),self.string(mode)
        if 'a' in m and p not in self.files:self.files[p]=b''
        result=super().fopen(path,mode,*a)
        if result and 'a' in m:self.handles[result][2].seek(0,2)
        return result
    def fclose(self,handle,*a):
        p,m,f=self.handles[handle]
        if 'a' in m:self.files[p]=f.getvalue()
        return super().fclose(handle,*a)
    def game_buffer(self,info,context,*a):
        assert self.gui_active
        self.write(info,struct.pack('<6H',0,480,272,1920,0,32))
        self.blits+=1;return 0x82000000
    def event(self,code,key,*a):
        stats=self.symbols['h1_ps1_stats']
        frame=struct.unpack('<I',self.read(stats+16,4))[0]
        if hasattr(self,'scripted'):
            for f,k in list(self.scripted):
                if frame>=f:
                    self.events.append((9,k));self.release_script.append((frame+12,k));self.scripted.remove((f,k))
            for f,k in list(self.release_script):
                if frame>=f:self.events.append((10,k));self.release_script.remove((f,k))
        return super().event(code,key,*a)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path)
    ap.add_argument('--game',type=Path);ap.add_argument('--bios',type=Path)
    ap.add_argument('--press-at',action='append',default=[])
    ap.add_argument('--stop-after',type=int,help='Stop a normal interactive build after N frames')
    ap.add_argument('--output-dir',type=Path);args=ap.parse_args()
    output=args.output_dir or args.bda.parent;output.mkdir(parents=True,exist_ok=True)
    guest=args.game or ROOT/'build/test-rom/H1TEST.exe'
    game_path='A:\\PS1\\game'+guest.suffix if args.game else 'A:\\PS1\\H1TEST.exe'
    machine=PS1Machine(args.bda,guest.read_bytes(),path=game_path,bios=args.bios.read_bytes() if args.bios else None)
    machine.stop_after=args.stop_after or 0
    if not machine.metadata['options']['test_frames'] and not machine.stop_after:ap.error('normal build requires --stop-after')
    machine.scripted=[tuple(map(int,s.split(':'))) for s in args.press_at]
    machine.release_script=[]
    try: elapsed=machine.run()
    except Exception:
        pc=machine.uc.reg_read(UC_MIPS_REG_PC)
        print('STOP_PC',hex(pc),sorted((v,k) for k,v in machine.symbols.items() if v<=pc)[-4:],flush=True)
        print('LOG',machine.files.get('A:\\PS1\\h1ps1.log',b''),flush=True)
        print('ALLOCS',sorted(hex(p) for p in machine.allocations),'HEAP',hex(machine.heap),flush=True)
        words=machine.metadata.get('stats_words',26)
        partial=list(struct.unpack(f'<{words}I',machine.read(machine.symbols['h1_ps1_stats'],words*4)))
        print('STATS',partial,flush=True)
        (output/'failure.json').write_text(json.dumps({'ok':False,'pc':pc,'stats':partial,'sha256':machine.metadata['sha256']},indent=2))
        raise
    words=machine.metadata.get('stats_words',26)
    stats=struct.unpack(f'<{words}I',machine.read(machine.symbols['h1_ps1_stats'],words*4))
    expected=5000*5001//2*51
    assert stats[3]==0 and stats[4]==(machine.stop_after or machine.metadata['options']['test_frames']),stats
    assert machine.system_volume==37 and all(v==37 for v in machine.volume_changes),machine.volume_changes
    if not machine.metadata['options']['benchmark'] and stats[4]>=120:
        assert machine.audio_submissions,'native PCM was never started'
    cpu_checks=stats[22:26]
    if not args.game:
        assert stats[17]==expected,(hex(stats[17]),hex(expected))
        assert cpu_checks==(17,34,4096,12),cpu_checks
        if machine.metadata['options'].get('idle'):assert stats[30]>0 and stats[31]>=50,stats[30:]
    pixels=struct.unpack('<'+('I'*(480*272)),machine.read(0x82000000,480*272*4))
    if not args.game:
        assert pixels[24*480]==0 and pixels[136*480+240]!=0
        assert pixels[80*480+130]&0xff0000,hex(pixels[80*480+130])
    from PIL import Image
    im=Image.new('RGB',(480,272));im.putdata([((p>>16)&255,(p>>8)&255,p&255) for p in pixels]);im.save(output/'smoke.png')
    report={'ok':True,'environment':'Unicorn MIPS32 + H1 service models','seconds_host':elapsed,
            'stats':list(stats),'sha256':machine.metadata['sha256'],'allocations_remaining':len(machine.allocations),
            'handles_remaining':len(machine.handles)}
    report['native_audio']={'submissions':len(machine.audio_submissions),'volume_preserved':machine.system_volume==37}
    if machine.metadata['options'].get('detailed_profile'):
        sys.path.insert(0,str(ROOT/'tools'))
        from profile_data import decode,RASTER_BYTES,GTE_BYTES
        detail=decode(machine.read(machine.symbols['h1_raster_stats'],RASTER_BYTES),machine.read(machine.symbols['h1_gte_stats'],GTE_BYTES))
        if not args.game:
            assert sum(row['requested_pixels'] for row in detail['raster'])>0
            assert next(row['calls'] for row in detail['gte'] if row['name']=='NCLIP')==1
        (output/'detail-profile.json').write_text(json.dumps(detail,indent=2))
    if not args.game:report['guest_checks']={'arithmetic':expected,'self_modifying_code':list(cpu_checks[:2]),
                            'gte_nclip':cpu_checks[2],'branch_delay':cpu_checks[3]}
    else:report['game']={'local_path':str(args.game),'sha256':__import__('hashlib').sha256(guest.read_bytes()).hexdigest(),'displayed':stats[5]}
    (output/'smoke.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
