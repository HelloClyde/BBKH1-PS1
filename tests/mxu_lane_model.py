"""Independent MXU1 lane semantics; never a cycle/performance model."""
import struct
import sys
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import UC_MIPS_REG_0,UC_MIPS_REG_PC,UC_MIPS_REG_CP0_STATUS

def signed(v,bits):
    v&=(1<<bits)-1
    return v-(1<<bits) if v&(1<<(bits-1)) else v

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mxu_isa import audit

def install(m,payload):
    start=payload.find(struct.pack('<I',0x50314d58))
    if start<0:return None
    audit(payload)
    end=payload.index(struct.pack('<I',0x50314d59),start+4)
    start+=0x83c00024;end+=0x83c00020
    state={'xr':[0]+[(i*0x1234abcd)&0xffffffff for i in range(1,16)]+[0], 'calls':0,'operations':0,'max_masked_instructions':0}
    uc=m.uc
    def reg(i):return uc.reg_read(UC_MIPS_REG_0+i)&0xffffffff
    def hook(uc,pc,size,_):
        w=struct.unpack('<I',m.read(pc,4))[0];xr=state['xr']
        status=uc.reg_read(UC_MIPS_REG_CP0_STATUS)
        if pc==start:
            state['saved']=(xr[:],status);state['calls']+=1;state['masked']=0
        if not status&1:state['masked']+=1
        if w==0x03e00008:
            assert (xr,status)==state['saved'],'MXU/IRQ context was not preserved'
            state['max_masked_instructions']=max(state['max_masked_instructions'],state['masked'])
        if w>>26!=28 or w&63==2:return # ordinary MIPS MUL
        state['operations']+=1;op=w&63;a=w>>6&15;b=w>>10&15;c=w>>14&15;d=w>>18&15
        assert not status&1,'IRQ enabled inside live MXU context'
        if op in (0x2e,0x2f):
            n=w>>6&31;g=w>>16&31;assert n<=16
            if op==0x2e:uc.reg_write(UC_MIPS_REG_0+g,xr[n])
            elif n:xr[n]=reg(g)
        else:
            assert xr[16]&1,'MXU disabled'
            vb,vc=xr[b],xr[c]
            if op==0x10:
                addr=(reg(w>>21&31)+signed(w>>10&1023,10)*4)&0xffffffff
                xr[a]=struct.unpack('<I',m.read(addr,4))[0]
            elif op in (0x30,0x33):
                shift=w>>22&15
                xr[a]=((vb<<shift) if op==0x30 else signed(vb,32)>>shift)&0xffffffff
                xr[d]=((vc<<shift) if op==0x30 else signed(vc,32)>>shift)&0xffffffff
            elif op==0x32:
                shift=w>>22&15
                xr[a]=((signed(vb,32)>>shift&65535)<<16)|(signed(vc,32)>>shift&65535)
            elif op==0x19:
                assert w>>22&3==0 and w>>24&3==0,'JZ4740 supports D32ACC, not Release-2 D32ASUM/ACCM'
                xr[a]=(xr[a]+vb+vc)&0xffffffff;xr[d]=(xr[d]+vb+vc)&0xffffffff
            elif op==0x0e:
                assert w>>22&15==0
                value=((vb+vc)&65535)|((((vb>>16)+(vc>>16))&65535)<<16)
                xr[a]=value;xr[d]=value
            elif op==0x3d:
                assert w>>24&3==3
                xr[a]=(vb&0xffff0000)|(vc>>16);xr[d]=((vb&65535)<<16)|(vc&65535)
            elif op==0x07:
                assert w>>18&7==6 and w>>21&7==0
                vals=[signed(vc,16),signed(vc>>16,16),signed(vb,16),signed(vb>>16,16)]
                xr[a]=sum(max(0,min(255,v))<<(8*i) for i,v in enumerate(vals))
            else:raise AssertionError('Unknown MXU opcode '+hex(w))
        xr[0]=0;uc.reg_write(UC_MIPS_REG_PC,pc+4)
    uc.hook_add(UC_HOOK_CODE,hook,begin=start,end=end-1)
    return state
