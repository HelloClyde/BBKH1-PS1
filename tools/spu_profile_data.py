"""Decode diagnostic SPU counters; coarse sampled timings are estimates."""
import struct
NAMES=('synthesis_total','channels_total','adpcm_decode','adsr','voice_mix',
       'finish_total','xa_mix','irq_schedule','pcm_feed_total','pcm_retire',
       'pcm_resample_total','pcm_submit','pcm_reset_total')
STRIDES=(1,1,64,16,16,1,1,1,1,1,1,1,1)
BYTES=len(NAMES)*3*4
def decode(raw,histogram):
    words=struct.unpack('<'+str(len(NAMES)*3)+'I',raw)
    stages=[]
    for i,(name,stride) in enumerate(zip(NAMES,STRIDES)):
        calls,sampled,ticks=words[i*3:i*3+3]
        stages.append({'name':name,'calls':calls,'sampled_calls':sampled,
            'sample_stride':stride,'sampled_raw_ticks':ticks,
            'estimated_raw_ticks':ticks*stride})
    return {'instrumentation_adds_overhead':True,'nested_scopes_overlap':True,
        'timer_note':'actual H1 raw tick frequency is saved in hardware stats; sampled short scopes have substantial quantization error',
        'stages':stages,'active_voice_histogram':list(struct.unpack('<25I',histogram))}
