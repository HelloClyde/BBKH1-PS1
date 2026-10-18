/* Exact PS1 viewport conversion directly into the native LCD buffer.
 * GPL-2.0-or-later. Same 362x272 nearest-neighbour image and byte wrapping. */
#include "present_fast.h"
#include <string.h>
#include <stddef.h>
static uint16_t cols[362],rows[272];
static unsigned oldw,oldh;
extern "C" { volatile uint32_t h1_present_fused_stats[3] __attribute__((used,externally_visible)); }
static inline uint32_t color15(unsigned c){return ((c&31u)<<19)|((c&0x3e0u)<<6)|((c&0x7c00u)>>7);}
template<unsigned Duplicate> static void row15(uint32_t *dst,const uint16_t *src,unsigned x){
    unsigned i=0;
    // Gather a short run before writing the LCD. Keep conversion in registers,
    // reduce loop branches and issue consecutive output words together.
    for(;i<360;i+=4){
        uint32_t a=color15(src[(x+cols[i])&1023u]);
        uint32_t b=color15(src[(x+cols[i+1])&1023u]);
        uint32_t c=color15(src[(x+cols[i+2])&1023u]);
        uint32_t d=color15(src[(x+cols[i+3])&1023u]);
        dst[i]=a;dst[i+1]=b;dst[i+2]=c;dst[i+3]=d;
        if(Duplicate==2){dst[i+480]=a;dst[i+481]=b;dst[i+482]=c;dst[i+483]=d;}
    }
    for(;i<362;++i){
        uint32_t c=color15(src[(x+cols[i])&1023u]);dst[i]=c;if(Duplicate==2)dst[i+480]=c;
    }
}
template<unsigned Duplicate> static void row24(uint32_t *dst,const uint16_t *src,unsigned x){
    const uint8_t *p=(const uint8_t*)src;
    unsigned i=0;
    for(;i<360;i+=4){
        unsigned oa=(x*2u+cols[i]*3u)&2047u,ob=(x*2u+cols[i+1]*3u)&2047u;
        unsigned oc=(x*2u+cols[i+2]*3u)&2047u,od=(x*2u+cols[i+3]*3u)&2047u;
        uint32_t a=((uint32_t)p[oa]<<16)|((uint32_t)p[(oa+1)&2047u]<<8)|p[(oa+2)&2047u];
        uint32_t b=((uint32_t)p[ob]<<16)|((uint32_t)p[(ob+1)&2047u]<<8)|p[(ob+2)&2047u];
        uint32_t c=((uint32_t)p[oc]<<16)|((uint32_t)p[(oc+1)&2047u]<<8)|p[(oc+2)&2047u];
        uint32_t d=((uint32_t)p[od]<<16)|((uint32_t)p[(od+1)&2047u]<<8)|p[(od+2)&2047u];
        dst[i]=a;dst[i+1]=b;dst[i+2]=c;dst[i+3]=d;
        if(Duplicate==2){dst[i+480]=a;dst[i+481]=b;dst[i+482]=c;dst[i+483]=d;}
    }
    for(;i<362;++i){
        unsigned o=(x*2u+cols[i]*3u)&2047u;
        uint32_t c=((uint32_t)p[o]<<16)|((uint32_t)p[(o+1)&2047u]<<8)|p[(o+2)&2047u];
        dst[i]=c;if(Duplicate==2)dst[i+480]=c;
    }
}
static bool overlaps(const void *a,unsigned an,const void *b,unsigned bn){
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x<y+bn && y<x+an;
}
extern "C" void h1_ps1_present_fused(uint32_t *out,const uint16_t *vram,unsigned x,unsigned y,unsigned w,unsigned h,unsigned depth24){
    if(!out||!vram||!w||w>1024||!h||h>512)return;
    if(w!=oldw||h!=oldh){
        for(unsigned i=0;i<362;++i)cols[i]=(uint16_t)(i*w/362u);
        for(unsigned i=0;i<272;++i)rows[i]=(uint16_t)(i*h/272u);
        oldw=w;oldh=h;
    }
    ++h1_present_fused_stats[0];
    uint32_t cache[362];
    // A malformed/aliasing surface must retain the original per-row source
    // snapshot and write order. Native H1 LCD and allocated PS1 VRAM differ.
    if(overlaps(out,480u*272u*4u,vram,1024u*512u*2u)){
        unsigned previous=~0u;
        for(unsigned i=0;i<272;++i){
            unsigned sy=(y+rows[i])&511u;
            if(sy!=previous){
                if(depth24)row24<1>(cache,vram+sy*1024u,x);else row15<1>(cache,vram+sy*1024u,x);
            }
            memcpy(out+i*480u+59u,cache,sizeof cache);previous=sy;
        }
        return;
    }
    for(unsigned i=0;i<272;){
        unsigned end=i+1;while(end<272 && rows[end]==rows[i])++end;
        const uint16_t *src=vram+((y+rows[i])&511u)*1024u;
        uint32_t *dst=out+i*480u+59u;unsigned duplicate=end-i;
        if(duplicate==1){if(depth24)row24<1>(dst,src,x);else row15<1>(dst,src,x);}
        else if(duplicate==2){if(depth24)row24<2>(dst,src,x);else row15<2>(dst,src,x);}
        else{
            if(depth24)row24<1>(cache,src,x);else row15<1>(cache,src,x);
            for(unsigned j=i;j<end;++j)memcpy(out+j*480u+59u,cache,sizeof cache);
        }
        ++h1_present_fused_stats[1];h1_present_fused_stats[2]+=duplicate-1;i=end;
    }
}
