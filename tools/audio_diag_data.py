"""Decode bounded native PCM starvation trace; no host-time FPS inference."""
import struct
FIELDS='frame raw_tick consumed queued missing retire_ticks disc_reads disc_ticks gpu_ticks spu_ticks video_ticks last_io_age last_io_lba last_io_ticks reset_ticks reserved'.split()
def decode(state,records):
    h=struct.unpack('<16I',state);assert h[:4]==(0x31474150,1,16,128)
    count=h[4];rows=[]
    for i in range(max(0,count-128),count):rows.append(dict(zip(FIELDS,struct.unpack_from('<16I',records,(i%128)*64))))
    return {'version':h[1],'gap_count':count,'observations':h[5],'disc_reads':h[6],'disc_ticks':h[7],
        'max_read_ticks':h[8],'read_tick_histogram':dict(zip(('0','1','2','3-4','5-8','9+'),h[9:15])),
        'omitted':max(0,count-128),'gaps':rows,
        'scope':'diagnostic build; coarse device ticks; missing is cursor deficit, not full audible gap duration; inter-retire correlation is not proof of cause'}
