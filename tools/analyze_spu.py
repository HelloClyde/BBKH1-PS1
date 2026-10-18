"""Compare SPU diagnostic intervals; never sum overlapping sampled timers."""
from pathlib import Path
import argparse,json

def interval(a,b):
    ticks=(b['raw_tick']-a['raw_tick'])&0xffffffff
    stages=[]
    for x,y in zip(a['profile']['stages'],b['profile']['stages']):
        calls=y['calls']-x['calls'];samples=y['sampled_calls']-x['sampled_calls']
        measured=y['sampled_raw_ticks']-x['sampled_raw_ticks'];estimate=measured*y['sample_stride']
        stages.append({'name':y['name'],'calls':calls,'sampled_calls':samples,'measured_raw_ticks':measured,
            'sample_stride':y['sample_stride'],'estimated_interval_fraction':estimate/ticks if ticks else None})
    histogram=[y-x for x,y in zip(a['profile']['active_voice_histogram'],b['profile']['active_voice_histogram'])]
    total=sum(histogram)
    return {'frame_first':a['frame_observed'],'frame_last':b['frame_observed'],'raw_ticks':ticks,
        'seconds_device':ticks/b['tick_hz'],'stages':stages,
        'active_voices_per_synthesis_group':sum(i*n for i,n in enumerate(histogram))/total if total else None,
        'active_voice_histogram':histogram}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('report',type=Path)
    ap.add_argument('--window',action='append',default=[]);args=ap.parse_args()
    report=json.loads(args.report.read_text(encoding='utf-8'))
    assert report['completed'] and report['build']['options']['spu_profile']
    windows=[]
    for value in args.window:
        lo,hi=map(int,value.split(':'));points=[p for p in report['spu_snapshots'] if lo<=p['frame_observed']<=hi and p['state']==3]
        assert len(points)>=2,value
        windows.append(interval(points[0],points[-1]))
    print(json.dumps({'sha256':report['sha256'],'instrumentation_adds_overhead':True,
        'nested_scopes_overlap':True,'sampled_short_timers_have_large_quantization_error':True,'windows':windows},indent=2))
if __name__=='__main__':main()
