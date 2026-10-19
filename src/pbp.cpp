/* PS1 PBP layout from PCSX4ALL cdriso.cpp (GPL-2.0-or-later) and psx-spx.
 * Copyright (C) 2007 PCSX-df Team; (C) 2009 Wei Mingzhi (upstream reader).
 * H1 bounded parser, compact index and separate data/CDDA block caches.
 * GPL-2.0-or-later. */
#include "pbp.h"
#include "h1_sdk.h"
#include "h1_port.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include "zlib.h"

enum {SECTOR_BYTES=2352,BLOCK_SECTORS=16,BLOCK_BYTES=SECTOR_BYTES*BLOCK_SECTORS,MAX_DISCS=8};
struct PbpIndex {uint32_t offset;uint16_t size,reserved;};
struct H1Pbp {
    FILE *file;
    PbpIndex *index;
    unsigned blocks,sectors,tag[2],inflate_ready;
    z_stream stream;
    uint8_t raw[2][BLOCK_BYTES];
    uint8_t packed[BLOCK_BYTES];
};
static unsigned le16(const uint8_t *p){return p[0]|(unsigned)p[1]<<8;}
static unsigned le32(const uint8_t *p){return le16(p)|le16(p+2)<<16;}
static bool bcd_value(unsigned b,unsigned max,unsigned *out){
    if((b&15)>9||(b>>4)>9)return false;
    *out=(b>>4)*10+(b&15);return *out<=max;
}
static bool toc_msf(const uint8_t *p,unsigned *out){
    unsigned m,s,f;if(!bcd_value(p[0],99,&m)||!bcd_value(p[1],59,&s)||!bcd_value(p[2],74,&f))return false;
    *out=(m*60+s)*75+f;return true;
}
static bool read_at(FILE *file,unsigned offset,void *dest,unsigned bytes,unsigned limit){
    return offset<=limit&&bytes<=limit-offset&&offset<=INT_MAX&&!fseek(file,(long)offset,SEEK_SET)&&fread(dest,1,bytes,file)==bytes;
}
void h1_pbp_close(H1Pbp *p){
    if(!p)return;
    if(p->inflate_ready)inflateEnd(&p->stream);
    if(p->file)fclose(p->file);
    free(p->index);free(p);
}
H1Pbp *h1_pbp_open(const char *path,unsigned selected,H1PbpInfo *info,const char **error){
    *error="Invalid or truncated PS1 PBP image.";
    memset(info,0,sizeof *info);
    H1Pbp *p=(H1Pbp*)calloc(1,sizeof *p);if(!p){*error="Not enough memory for PBP.";return 0;}
    p->tag[0]=p->tag[1]=~0u;
    p->file=fopen(path,"rb");
    if(!p->file){*error="Cannot open PBP file.";h1_pbp_close(p);return 0;}
    long length=fseek(p->file,0,SEEK_END)?-1:ftell(p->file);
    if(length<40){*error="Invalid PBP size (H1 supports files below 2 GiB).";h1_pbp_close(p);return 0;}
    unsigned limit=(unsigned)length,psar,base,data_offset,offsets[MAX_DISCS]={0},disc_limit;
    uint8_t header[40],sig[16],toc[102*10];unsigned discs=1,first,last,raw_sectors;
    if(!read_at(p->file,0,header,sizeof header,limit)||memcmp(header,"\0PBP",4))goto fail;
    psar=le32(header+36);
    if(psar<sizeof header||!read_at(p->file,psar,sig,sizeof sig,limit))goto fail;
    offsets[0]=psar;
    if(!memcmp(sig,"PSTITLEIMG",10)){
        uint8_t table[MAX_DISCS*4];
        if(limit-psar<0x220||!read_at(p->file,psar+0x200,table,sizeof table,limit))goto fail;
        if(!memcmp(table,"\0PGD",4))goto encrypted;
        discs=0;
        for(unsigned i=0;i<MAX_DISCS;++i){
            unsigned offset=le32(table+i*4);
            if(!offset){for(unsigned j=i+1;j<MAX_DISCS;++j)if(le32(table+j*4))goto fail;break;}
            if(offset<0x220||offset>limit-psar||limit-psar-offset<0x100000)goto fail;
            offsets[discs]=psar+offset;
            if(discs&&offsets[discs]<=offsets[discs-1])goto fail;
            ++discs;
        }
        if(!discs)goto fail;
    }
    if(selected>=discs){*error="PBP disc number is out of range.";goto fail;}
    base=offsets[selected];disc_limit=selected+1<discs?offsets[selected+1]:limit;
    if(base>disc_limit||disc_limit-base<0x100000||!read_at(p->file,base,sig,12,disc_limit))goto fail;
    if(memcmp(sig,"PSISOIMG0000",12)){*error="This PBP does not contain a supported PS1 disc.";goto fail;}
    if(!read_at(p->file,base+0x400,sig,4,disc_limit))goto fail;
    if(!memcmp(sig,"\0PGD",4))goto encrypted;
    if(!read_at(p->file,base+0x800,toc,sizeof toc,disc_limit))goto fail;
    if(toc[2]!=0xa0||toc[12]!=0xa1||toc[22]!=0xa2||
       !bcd_value(toc[7],99,&first)||first!=1||!bcd_value(toc[17],99,&last)||!last||
       !toc_msf(toc+27,&raw_sectors)||!raw_sectors)goto fail;
    info->discs=discs;info->selected=selected;info->tracks=last;info->sectors=raw_sectors+150;
    for(unsigned i=1;i<=last;++i){
        const uint8_t *t=toc+(i+2)*10;unsigned number,start,pregap;
        if(!bcd_value(t[2],99,&number)||number!=i||!toc_msf(t+7,&start)||!toc_msf(t+3,&pregap))goto fail;
        H1PbpTrack &track=info->track[i];track.audio=(t[0]&0x40)==0;
        if(i==1){if(track.audio||start!=150)goto fail;track.first=150;}
        else {if(pregap>start||pregap<info->track[i-1].start)goto fail;track.first=pregap;info->track[i-1].end=pregap;}
        if(start>=info->sectors)goto fail;
        track.start=start;track.end=info->sectors;
    }
    for(unsigned i=1;i<=last;++i)if(info->track[i].start>=info->track[i].end)goto fail;
    // The first 150-sector lead-in is absent from the file. Audio pregaps
    // after track 1 are stored, and share the same physical sector mapping.
    p->sectors=raw_sectors;p->blocks=(raw_sectors+15)/16;
    if(!read_at(p->file,base+0xbfc,sig,4,disc_limit))goto fail;
    data_offset=le32(sig);if(!data_offset)data_offset=0x100000; // older popstation writers
    if(data_offset<0x4000||data_offset>disc_limit-base||p->blocks>(data_offset-0x4000)/32)goto fail;
    p->index=(PbpIndex*)malloc(p->blocks*sizeof(PbpIndex));
    if(!p->index){*error="Not enough memory for PBP index.";goto fail;}
    for(unsigned block=0;block<p->blocks;){
        unsigned count=p->blocks-block;if(count>128)count=128;
        if(!read_at(p->file,base+0x4000+block*32,p->packed,count*32,disc_limit))goto fail;
        for(unsigned j=0;j<count;++j){
            const uint8_t *entry=p->packed+j*32;unsigned offset=le32(entry),size=le16(entry+4);
            if(!size||size>BLOCK_BYTES||offset>disc_limit-base-data_offset||size>disc_limit-base-data_offset-offset)goto fail;
            p->index[block+j].offset=base+data_offset+offset;p->index[block+j].size=(uint16_t)size;
            if(block+j&&p->index[block+j].offset<p->index[block+j-1].offset+p->index[block+j-1].size)goto fail;
        }
        block+=count;
    }
    *error=0;return p;
encrypted:
    *error="Encrypted PBP is not supported. Use an unencrypted PS1 PBP.";
fail:
    h1_pbp_close(p);memset(info,0,sizeof *info);return 0;
}
int h1_pbp_read(H1Pbp *p,unsigned sector,uint8_t *output,bool audio){
    if(!p||sector>=p->sectors)return -1;
    unsigned block=sector/16,slot=audio?1:0;
    for(unsigned i=0;i<2;++i)if(p->tag[i]==block){memcpy(output,p->raw[i]+(sector%16)*SECTOR_BYTES,SECTOR_BYTES);++h1_ps1_stats.disc_hits;return SECTOR_BYTES;}
    p->tag[slot]=~0u;
    unsigned tick=h1_raw_tick_80hz(),size=p->index[block].size;
    ++h1_ps1_stats.disc_reads;
    bool ok=!fseek(p->file,(long)p->index[block].offset,SEEK_SET)&&fread(p->packed,1,size,p->file)==size;
    if(ok&&size==BLOCK_BYTES)memcpy(p->raw[slot],p->packed,BLOCK_BYTES);
    else if(ok){
        if(!p->inflate_ready){ok=inflateInit2(&p->stream,-15)==Z_OK;if(ok)p->inflate_ready=1;}
        else ok=inflateReset(&p->stream)==Z_OK;
        if(ok){
            p->stream.next_in=p->packed;p->stream.avail_in=size;p->stream.next_out=p->raw[slot];p->stream.avail_out=BLOCK_BYTES;
            ok=inflate(&p->stream,Z_FINISH)==Z_STREAM_END&&p->stream.total_out==BLOCK_BYTES&&!p->stream.avail_in;
        }
    }
    h1_ps1_stats.disc_ticks+=h1_raw_tick_80hz()-tick;
    if(!ok){h1_ps1_log("PBP_BLOCK_ERROR block=%u size=%u",block,size);return -1;}
    p->tag[slot]=block;memcpy(output,p->raw[slot]+(sector%16)*SECTOR_BYTES,SECTOR_BYTES);return SECTOR_BYTES;
}
