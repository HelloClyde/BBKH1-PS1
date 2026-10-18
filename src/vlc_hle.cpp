/* Native SDK VLC common AC path. GPL-2.0-or-later.
 * Exact guest lookup tables, bit refill, RLE output and register effects.
 * Recognized complete coefficient/DC flow includes secondary and escape paths.
 * Both recognition and event-bounded batches are independent of game PCs.
 */
#include "vlc_hle.h"
#include "r3000a.h"
#include "psxmem.h"
#ifdef H1_MOVIE_HLE
#define h1_ps1_vlc_hle_admit h1_ps1_vlc_core_admit
#define h1_ps1_vlc_hle_execute h1_ps1_vlc_core_execute
extern "C" volatile uint32_t h1_movie_hle_stats[16];
#endif
extern uint32_t cycle_multiplier;
extern "C" { volatile uint32_t h1_vlc_hle_stats[2] __attribute__((used,externally_visible)); }
extern "C" { volatile uint32_t h1_vlc_full_stats[2] __attribute__((used,externally_visible)); }
struct VlcToken {uint32_t pc,words[137];bool full;};
static VlcToken tokens[32];
static unsigned token_count;
static uint8_t *ram(unsigned address,unsigned count,unsigned align){
    unsigned seg=address&0xe0000000u,off=address&0x1fffffu;
    if((seg!=0&&seg!=0x80000000u&&seg!=0xa0000000u)||(address&(align-1u))||
       (address&0x1fffffffu)>=0x800000u||off+count>0x200000u||!psxM)return 0;
    return (uint8_t*)psxM+off;
}
static bool unchanged(const VlcToken &t){
    unsigned size=t.full?137u:57u;
    const uint32_t *p=(const uint32_t*)ram(t.pc-(t.full?284u:0u),size*4u,4);if(!p)return false;
    unsigned diff=0;
    #pragma GCC unroll 8
    for(unsigned i=0;i<size;++i)diff|=p[i]^t.words[i];return diff==0;
}
static bool full_entry(unsigned offset){
    switch(offset){
    case 0x000:case 0x068:case 0x088:case 0x0a8:case 0x0b0:case 0x0b4:
    case 0x0d8:case 0x108:case 0x110:case 0x11c:case 0x15c:case 0x178:
    case 0x17c:case 0x1a0:case 0x200:return true;
    default:return false;
    }
}
extern "C" int h1_ps1_vlc_hle_admit(unsigned pc){
    for(unsigned i=0;i<token_count;++i)
        if(tokens[i].full&&full_entry(pc-(tokens[i].pc-284u))&&unchanged(tokens[i]))return i+1;
    const uint32_t *p=(const uint32_t*)ram(pc,228,4);
    if(!p||p[0]!=0x000244c2u||p[1]!=0x000840c0u||p[2]!=0x01064020u||p[3]!=0x8d090000u)return 0;
    for(unsigned i=0;i<token_count;++i)if(tokens[i].pc==pc&&unchanged(tokens[i]))return i+1;
    // Two independent word fingerprints identify this SDK instruction path;
    // an immutable exact copy is rechecked before every native batch.
    uint32_t a=2166136261u,b=0;
    for(unsigned i=0;i<57;++i){a=(a^p[i])*16777619u;b=b*33u+p[i];}
    if(a!=0x3b4565c9u||b!=0xe3b5e040u||token_count==32)return 0;
    VlcToken &t=tokens[token_count++];t.pc=pc;
    t.full=false;
    const uint32_t *q=(const uint32_t*)ram(pc-284u,548,4);
    if(q){
        a=2166136261u;b=0;
        for(unsigned i=0;i<137;++i){a=(a^q[i])*16777619u;b=b*33u+q[i];}
        t.full=a==0x5c5e8386u&&b==0xf73610d3u;
    }
    for(unsigned i=0;i<(t.full?137u:57u);++i)t.words[i]=t.full?q[i]:p[i];return token_count;
}
static unsigned cycles(unsigned n){return (n*cycle_multiplier)>>8;}
static bool special(unsigned value){return value==0x7c1fu||value==0xfe00u;}
static bool overlaps(unsigned a,unsigned n,unsigned b,unsigned m){
    a&=0x1fffffu;b&=0x1fffffu;return a<b+m&&b<a+n;
}
// Direct native control flow for the recognized SDK decoder. Yield only at
// original taken-branch boundaries, retaining the JIT's per-block rounding
// (including its conditional-move conversion of short forward ALU branches).
// Tables stay in guest RAM. No movie, game identity or table values are baked in.
#ifdef H1_MOVIE_HLE
static int execute_full(unsigned pc,const VlcToken &token,unsigned prelude=0){
    const unsigned input_bytes=4096,output_bytes=8192,block_limit=4096,reserve_instructions=42;
#elif defined(H1_VLC_BATCH)
static int execute_full(unsigned pc,const VlcToken &token){
    const unsigned input_bytes=4096,output_bytes=8192,block_limit=4096,reserve_instructions=42;
#else
static int execute_full(unsigned pc,const VlcToken &token){
    const unsigned input_bytes=512,output_bytes=1024,block_limit=512,reserve_instructions=96;
#endif
#ifdef H1_MOVIE_HLE
    // The fixture proves a maximum 42-instruction linear span through every
    // recognized entry before an original unconditional branch boundary.
    // Reject short budgets before resolving the large data windows.
    if(!prelude&&(psxRegs.io_cycle_counter<=psxRegs.cycle||
       cycles(reserve_instructions)>=psxRegs.io_cycle_counter-psxRegs.cycle)){
        ++h1_movie_hle_stats[6];++h1_movie_hle_stats[13];return 0;
    }
#elif defined(H1_VLC_BATCH)
    if(psxRegs.io_cycle_counter<=psxRegs.cycle||
       cycles(reserve_instructions)>=psxRegs.io_cycle_counter-psxRegs.cycle)return 0;
#endif
    uint32_t *r=psxRegs.GPR.r;
    const uint8_t *tables=ram(r[6]-2048u,67584,4);
    const uint32_t *secondary=(const uint32_t*)ram(r[7],2048,4);
    const uint16_t *input=(const uint16_t*)ram(r[4],input_bytes,2);
    uint16_t *output=(uint16_t*)ram(r[5],output_bytes,2);
    unsigned base=token.pc-284u;
    if(!tables||!secondary||!input||!output||r[3]>15u||
       overlaps(r[5],output_bytes,r[4],input_bytes)||overlaps(r[5],output_bytes,r[6]-2048u,67584)||
       overlaps(r[5],output_bytes,r[7],2048)||overlaps(r[5],output_bytes,base,548))return 0;
    const uint32_t *primary=(const uint32_t*)(tables+2048);
    uint32_t at=r[1],window=r[2],position=r[3],t0=r[8],t1=r[9],t2=r[10],t3=r[11];
    uint32_t dc=r[13],pred1=r[15],pred2=r[24],pred3=r[25];
    unsigned i=0,o=0,current=psxRegs.cycle,end=psxRegs.io_cycle_counter;
#ifdef H1_MOVIE_HLE
    unsigned pending=prelude,blocks=0,next=pc-base,writes=0,dirty=0;bool decision;
#else
    unsigned pending=0,blocks=0,next=pc-base,writes=0,dirty=0;bool decision;
#endif
    // A block can fall through several forward conditionals. The selected
    // conservative reserve covers every path here. Windows include a block's
    // maximum four writes and two input halfwords before the next yield point.
    // Avoid calling hardware callbacks inside the native decoder.
#define RUN(offset) do { if(!pending){next=(offset); \
    if(blocks>=block_limit||i>input_bytes/2u-4u||o>output_bytes/2u-8u||end<=current||cycles(reserve_instructions)>=end-current)goto done;} } while(0)
#define STEP(n) do { pending+=(n); } while(0)
#define TAKE(label) do {current+=cycles(pending);pending=0;++blocks;goto label;} while(0)
#define STORE(value) do {output[o]=(uint16_t)(value);dirty=o+1u;++writes;} while(0)
    switch(next){
    case 0x000:goto dc_start;case 0x068:goto dc_position;case 0x088:goto dc_predict;
    case 0x0a8:goto dc_pred2;case 0x0b0:goto dc_pred3;case 0x0b4:goto dc_pack;
    case 0x0d8:goto dc_raw;case 0x108:goto dc_raw_store;case 0x110:goto limit;
    case 0x11c:goto ac;case 0x15c:goto secondary_lookup;case 0x178:goto primary_extra;
    case 0x17c:goto bits;case 0x1a0:goto coefficients;case 0x200:goto escape;
    default:return 0;
    }
ac:
    RUN(0x11c);
    // The common AC group has no intermediate externally visible event when
    // its complete cost fits the remaining budget. Fuse its native state
    // changes instead of passing through three guest-branch checkpoints.
    // Keep the detailed paths below for DC, escape, secondary and fractional
    // cycle multipliers. Both end at an original branch back to this head.
    if(!pending&&cycle_multiplier==512u){
        unsigned index=(window>>19)*2u;
        uint32_t word=primary[index],extra=primary[index+1u];
        unsigned bits_count=word&255u,first=word>>16,second=extra&65535u,third=extra>>16;
        if(word&&bits_count&&bits_count<=16u&&!special(first)&&
           (!extra||!special(second))&&(!third||!special(third))){
            unsigned pos=position+bits_count;bool refill=pos&16u;
            unsigned tail=extra?(third?24u:17u):8u;
            unsigned cost=(7u+6u+tail+(refill?4u:0u))*2u;
            if(cost>=end-current)goto done;
            window<<=bits_count;position=pos&15u;t0=r[6]+index*4u;
            if(refill){t0=(uint32_t)input[i++]<<position;window|=t0;}
            STORE(first);++o;
            if(extra){STORE(second);++o;t2=third;}
            if(third){STORE(third);++o;}
            at=(third?third:extra?second:first)^0xfe00u;t1=first;t3=extra;
            current+=cost;blocks+=refill?2u:3u;goto ac;
        }
    }
    t0=r[6]+((window>>19)<<3);t1=primary[(window>>19)*2u];at=t1&255u;STEP(7);
    if(t1)TAKE(primary_extra);
    window<<=8;position+=8;at=position&16u;position&=15u;STEP(5);
    if(!at)TAKE(secondary_lookup);
    t0=(uint32_t)input[i++]<<position;window|=t0;STEP(4);
secondary_lookup:
    RUN(0x15c);
    t0=r[7]+((window>>23)<<2);t1=secondary[window>>23];t3=0;at=t1&255u;STEP(7);
    TAKE(bits);
primary_extra:
    RUN(0x178);if(t0-r[6]>=65536u||((t0-r[6])&7u))goto done;
    t3=primary[((t0-r[6])>>2)+1u];STEP(1);
bits:
    RUN(0x17c);window<<=(at&31u);position+=at;at=position&16u;position&=15u;STEP(5);
    if(!at)TAKE(coefficients);
    t0=(uint32_t)input[i++]<<position;window|=t0;STEP(4);
coefficients:
    RUN(0x1a0);t1>>=16;at=t1^0x7c1fu;decision=!at;at=t1^0xfe00u;STEP(4);
    if(decision)TAKE(escape);
    decision=!at;STORE(t1);STEP(2);if(decision)TAKE(dc_start);
    decision=!t3;++o;STEP(2);if(decision)TAKE(ac);
    t2=t3&65535u;at=t2^0x7c1fu;decision=!at;at=t2^0xfe00u;STEP(4);
    if(decision)TAKE(escape);
    decision=!at;STORE(t2);STEP(2);if(decision)TAKE(dc_start);
    t2=t3>>16;decision=!t2;++o;STEP(3);if(decision)TAKE(ac);
    at=t2^0x7c1fu;decision=!at;at=t2^0xfe00u;STEP(3);if(decision)TAKE(escape);
    decision=!at;STORE(t2);STEP(2);if(decision)TAKE(dc_start);
    ++o;STEP(2);TAKE(ac);
escape:
    RUN(0x200);t0=window>>16;STORE(t0);++o;
    t0=input[i++];window<<=16;t0<<=position;window|=t0;STEP(9);TAKE(ac);
dc_start:
    RUN(0x000);t0=window>>22;STEP(2);if(!dc)TAKE(dc_raw);
    at=t0^0x3ffu;++o;STEP(3);if(!at)TAKE(finished);
    decision=(int32_t)(dc-3u)<0;at=r[6]-1024u;if(!decision)at-=1024u;STEP(4);
    t0=at+((window>>24)<<2);
    {const uint16_t *entry=(const uint16_t*)(tables+(t0-(r[6]-2048u)));
     t1=entry[0];t2=entry[1];}
    t0=0;window<<=(t1&31u);STEP(8);if(!t2)TAKE(dc_position);
    at=32u-t2;t0=window>>(at&31u);decision=(int32_t)window<0;window<<=(t2&31u);
    if(!decision){t3=0xffffffffu>>(at&31u);t0-=t3;}
    position+=t2;STEP(9);
dc_position:
    RUN(0x068);position+=t1;at=position&16u;position&=15u;STEP(4);
    if(!at)TAKE(dc_predict);
    t1=(uint32_t)input[i++]<<position;window|=t1;STEP(4);
dc_predict:
    RUN(0x088);at=dc-2u;t1=pred3+t0;STEP(3);if((int32_t)at>0)TAKE(dc_pred3);
    decision=!at;t1=pred2+t0;STEP(2);if(decision)TAKE(dc_pred2);
    t1=pred1+t0;pred1+=t0;STEP(3);TAKE(dc_pack);
dc_pred2:
    RUN(0x0a8);pred2+=t0;STEP(2);TAKE(dc_pack);
dc_pred3:
    RUN(0x0b0);pred3+=t0;STEP(1);
dc_pack:
    RUN(0x0b4);t1=((t1<<2)&0x3ffu)|r[12];++dc;at=dc-7u;
    STORE(t1);STEP(7);if(at)TAKE(limit);
    dc-=6;STEP(2);TAKE(limit);
dc_raw:
    RUN(0x0d8);at=t0^0x1ffu;++o;STEP(3);if(!at)TAKE(finished);
    window<<=10;position+=10;at=position&16u;position&=15u;STEP(5);
    if(!at)TAKE(dc_raw_store);
    t1=(uint32_t)input[i++]<<position;window|=t1;STEP(4);
dc_raw_store:
    RUN(0x108);t0=r[12]|t0;STORE(t0);STEP(2);
limit:
    RUN(0x110);at=(r[5]+o*2u)-r[14];decision=(int32_t)at>=0;++o;STEP(3);
    if(decision)TAKE(suspended);
    goto ac;
finished:
    next=0x224;goto done;
suspended:
    next=0x258;
done:
#ifdef H1_MOVIE_HLE
    ++h1_movie_hle_stats[6];
    if(end<=current||cycles(reserve_instructions)>=end-current)++h1_movie_hle_stats[13];
    if(blocks>=block_limit)++h1_movie_hle_stats[14];
    if(i>input_bytes/2u-4u||o>output_bytes/2u-8u)++h1_movie_hle_stats[15];
#endif
    if(!blocks)return 0;
    r[1]=at;r[2]=window;r[3]=position;r[4]+=i*2u;r[5]+=o*2u;
    r[8]=t0;r[9]=t1;r[10]=t2;r[11]=t3;r[13]=dc;r[15]=pred1;r[24]=pred2;r[25]=pred3;
    psxRegs.cycle=current;psxRegs.pc=base+next;
    // The last store can be an EOB/DC at the current, unadvanced pointer.
    unsigned aligned=(r[5]-o*2u)&~3u;
    if(dirty)psxCpu->Clear(aligned,(((r[5]-o*2u)&3u)+dirty*2u+3u)/4u);
    ++h1_vlc_hle_stats[0];h1_vlc_hle_stats[1]+=writes;
    ++h1_vlc_full_stats[0];h1_vlc_full_stats[1]+=blocks;return 1;
#undef RUN
#undef STEP
#undef TAKE
#undef STORE
}
#ifdef H1_MOVIE_HLE
extern "C" int h1_ps1_vlc_movie_body(unsigned pc,unsigned token,unsigned prelude){
    if(!token||token>token_count||!tokens[token-1].full)return 0;
    return execute_full(pc,tokens[token-1],prelude);
}
#endif
extern "C" int h1_ps1_vlc_hle_execute(unsigned pc,unsigned token){
    if(!token||token>token_count||
       (tokens[token-1].pc!=pc&&(!tokens[token-1].full||!full_entry(pc-(tokens[token-1].pc-284u))))||
       !unchanged(tokens[token-1])){
        if(token&&token<=token_count&&tokens[token-1].full)psxCpu->Clear(tokens[token-1].pc-284u,137);
        else psxCpu->Clear(pc,57);
        psxRegs.pc=pc;return 1;
    }
    if(!psxRegs.writeok)return 0;
    if(tokens[token-1].full)return execute_full(pc,tokens[token-1]);
    uint32_t *r=psxRegs.GPR.r;unsigned groups=0,produced=0,start=r[5];
    // Prove bounded windows once. Keep bit state in native registers while
    // preserving each group's source loads before its output stores.
    const uint32_t *table=(const uint32_t*)ram(r[6],65536,4);
    const uint16_t *input=(const uint16_t*)ram(r[4],256,2);
    uint16_t *output=(uint16_t*)ram(start,768,2);
    unsigned off=start&0x1fffffu,code=pc&0x1fffffu;
    if(!table||!input||!output||r[3]>15||(off<code+228u&&off+768u>code))return 0;
    uint32_t window=r[2],position=r[3],t0=r[8],first=r[9],third=r[10],extra=r[11],last=r[1];
    unsigned current=psxRegs.cycle,end=psxRegs.io_cycle_counter,consumed=0;
    for(;groups<128;++groups){
        if(end<=current)break;
        unsigned index=(window>>19)*2u;
        uint32_t word=table[index],entry_extra=table[index+1];unsigned bits=word&255u;
        if(!word||!bits||bits>16)break;
        unsigned entry_first=word>>16,second=entry_extra&65535u,entry_third=entry_extra>>16;
        unsigned count=entry_extra?(entry_third?3:2):1;
        if(special(entry_first)||(entry_extra&&special(second))||(entry_third&&special(entry_third)))break;
        unsigned next_position=position+bits;bool refill=next_position&16u;
        // The original JIT inlines the tail's conditional paths. Its cycle
        // rounding is per emitted block, including the refill fall-through.
        unsigned tail=entry_extra?(entry_third?24u:17u):8u;
        unsigned cost=cycles(7)+cycles(6)+cycles(tail+(refill?4u:0u));
        if(!cost||cost>=end-current)break;
        uint32_t next=window<<bits;t0=r[6]+index*4u;next_position&=15u;
        if(refill){t0=(uint32_t)input[consumed++]<<next_position;next|=t0;}
        // Read all source/table values before stores, just as the SDK path.
        output[produced]=(uint16_t)entry_first;
        if(entry_extra)output[produced+1]=(uint16_t)second;
        if(entry_third)output[produced+2]=(uint16_t)entry_third;
        last=(entry_third?entry_third:entry_extra?second:entry_first)^0xfe00u;
        window=next;position=next_position;first=entry_first;extra=entry_extra;
        if(entry_extra)third=entry_third;
        current+=cost;produced+=count;
    }
    if(!groups)return 0;
    r[1]=last;r[2]=window;r[3]=position;r[4]+=consumed*2u;r[5]+=produced*2u;
    r[8]=t0;r[9]=first;r[10]=third;r[11]=extra;psxRegs.cycle=current;
    unsigned aligned=start&~3u,words=((start&3u)+produced*2u+3u)/4u;
    psxCpu->Clear(aligned,words);
    psxRegs.pc=pc;++h1_vlc_hle_stats[0];h1_vlc_hle_stats[1]+=produced;return 1;
}
