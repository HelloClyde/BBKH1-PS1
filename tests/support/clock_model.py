"""JZ4740 register behavior for compiled-code tests, never a timing model."""
import struct
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE

BASE={0x10000000:0x40662220,0x10000010:0x1b000520,0x10000020:0,
      0x10000060:4,0x10000064:36,0x10000068:13,0x1000006c:6,0x10000074:4,
      0x13010080:0x05aa3211,0x13010084:0x83,0x1301008c:30,
      0x13050000:0x980,0x13050030:0x20000c0d,0x13050034:0xb0,0x13050040:0x57bbc0,0x13050050:0}

def install(m):
    for a in [0x10000000,0x13010000,0x13050000]:m.uc.mem_map(a,4096)
    for a,v in BASE.items():m.word(a|0xa0000000,v)
    return {'registers':dict(BASE),'writes':[],'enabled':False,'pending':False,'polls':0,'rates':[]}

def enable(m):
    state=m.clock_model;regs=state['registers']
    if state['enabled']:return
    state['enabled']=True
    def read(uc,access,address,size,value,data):
        a=address&0x1fffffff
        if a==0x10000010 and state['pending']:
            state['polls']+=1
            if state['polls']>=4:regs[a]|=0x400;state['pending']=False
        if a in regs:m.write(address,int(regs[a]).to_bytes(size,'little'))
    def write(uc,access,address,size,value,data):
        a=address&0x1fffffff;state['writes'].append([a,size,value])
        if a==0x13050030 and value&16:regs[0x13050034]|=1;value&=~8
        if a==0x10000010:
            assert not m.audio_active,'PCM must be stopped before PLL writes'
            if (value^regs[a])&0xfffffb00:
                assert value&255==255
                state['pending']=True;state['polls']=0
            else:value|=regs[a]&0x400
            mhz=12*((value>>23)+2)/(((value>>18)&31)+2)
            assert mhz in [336,384,408];state['rates'].append(mhz)
        regs[a]=value
    for start,end in [(0x10000000,0x10000fff),(0x13010000,0x13010fff),(0x13050000,0x13050fff)]:
        m.uc.hook_add(UC_HOOK_MEM_READ,read,begin=start,end=end)
        m.uc.hook_add(UC_HOOK_MEM_WRITE,write,begin=start,end=end)

def verify_restored(m):
    s=m.clock_model
    if m.metadata['options'].get('cpu_mhz',336)>336 and s['writes']:
        assert 408 in s['rates']
        for a,v in BASE.items():
            if a==0x13050034:continue
            mask=~0x400 if a==0x10000010 else ~0x80 if a==0x13010084 else 0xffffffff
            assert (s['registers'][a]&mask)==(v&mask),hex(a)
