"""Summarize physical H1Debug reports; never treat host/model seconds as FPS."""
from pathlib import Path
import argparse,json

def interval(first,last):
    ticks=((last['raw_end']-first['raw_end'])&0xffffffff)-(last.get('paused_ticks',0)-first.get('paused_ticks',0))
    if ticks<=0 or last['frames']<=first['frames'] or not last['tick_hz']:return None
    seconds=ticks/last['tick_hz']
    return {'frame_first':first['frames'],'frame_last':last['frames'],'seconds_device':seconds,
            'logical_fps':(last['frames']-first['frames'])/seconds,
            'displayed_per_second':(last['displayed']-first['displayed'])/seconds,
            **{field+'_fraction':(last.get(field,0)-first.get(field,0))/ticks for field in ('gpu_ticks','spu_ticks','video_ticks','disc_ticks')}}

def audio_interval(report,first,last):
    points=[p for p in report.get('audio_snapshots',[]) if p['state']==3 and first<=p['frame_observed']<=last]
    if len(points)<2:return None
    a,b=points[0]['counters'],points[-1]['counters']
    return {'frame_first':points[0]['frame_observed'],'frame_last':points[-1]['frame_observed'],
            'output_active_at_all_samples':(all(p['counters']['active']==1 for p in points)
                                            if all('active' in p['counters'] for p in points) else None),
            **{name+'_delta':(b[name]-a[name])&0xffffffff for name in ('nonzero','dropped','failures','underruns') if name in a and name in b}}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('report',type=Path)
    ap.add_argument('--window',action='append',default=[],help='Inclusive logical frame range START:END')
    args=ap.parse_args();report=json.loads(args.report.read_text(encoding='utf-8'))
    if report.get('environment')!='physical BBK H1/Y100 V1.41':ap.error('requires a physical hardware report')
    windows=[]
    for value in args.window:
        first,last=map(int,value.split(':'))
        samples=[p['stats'] for p in report['snapshots'] if p['stats']['state']==3 and first<=p['stats']['frames']<=last]
        if len(samples)<2:ap.error(f'not enough running snapshots in {value}')
        windows.append(interval(samples[0],samples[-1])|{'audio':audio_interval(report,first,last)})
    print(json.dumps({k:report[k] for k in ('environment','sha256','game','completed','core_interval_seconds','logical_fps','displayed_per_second')}|
                     {'physical_audio_requested':report.get('physical_audio_requested',not report['build']['options']['benchmark']),'windows':windows},indent=2))
if __name__=='__main__':main()
