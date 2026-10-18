/* JZ4740 TLB-backed JIT pointer tables, without Linux mmap or TLB refill.
 * GPL-2.0-or-later. Only invalid slots are borrowed; Wired stays unchanged. */
#include "fastmap.h"
#define GET(reg) ({uint32_t x;__asm__ volatile("mfc0 %0,$" #reg "\n\tnop":"=r"(x)::"memory");x;})
#define PUT(reg,x) __asm__ volatile("mtc0 %0,$" #reg "\n\tnop\n\tnop\n\tnop\n\tnop"::"r"(x):"memory")
typedef struct {uint32_t hi,lo0,lo1,mask;} entry;
typedef struct {uint32_t index,lo0,lo1,mask,hi,status;} scratch;
volatile uint32_t h1_fastmap_stats[32] __attribute__((used,externally_visible));
static h1_fastmap_api ops;
static entry saved[32],mapped[5];
static unsigned slots[5],active;
static void *ram_raw,*rom_raw;
static uintptr_t ram,rom;
static scratch lock(void) {
    scratch s;s.status=GET(12);PUT(12,s.status&~1u);
    s.index=GET(0);s.lo0=GET(2);s.lo1=GET(3);s.mask=GET(5);s.hi=GET(10);return s;
}
static void unlock(scratch s) {
    PUT(2,s.lo0);PUT(3,s.lo1);PUT(5,s.mask);PUT(10,s.hi);PUT(0,s.index);PUT(12,s.status);
}
__attribute__((noinline)) static entry read_slot(unsigned i) {
    PUT(0,i);__asm__ volatile("tlbr\n\tnop\n\tnop\n\tnop\n\tnop":::"memory");
    entry e={GET(10),GET(2),GET(3),GET(5)};return e;
}
static void write_slot(unsigned i,entry e) {
    PUT(0,i);PUT(2,e.lo0);PUT(3,e.lo1);PUT(5,e.mask);PUT(10,e.hi);
    __asm__ volatile("tlbwi\n\tnop\n\tnop\n\tnop\n\tnop":::"memory");
}
static int equal(entry a,entry b) {
    return !((a.hi^b.hi)&0xffffe0ffu) && a.lo0==b.lo0 && a.lo1==b.lo1 && a.mask==b.mask;
}
static int overlaps(entry e,uint32_t va,uint32_t mask) {
    /* Conservative even for noncanonical power-on PageMask values. Include
     * invalid tags too: a second matching tag can cause a multiple-hit fault. */
    return !((e.hi^va)&~(e.mask|mask|8191u));
}
static int owned(uintptr_t raw,size_t size,uintptr_t aligned,size_t used) {
    return raw>=0x80004000u && raw<=0x84000000u-size && aligned>=raw && aligned+used<=raw+size;
}
static void free_backing(void) {
    if(rom_raw)ops.release(rom_raw);
    if(ram_raw)ops.release(ram_raw);
    ram_raw=rom_raw=0;ram=rom=0;h1_fastmap_stats[10]=0;
}
int h1_fastmap_open(const h1_fastmap_api *api) {
    if(active)return 0;
    for(unsigned i=0;i<32;++i)h1_fastmap_stats[i]=0;
    h1_fastmap_stats[0]=0x31504d46u;h1_fastmap_stats[1]=1;
    if(!api || !api->allocate || !api->release || !api->flush){h1_fastmap_stats[3]=1;return 0;}
    ops=*api;
    if(GET(15)!=0x0ad0024fu || GET(16)!=0x80000483u || GET(6)!=0 || (GET(12)&0x1eu)) {h1_fastmap_stats[3]=2;return 0;}
    uint32_t config1;__asm__ volatile("mfc0 %0,$16,1\n\tnop":"=r"(config1)::"memory");
    if(((config1>>25)&63u)!=31u){h1_fastmap_stats[3]=3;return 0;}
    unsigned found=0;uint32_t slotmask=0;int collision=0;scratch s=lock();
    for(unsigned i=0;i<32;++i) {
        saved[i]=read_slot(i);
        if(!((saved[i].lo0|saved[i].lo1)&2u) && found<5){slots[found++]=i;slotmask|=1u<<i;}
        for(unsigned j=0;j<4;++j)if(overlaps(saved[i],0x20000000u+j*0x200000u,0x1fe000u))collision=1;
        if(overlaps(saved[i],0x20c00000u,0x7e000u))collision=1;
    }
    unlock(s);h1_fastmap_stats[4]=found;h1_fastmap_stats[5]=slotmask;
    if(found!=5 || collision){h1_fastmap_stats[3]=collision?5:4;return 0;}
    ram_raw=ops.allocate(0x2fffffu);rom_raw=ram_raw?ops.allocate(0xbffffu):0;
    ram=((uintptr_t)ram_raw+0xfffffu)&~0xfffffu;rom=((uintptr_t)rom_raw+0x3ffffu)&~0x3ffffu;
    h1_fastmap_stats[6]=(uintptr_t)ram_raw;h1_fastmap_stats[7]=(uintptr_t)rom_raw;
    h1_fastmap_stats[8]=ram;h1_fastmap_stats[9]=rom;
    if(!ram_raw || !rom_raw || !owned((uintptr_t)ram_raw,0x2fffffu,ram,0x200000u) || !owned((uintptr_t)rom_raw,0xbffffu,rom,0x80000u)) {
        free_backing();h1_fastmap_stats[3]=6;return 0;
    }
    h1_fastmap_stats[10]=2;ops.flush((void*)ram,0x200000,3);ops.flush((void*)rom,0x80000,3);
    uint32_t p=ram&0x1fffffffu,q=rom&0x1fffffffu;
    for(unsigned j=0;j<4;++j){entry e={0x20000000u+j*0x200000u,(p>>6)|0x1fu,((p+0x100000u)>>6)|0x1fu,0x1fe000u};mapped[j]=e;}
    entry bios={0x20c00000u,(q>>6)|0x1fu,((q+0x40000u)>>6)|0x1fu,0x7e000u};mapped[4]=bios;
    s=lock();unsigned changed=0;int ok=GET(6)==0;
    for(unsigned i=0;i<32;++i)if(!equal(saved[i],read_slot(i)))ok=0;
    if(ok)for(unsigned j=0;j<5;++j){write_slot(slots[j],mapped[j]);++changed;if(!equal(mapped[j],read_slot(slots[j]))){ok=0;break;}}
    if(!ok) {
        for(unsigned j=0;j<changed;++j)write_slot(slots[j],saved[slots[j]]);
        unsigned restored=0;for(unsigned i=0;i<32;++i)if(equal(saved[i],read_slot(i)))++restored;
        unsigned own_restored=0;
        for(unsigned j=0;j<changed;++j)if(equal(saved[slots[j]],read_slot(slots[j])))++own_restored;
        h1_fastmap_stats[12]=restored;unlock(s);
        // Never free storage when a failed TLB write cannot be confirmed as
        // rolled back. Retain ownership and diagnostics for explicit recovery.
        if(own_restored!=changed){active=1;h1_fastmap_stats[2]=3;h1_fastmap_stats[3]=10;return 0;}
        free_backing();h1_fastmap_stats[3]=7;return 0;
    }
    active=1;h1_fastmap_stats[2]=1;h1_fastmap_stats[11]=5;unlock(s);return 1;
}
int h1_fastmap_close(void) {
    if(!active)return 1;
    scratch s=lock();int ok=GET(6)==0;
    for(unsigned j=0;j<5;++j)if(!equal(mapped[j],read_slot(slots[j])))ok=0;
    unlock(s);
    if(!ok){h1_fastmap_stats[3]=8;h1_fastmap_stats[2]=3;return 0;}
    /* Flush dirty virtual lines while translations still exist. Physical
     * buffers were flushed before mapping; no stale allocator alias survives. */
    for(unsigned j=0;j<4;++j)ops.flush((void*)(uintptr_t)(0x20000000u+j*0x200000u),0x200000,3);
    ops.flush((void*)0x20c00000u,0x80000,3);
    s=lock();ok=GET(6)==0;
    for(unsigned j=0;j<5;++j)if(!equal(mapped[j],read_slot(slots[j])))ok=0;
    if(!ok){unlock(s);h1_fastmap_stats[3]=8;h1_fastmap_stats[2]=3;return 0;}
    for(unsigned j=0;j<5;++j)write_slot(slots[j],saved[slots[j]]);
    unsigned restored=0;for(unsigned i=0;i<32;++i)if(equal(saved[i],read_slot(i)))++restored;
    h1_fastmap_stats[12]=restored;unlock(s);
    if(restored!=32){h1_fastmap_stats[3]=9;h1_fastmap_stats[2]=3;return 0;}
    active=0;free_backing();h1_fastmap_stats[2]=2;return 1;
}
