/* Exact span shortcuts for UNAI. GPL-2.0-or-later. */
#include "raster_fast.h"
#include <stddef.h>

extern "C" void h1_ps1_fill16(uint16_t *dst,unsigned count,unsigned color){
    if((uintptr_t)dst&2u){*dst++=(uint16_t)color;if(!--count)return;}
    uint32_t word=(color&65535u)*0x10001u;
    while(count>=8){
        uint32_t *p=(uint32_t*)dst;p[0]=word;p[1]=word;p[2]=word;p[3]=word;
        dst+=8;count-=8;
    }
    while(count>=2){*(uint32_t*)dst=word;dst+=2;count-=2;}
    if(count)*dst=(uint16_t)color;
}

extern "C" void h1_ps1_blend16(uint16_t *dst,unsigned count,unsigned color,unsigned mask_set){
    const unsigned src=color&0x7bdeu,msb=mask_set?0x8000u:0;
    if((uintptr_t)dst&2u){*dst=(uint16_t)((((*dst&0x7bdeu)+src)>>1)|msb);++dst;if(!--count)return;}
    const uint32_t packed=src*0x10001u,bits=msb*0x10001u;
    while(count>=4){
        uint32_t *p=(uint32_t*)dst;
        p[0]=(((p[0]&0x7bde7bdeu)+packed)>>1)|bits;
        p[1]=(((p[1]&0x7bde7bdeu)+packed)>>1)|bits;
        dst+=4;count-=4;
    }
    if(count>=2){uint32_t *p=(uint32_t*)dst;*p=(((*p&0x7bde7bdeu)+packed)>>1)|bits;dst+=2;count-=2;}
    if(count)*dst=(uint16_t)((((*dst&0x7bdeu)+src)>>1)|msb);
}

static bool overlaps(const void *a,unsigned an,const void *b,unsigned bn){
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    return x<y+bn && y<x+an;
}
extern "C" int h1_ps1_sprite4(uint16_t *dst,unsigned count,const uint8_t *texture,unsigned u,
                              unsigned mask,const uint16_t *clut){
    // A previous output pixel may modify the next texture/CLUT fetch. Keep
    // UNAI's sequential path for all such aliases, including transparent data.
    if(!(mask&1u) || overlaps(dst,count*2,texture,(mask>>1)+1) || overlaps(dst,count*2,clut,32))return 0;
    if(u&1u){unsigned c=clut[texture[(u&mask)>>1]>>4];if(c)*dst=(uint16_t)c;++dst;++u;--count;}
    while(count>=2){
        unsigned byte=texture[(u&mask)>>1];
        unsigned lo=clut[byte&15u],hi=clut[byte>>4];
        if(lo)dst[0]=(uint16_t)lo;
        if(hi)dst[1]=(uint16_t)hi;
        dst+=2;u+=2;count-=2;
    }
    if(count){unsigned c=clut[texture[(u&mask)>>1]&15u];if(c)*dst=(uint16_t)c;}
    return 1;
}
