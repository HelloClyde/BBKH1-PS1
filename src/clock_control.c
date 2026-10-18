/* Opt-in clock experiment for the measured H1 V1.41 register configuration.
 * JZ4740 PM ch. 3.6 and 5.2; Linux ingenic CGU PLL update/lock semantics.
 * Never disable/bypass the PLL, raise voltage, or exceed the original bus,
 * SDRAM, pixel, SD or USB-host clock rates. USB/I2S/SSI stay on EXTAL.
 * Callers must stop native PCM/DMA before either transition. Runtime PLL
 * changes use PLLST=255 while settling, then restore the caller's PLLST;
 * audio clocks are gated together with the affected peripheral clocks.
 * This is a trial, not evidence of a board's long-term overclock stability.
 */
#include "clock_control.h"
enum {CPCCR,CPPCR,CLKGR,I2SCDR,LPCDR,MSCCDR,UHCCDR,SSICDR,DMCR,RTCSR,RTCOR,NREG};
static const uint32_t offsets[]={0,0x10,0x20,0x60,0x64,0x68,0x6c,0x74};
volatile uint32_t h1_clock_stats[H1_CLOCK_STATS_WORDS] __attribute__((used,externally_visible));
static uint32_t saved[NREG];
static unsigned owned;
#define CE (1u<<22)
#define STABLE (1u<<10)
#define GATED ((1u<<10)|(1u<<7)|(1u<<14)|(1u<<6)|(1u<<5))
#define REG32(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define REG16(a) (*(volatile uint16_t *)(uintptr_t)(a))
static void snapshot(uint32_t *out){
    for(unsigned n=0;n<8;++n)out[n]=REG32(0xb0000000u+offsets[n]);
    out[DMCR]=REG32(0xb3010080u);out[RTCSR]=REG16(0xb3010084u);out[RTCOR]=REG16(0xb301008cu);
}
static void record(unsigned base,const uint32_t *regs){
    for(unsigned n=0;n<NREG;++n)h1_clock_stats[base+n]=regs[n];
}
static unsigned irq_disable(void){
    unsigned before,after;
    __asm__ volatile("mfc0 %0,$12\n\tnop\n\tnop\n\tnop":"=r"(before));
    after=before&~1u;
    __asm__ volatile("mtc0 %0,$12\n\tnop\n\tnop\n\tnop\n\tsync"::"r"(after):"memory");
    return before;
}
static void irq_restore(unsigned before){
    __asm__ volatile("sync\n\tmtc0 %0,$12\n\tnop\n\tnop\n\tnop"::"r"(before):"memory");
}
static int equal(const uint32_t *a,const uint32_t *b){
    for(unsigned n=0;n<NREG;++n){
        uint32_t mask=n==CPPCR?~STABLE:n==RTCSR?~0x80u:~0u;
        if((a[n]&mask)!=(b[n]&mask))return 0;
    }
    return 1;
}
static unsigned ceil_ratio(unsigned value,unsigned mhz){return (value*mhz+335u)/336u;}
/* Keep the actual PLL transition in a preloaded, bounded leaf. No stack,
 * literal-pool or target-array accesses between the PLL store and stable bit.
 * The H1 firmware also uses cache 0x1c around its transition leaf. */
extern unsigned h1_clock_pll_change(unsigned cpccr,unsigned cppcr);
extern char h1_clock_pll_end[];
__asm__(
".pushsection .text.h1_clock_pll_change,\"ax\",@progbits\n"
".set push\n.set noreorder\n.balign 32\n"
".global h1_clock_pll_change\nh1_clock_pll_change:\n"
"lui $8,%hi(h1_clock_pll_change)\naddiu $8,$8,%lo(h1_clock_pll_change)\n"
"lui $9,%hi(h1_clock_pll_end)\naddiu $9,$9,%lo(h1_clock_pll_end)\n"
"1: cache 0x1c,0($8)\naddiu $8,$8,32\nsltu $10,$8,$9\nbnez $10,1b\nnop\n"
"sync\nlui $8,0xb000\nlui $9,0x1e\nori $9,$9,0x8480\nmove $2,$0\n"
"move $11,$5\nori $5,$5,0xff\n"
"sw $5,16($8)\nsync\n"
"2: lw $10,16($8)\nandi $10,$10,0x400\naddiu $2,$2,1\n"
"bnez $10,3f\nnop\nsltu $10,$2,$9\nbnez $10,2b\nnop\nmove $2,$0\n"
"3: sw $11,16($8)\nsw $4,0($8)\nsync\njr $31\nnop\n.balign 32\n"
".global h1_clock_pll_end\nh1_clock_pll_end:\n.set pop\n.popsection\n");
static void release_pll_cache(void){
    uintptr_t first=(uintptr_t)h1_clock_pll_change;
    for(;first<(uintptr_t)h1_clock_pll_end;first+=32u)
        __asm__ volatile("cache 0x10,0(%0)"::"r"(first):"memory");
    __asm__ volatile("sync":::"memory");
}
static int change(const uint32_t *target){
    unsigned irq=irq_disable();
    unsigned ctrl=REG32(0xb3050030u),da0=REG32(0xb3050040u),da1=REG32(0xb3050050u);
    unsigned lcd_active=ctrl&8u;
    if(lcd_active){
        REG32(0xb3050034u)=REG32(0xb3050034u)&~1u;
        REG32(0xb3050030u)=ctrl|16u;
        unsigned wait;
        for(wait=0;wait<8000000u;++wait)if(REG32(0xb3050034u)&1u)break;
        if(wait==8000000u){
            REG32(0xb3050030u)=ctrl;irq_restore(irq);return -2;
        }
    }
    uint32_t old_refresh=REG16(0xb301008cu);
    unsigned refresh=old_refresh<target[RTCOR]?old_refresh:target[RTCOR];
    REG32(0xb0000020u)=REG32(0xb0000020u)|GATED;
    /* CE=0 stages division updates for the multiplier-change sequence. */
    REG32(0xb0000000u)=REG32(0xb0000000u)&~CE;
    REG32(0xb0000000u)=target[CPCCR]&~CE;
    REG32(0xb0000064u)=target[LPCDR];REG32(0xb0000068u)=target[MSCCDR];REG32(0xb000006cu)=target[UHCCDR];
    int staged=(REG32(0xb0000000u)==(target[CPCCR]&~CE) && REG32(0xb0000064u)==target[LPCDR] &&
       REG32(0xb0000068u)==target[MSCCDR] && REG32(0xb000006cu)==target[UHCCDR]);
    /* A faster refresh is safe on either side of the transition. Do not
     * lengthen its real-time period when reducing the SDRAM clock. */
    unsigned polls=0;
    if(staged){
        REG16(0xb301008cu)=(uint16_t)refresh;REG16(0xb3010088u)=(uint16_t)(refresh-1u);
        polls=h1_clock_pll_change(target[CPCCR],target[CPPCR]&~STABLE);
        release_pll_cache();h1_clock_stats[7]+=polls;
        REG16(0xb301008cu)=(uint16_t)target[RTCOR];REG16(0xb3010088u)=(uint16_t)(target[RTCOR]-1u);
    }
    REG32(0xb0000020u)=target[CLKGR];
    if(lcd_active){
        REG32(0xb3050034u)=0;REG32(0xb3050040u)=da0;REG32(0xb3050050u)=da1;
        REG32(0xb3050030u)=ctrl;
    }
    irq_restore(irq);
    return staged?(polls!=0):-1;
}
int h1_clock_open(unsigned cpu_mhz){
    if(owned)return 0;
    for(unsigned n=0;n<H1_CLOCK_STATS_WORDS;++n)h1_clock_stats[n]=0;
    h1_clock_stats[0]=0x48434c4bu;h1_clock_stats[1]=cpu_mhz;h1_clock_stats[5]=336;h1_clock_stats[6]=cpu_mhz;
    snapshot(saved);record(8,saved);
    if((cpu_mhz!=384 && cpu_mhz!=408) ||
       saved[CPCCR]!=0x40662220u || (saved[CPPCR]&~STABLE)!=(0x1b000520u&~STABLE) ||
       !(saved[CPPCR]&STABLE) || saved[CLKGR]!=0 || saved[I2SCDR]!=4 || saved[LPCDR]!=0x24 ||
       saved[MSCCDR]!=13 || saved[UHCCDR]!=6 || saved[SSICDR]!=4 ||
       (saved[DMCR]&(3u<<24))!=(1u<<24) || (saved[RTCSR]&7u)!=3 || saved[RTCOR]<4 || saved[RTCOR]>255){
        h1_clock_stats[2]=3;h1_clock_stats[3]=1;return 0;
    }
    uint32_t target[NREG];for(unsigned n=0;n<NREG;++n)target[n]=saved[n];
    target[CPPCR]=(saved[CPPCR]&~(0x1ffu<<23))|((cpu_mhz/6u-2u)<<23);
    target[CPCCR]=(saved[CPCCR]&~0x1fffffu)|((ceil_ratio(7,cpu_mhz)-1u)<<16)|0x3330u;
    target[LPCDR]=ceil_ratio(37,cpu_mhz)-1u;
    target[MSCCDR]=ceil_ratio(14,cpu_mhz)-1u;target[UHCCDR]=ceil_ratio(7,cpu_mhz)-1u;
    target[RTCOR]=(saved[RTCOR]+1u)*cpu_mhz/448u-1u;
    record(19,target);owned=1;
    int result=change(target);uint32_t actual[NREG];snapshot(actual);record(30,actual);
    if(result<=0 || !equal(target,actual)){
        h1_clock_stats[3]=result==0?2u:4u;h1_clock_close();return 0;
    }
    h1_clock_stats[2]=1;return 1;
}
void h1_clock_observe(void){
    if(owned){uint32_t actual[NREG];snapshot(actual);record(30,actual);}
}
int h1_clock_close(void){
    if(!owned)return h1_clock_stats[2]!=4;
    uint32_t actual[NREG];snapshot(actual);record(30,actual);
    int result=change(saved);snapshot(actual);record(41,actual);
    if(result<=0 || !equal(saved,actual)){
        h1_clock_stats[2]=4;h1_clock_stats[3]|=8;return 0;
    }
    owned=0;h1_clock_stats[2]=2;return 1;
}
