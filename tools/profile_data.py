"""Decode diagnostic UNAI/GTE counters; requested pixels are before masks."""
import struct
GTE_NAMES={1:'RTPS',0x30:'RTPT',0x12:'MVMVA',6:'NCLIP',0x2d:'AVSZ3',0x2e:'AVSZ4',0x28:'SQR',
 0x1b:'NCCS',0x3f:'NCCT',0x13:'NCDS',0x16:'NCDT',0xc:'OP',0x29:'DCPL',0x3d:'GPF',0x3e:'GPL',
 0x10:'DPCS',0x2a:'DPCT',0x1e:'NCS',0x20:'NCT',0x1c:'CC',0x11:'INTPL',0x14:'CDP'}
RASTER_BYTES=4*2048*16
GTE_BYTES=64*16

def decode(raster,gte):
    assert len(raster)==RASTER_BYTES and len(gte)==GTE_BYTES
    spans=[]
    for index,(calls,pixels) in enumerate(struct.iter_unpack('<QQ',raster)):
        if not calls:continue
        kind,cf=divmod(index,2048)
        spans.append({'kind':['polygon','sprite','tile','line'][kind],'cf':cf,'calls':calls,'requested_pixels':pixels,
                      'lighting':bool(cf&1),'blend':bool(cf&2),'mask_check':bool(cf&4),'blend_mode':(cf>>3)&3,
                      'texture_mode':(cf>>5)&3,'gouraud':bool(cf&128),'mask_set':bool(cf&256),
                      'dither':bool(cf&512),'blit_mask':bool(cf&1024)})
    operations=[]
    for opcode,(calls,ticks) in enumerate(struct.iter_unpack('<QQ',gte)):
        if calls:operations.append({'opcode':opcode,'name':GTE_NAMES.get(opcode,hex(opcode)),'calls':calls,'raw_ticks':ticks})
    return {'instrumentation_adds_overhead':True,'pixel_count_is_requested_before_transparency_and_masks':True,
            'raster':sorted(spans,key=lambda row:row['requested_pixels'],reverse=True),
            'gte':sorted(operations,key=lambda row:row['raw_ticks'],reverse=True)}
