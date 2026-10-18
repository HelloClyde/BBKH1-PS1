/* Exact constant-V 4bpp span. Included after gpu_unai_t. GPL-2.0-or-later. */
#ifndef H1_PS1_RASTER_POLY4_H
#define H1_PS1_RASTER_POLY4_H
static inline void h1_ps1_poly4_horizontal(const gpu_unai_t &g,u16 *dst,u32 count){
    u32 u=g.u&g.u_msk,mask=g.u_msk;
    const u8 *row=(const u8*)g.TBA+(((g.v&g.v_msk)<<1)&0x7f800u);
    const u16 *clut=g.CBA;const u32 step=(u32)g.u_inc;
    // Preserve fetch/store order even when framebuffer aliases the texture or
    // CLUT. Only the invariant row calculation is hoisted; UV precision stays
    // at UNAI's full 22.10 bits and transparent texels leave output untouched.
    while(count>=2){
        u32 color=clut[(row[u>>11]>>((u>>8)&4u))&15u];
        if(color)*dst=(u16)color;
        ++dst;u=(u+step)&mask;
        color=clut[(row[u>>11]>>((u>>8)&4u))&15u];
        if(color)*dst=(u16)color;
        ++dst;u=(u+step)&mask;count-=2;
    }
    if(count){u32 color=clut[(row[u>>11]>>((u>>8)&4u))&15u];if(color)*dst=(u16)color;}
}
#endif
