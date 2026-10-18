"""Optional lossy rendering in a prepared core, never in the pinned checkout."""
from pathlib import Path
import re
from prepare import replace


def function(text, signature):
    start=text.index(signature+'\n{');brace=text.index('{',start)
    end=brace+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]


def prepare_spu_turbo(root:Path,core:Path):
    spu=core/'spu/spu_pcsxrearmed/spu.c'
    adsr=core/'spu/spu_pcsxrearmed/adsr.c'
    signature='static int MixADSR(ADSRInfoEx *adsr, int ns_to)'
    original=function(adsr.read_text(encoding='utf-8'),signature)
    # Retain every upstream envelope transition, end index and per-sample
    # update. The original SkipADSR has different release-end rounding, so
    # it cannot stand in for the envelope state of a skipped quiet voice.
    scale=re.compile(r'(?m)^([ \t]*)ChanBuf\[ns\] \*= EnvelopeVol >> 21;\n\1ChanBuf\[ns\] >>= 10;')
    assert len(scale.findall(original))==7
    half=scale.sub(lambda m:m[1]+'if (!(ns & 1)) {\n'+m[0]+'\n'+m[1]+'}',
        original.replace('MixADSR(', 'h1_turbo_adsr_half(',1))
    quiet=scale.sub('',original.replace('MixADSR(', 'h1_turbo_adsr_quiet(',1))
    with adsr.open('a',encoding='utf-8') as f:f.write('\n'+half+'\n'+quiet+'\n')
    text=spu.read_text(encoding='utf-8')
    text='#include "spu_turbo.h"\n'+text
    old=function(text,'static void do_channels(int ns_to)')
    turbo=r'''
/* Same event/state flow as upstream do_channels; only audible rendering is
 * lossy. Voice 1/3 readback, noise and FM stay on the full sample path. */
static int h1_turbo_quiet(const SPUCHAN *channel)
{
 int lv=channel->iLeftVolume,rv=channel->iRightVolume;
 if(lv<0)lv=-lv;
 if(rv<0)rv=-rv;
 int volume=lv>rv?lv:rv;
 if(!volume)return 1;
 const ADSRInfoEx *a=&channel->ADSRX;
 if(a->EnvelopeVol<0)return 0;
 if(a->State!=ADSR_RELEASE &&
    !(a->State==ADSR_SUSTAIN && !a->SustainIncrease))return 0;
 /* Approximate full-scale peak <=256/32768 (-42 dB), not a guarantee
  * for malformed/unclamped ADPCM. Attack transients are never removed. */
 return (a->EnvelopeVol>>21)*volume<=131072;
}
static void h1_turbo_channels(int ns_to)
{
 unsigned mask=spu.dwNewChannel&0xffffff;
 for(int ch=0;mask;ch++,mask>>=1)if(mask&1)StartSound(ch);
 ++h1_spu_turbo_stats[0];h1_spu_turbo_stats[4]+=ns_to;
 mask=spu.dwChannelOn&0xffffff;
 for(int ch=0;mask;ch++,mask>>=1){
  if(!(mask&1))continue;
  SPUCHAN *s_chan=&spu.s_chan[ch];
  int *SB=spu.SB+ch*SB_SIZE;
  int sinc=s_chan->sinc,d;
  int protected_voice=ch==1||ch==3||s_chan->bFMod||s_chan->bNoise;
  int quiet=!protected_voice && h1_turbo_quiet(s_chan);
  if(quiet){
   d=h1_spu_samples_quiet(decode_block,NULL,ch,ns_to,SB,sinc,&s_chan->spos,&s_chan->iSBPos);
   d=h1_turbo_adsr_quiet(&s_chan->ADSRX,d);
   ++h1_spu_turbo_stats[2];h1_spu_turbo_stats[6]+=ns_to;
  }
  else if(!protected_voice){
   d=h1_spu_samples_half(decode_block,NULL,ch,ns_to,SB,sinc,&s_chan->spos,&s_chan->iSBPos,ChanBuf);
   d=h1_turbo_adsr_half(&s_chan->ADSRX,d);
   ++h1_spu_turbo_stats[1];h1_spu_turbo_stats[5]+=ns_to;
  }
  else{
   if(s_chan->bNoise)d=do_samples_noise(ch,ns_to);
   else if(s_chan->bFMod==2 || (s_chan->bFMod==0 && !spu_config.iUseInterpolation))
    d=do_samples_noint(decode_block,NULL,ch,ns_to,SB,sinc,&s_chan->spos,&s_chan->iSBPos);
   else d=do_samples_default(decode_block,NULL,ch,ns_to,SB,sinc,&s_chan->spos,&s_chan->iSBPos);
   d=MixADSR(&s_chan->ADSRX,d);
   ++h1_spu_turbo_stats[3];
  }
  if(d<ns_to){
   spu.dwChannelOn&=~(1<<ch);s_chan->ADSRX.EnvelopeVol=0;
   if(!quiet)memset(&ChanBuf[d],0,(ns_to-d)*sizeof(ChanBuf[0]));
  }
  if(quiet)continue;
  if(ch==1 || ch==3){
   do_decode_bufs(spu.spuMem,ch/2,ns_to,spu.decode_pos);
   spu.decode_dirty_ch|=1<<ch;
  }
  if(s_chan->bFMod==2)memcpy(iFMod,ChanBuf,ns_to*sizeof(iFMod[0]));
  h1_spu_mix_half_mono(spu.SSumLR,ns_to,s_chan->iLeftVolume,s_chan->iRightVolume,ChanBuf);
 }
 if(spu.rvb->StartAddr){
  spu.rvb->CurrAddr+=ns_to/2;
  while(spu.rvb->CurrAddr>=0x40000)spu.rvb->CurrAddr-=0x40000-spu.rvb->StartAddr;
 }
}
'''
    assert text.count(old)==1
    text=text.replace(old,old+'\n'+turbo,1)
    spu.write_text(text,encoding='utf-8')
    replace(spu,'   do_channels(ns_to);',
        '   if(h1_spu_turbo_mode && !spu_config.iUseReverb && !spu_config.iUseInterpolation)\n'
        '    h1_turbo_channels(ns_to);\n   else do_channels(ns_to);')
    replace(spu,'  MixXA(SSumLR, ns_to, decode_pos);',
        '  MixXA(SSumLR, ns_to, decode_pos);\n'
        '  if(h1_spu_turbo_mode && !spu_config.iUseReverb && !spu_config.iUseInterpolation){\n'
        '   h1_spu_finish_mono(SSumLR,ns_to,volmult,spu.spuCtrl&0x4000,spu.pS);\n'
        '   spu.pS+=ns_to*2;return;\n  }')
