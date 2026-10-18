"""Decode exclusive diagnostic wall-clock phases; never infer CPU clocks."""
import struct
NAMES=('CPU/JIT/other','JIT compile','code invalidation','events','GTE',
       'VLC gateway/validation','immutable code checks','VLC decoding','empty stream HLE',
       'movie gateway','movie queue/DMA SDK','movie upload SDK','MDEC DMA/RLE',
       'MDEC IDCT','MDEC RGB','GPU core','SPU synthesis','LCD conversion',
       'disc service/cache','PCM output','input','pacing wait')
BINS=120
BYTES=BINS*len(NAMES)*8
def decode(header,raw,hz):
    h=struct.unpack('<8I',header)
    assert h[:4]==(0x31504850,1,len(NAMES),BINS)
    assert len(raw)==BYTES and hz
    values=list(struct.iter_unpack('<II',raw));bins=[]
    for b in range(BINS):
        rows=[{'name':name,'calls':values[b*len(NAMES)+i][0],'raw_ticks':values[b*len(NAMES)+i][1]} for i,name in enumerate(NAMES)]
        bins.append({'first_frame':b*100,'last_frame_exclusive':(b+1)*100,'phases':rows})
    total=sum(v[1] for v in values)
    assert total==((h[5]-h[4])&0xffffffff),(total,h)
    return {'instrumentation_adds_overhead':True,'clock_hz':hz,'timings_are_exclusive':True,
            'scope':'wall clock including profiler and OS/debug scheduling overhead; CPU/JIT/other is unwrapped remainder',
            'raw_ticks':total,'seconds':total/hz,'transitions':h[6],'recording':h[7],'bins':bins}
def window(report,lo,hi):
    assert lo%100==hi%100==0 and 0<=lo<hi<=12000
    counts=[0]*len(NAMES);ticks=[0]*len(NAMES)
    for b in report['bins']:
        if lo<=b['first_frame']<hi:
            for i,row in enumerate(b['phases']):counts[i]+=row['calls'];ticks[i]+=row['raw_ticks']
    total=sum(ticks)
    return {'first_frame':lo,'last_frame_exclusive':hi,'seconds':total/report['clock_hz'],
            'phases':sorted([{'name':name,'calls':c,'raw_ticks':t,'seconds':t/report['clock_hz'],
                'fraction':t/total if total else 0} for name,c,t in zip(NAMES,counts,ticks)],key=lambda r:r['raw_ticks'],reverse=True)}
