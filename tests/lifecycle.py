"""Exercise allocation failure, selector cancel and malformed EXE cleanup."""
from pathlib import Path
import json,struct,sys
from smoke import PS1Machine,ROOT

def main():
    bda=Path(sys.argv[1]);guest=(ROOT/'build/test-rom/H1TEST.exe').read_bytes()
    class FaultMachine(PS1Machine):
        def __init__(self,*args,fail_bytes=0,fail_match=1,**kwargs):
            self.fail_bytes,self.fail_match,self.matches=fail_bytes,fail_match,0
            super().__init__(*args,**kwargs);self.stop_after=6
        def alloc(self,n,*args):
            if n==self.fail_bytes:
                self.matches+=1
                if self.matches==self.fail_match:return 0
            return super().alloc(n,*args)
    passed=[]
    for name,size,match,error in [('JIT allocation fallback',4*1024*1024+63,1,0),
        ('GPU allocation failure',2101248+63,1,3),('SPU primary allocation failure',524288+63,3,3),
        ('SPU stream allocation failure',176400+63,1,3)]:
        m=FaultMachine(bda,guest,fail_bytes=size,fail_match=match);m.expected_error=error;m.run()
        st=struct.unpack('<33I',m.read(m.symbols['h1_ps1_stats'],132))
        assert st[2]==5 and st[3]==error and m.matches>=match,(name,st)
        if not error:assert st[19]==1 and st[22:26]==(17,34,4096,12),st
        passed.append(name)
    class Cancel(PS1Machine):
        def select_file(self,directory,extension,output,*args):self.write(output,b'\0');return 0
    m=Cancel(bda,guest);m.run();assert m.gui_opens==1;passed.append('selector cancel restores native display mode')
    for name,offset,value in [('truncated',None,None),('RAM end overflow',0x18,0x801ffffc),
        ('non-RAM target',0x18,0x1f801000),('unaligned entry',0x10,0x80010001),('oversized text',0x1c,0xffffffff)]:
        data=bytearray(guest[:32] if offset is None else guest)
        if offset is not None:struct.pack_into('<I',data,offset,value)
        m=PS1Machine(bda,bytes(data));m.expected_error=4;m.run()
        st=struct.unpack('<33I',m.read(m.symbols['h1_ps1_stats'],132))
        assert st[2:5]==(5,4,0) and m.gui_opens==1,(name,st)
        passed.append('EXE '+name)
    report={'ok':True,'sha256':m.metadata['sha256'],'environment':'compiled MIPS + H1 service models',
            'checks':passed,'all_cases_returned_without_resource_leaks':True}
    (bda.parent/'lifecycle.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
