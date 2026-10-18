"""Actual compiled bounded diagnostic: read correlation and trace retention."""
from pathlib import Path
import argparse,json,struct,sys
from vlc_hle_equivalence import CPU
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from audio_diag_data import decode

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);args=ap.parse_args()
    cpu=CPU(args.bda,True);sy=cpu.m.symbols;stats=sy['h1_ps1_stats']
    def word(i,v):cpu.m.word(stats+4*i,v)
    def report():return decode(cpu.m.read(sy['h1_audio_diag_state'],64),cpu.m.read(sy['h1_audio_diag_gaps'],8192))
    cpu.call(sy['h1_audio_diag_reset']);word(2,3);word(4,100)
    for i,v in ((26,10),(28,20),(10,30)):word(i,v)
    cpu.call(sy['h1_audio_diag_retire'],128,256,0,128);assert report()['gap_count']==0
    cpu.call(sy['h1_audio_diag_io'],1234,3);word(4,101)
    for i,v in ((26,15),(28,27),(10,31)):word(i,v)
    cpu.call(sy['h1_audio_diag_retire'],512,300,128,640);cpu.call(sy['h1_audio_diag_gap_finish'])
    r=report();g=r['gaps'][0]
    assert r['gap_count']==1 and r['disc_reads']==1 and r['disc_ticks']==3 and r['max_read_ticks']==3
    assert r['read_tick_histogram']['3-4']==1
    assert [g[k] for k in ('frame','consumed','queued','missing','disc_reads','disc_ticks','gpu_ticks','spu_ticks','video_ticks','last_io_lba','last_io_ticks')]==[101,512,300,212,1,3,5,7,1,1234,3]
    for i in range(140):
        word(4,200+i);cpu.call(sy['h1_audio_diag_retire'],128,0,0,128)
    r=report();assert r['gap_count']==141 and r['omitted']==13 and len(r['gaps'])==128
    assert r['gaps'][0]['frame']==212 and r['gaps'][-1]['frame']==339
    assert all(p['disc_reads']==p['disc_ticks']==0 for p in r['gaps'])
    word(2,6);cpu.call(sy['h1_audio_diag_retire'],128,0,0,128);assert report()['gap_count']==141
    result={'ok':True,'sha256':cpu.m.metadata['sha256'],'checks':['actual compiled recorder and host decoder','no gap with enough queued PCM','read latency histogram and inter-retire deltas','GPU/SPU/video deltas','128-record retention and omitted count','freeze excluded']}
    (args.bda.parent/'audio-diagnostic-contract.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
