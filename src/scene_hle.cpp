/* Exact event-bounded native polygon packet loops. GPL-2.0-or-later.
 * Recognize executed code, preserve original GTE and guest time. No game PC,
 * mesh, ordering table, movie or output pixels are baked into the algorithm. */
#include "scene_hle.h"
#include "r3000a.h"
#include "psxmem.h"
#include "gte.h"
extern uint32_t cycle_multiplier;
extern "C" {volatile uint32_t h1_scene_hle_stats[12] __attribute__((used,externally_visible));}
struct Token {uint32_t pc,words[61];unsigned count;bool quad,full;};
static Token tokens[64];
static unsigned token_count;
static uint32_t *memory(unsigned address,unsigned bytes) {
    if(address&3u)return 0;
    unsigned seg=address&0xe0000000u,physical=address&0x1fffffffu;
    if(seg!=0 && seg!=0x80000000u && seg!=0xa0000000u)return 0;
    if(physical<0x800000u && (physical&0x1fffffu)+bytes<=0x200000u && psxM)
        return (uint32_t*)(psxM+(physical&0x1fffffu));
    if(physical>=0x1f800000u && physical<=0x1f800400u-bytes && bytes<=1024u && psxH)
        return (uint32_t*)(psxH+(physical&1023u));
    return 0;
}
static bool overlap(const void *a,unsigned n,const void *b,unsigned m) {
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<y+m && y<x+n;
}
static unsigned cycles(unsigned n){return (n*cycle_multiplier)>>8;}
static bool suffix_matches(const Token &t) {
    const uint32_t tail[12]={0x8fbe0068,0x8fb70064,0x8fb60060,0x8fb5005c,
        0x8fb40058,0x8fb30054,0x8fb20050,0x8fb1004c,0x8fb00048,0x27bd0070,0x03e00008,0};
    const uint32_t *p=memory(t.pc+(t.quad?244u:476u),48);if(!p)return false;
    uint32_t diff=0;for(unsigned i=0;i<12;++i)diff|=p[i]^tail[i];
    if(!t.quad) {
        p=memory(t.pc+216u,12);if(!p)return false;
        diff|=(p[0]^0x001e8e02u)|(p[1]^0x1220003fu)|(p[2]^0x00003821u);
    }
    return diff==0;
}
struct Window {uint32_t *data;unsigned bytes;};
static Window window(unsigned address,unsigned cap) {
    if(!memory(address,4))return {0,0};
    unsigned p=address&0x1fffffffu;
    unsigned left=p<0x800000u?0x200000u-(p&0x1fffffu):0x400u-(p&1023u);
    if(left>cap)left=cap;return {memory(address,4),left};
}
static bool unchanged(const Token &t) {
    const uint32_t *p=memory(t.pc,t.count*4u);if(!p)return false;
    uint32_t diff=0;for(unsigned i=0;i<t.count;++i)diff|=p[i]^t.words[i];
    return !diff && (!t.full||suffix_matches(t));
}
extern "C" int h1_ps1_scene_hle_admit(unsigned pc) {
    const uint32_t *p=memory(pc,244);if(!p)return 0;
    bool quad=p[0]==0x8d030000u && p[1]==0 && p[2]==0x306200ffu;
    bool tri=p[0]==0 && p[1]==0x31c200ffu && p[2]==0x000210c0u;
    if(!quad&&!tri)return 0;
    for(unsigned i=0;i<token_count;++i)if(tokens[i].pc==pc&&unchanged(tokens[i]))return i+1;
    unsigned count=quad?61u:54u;uint32_t a=2166136261u,b=0;
    for(unsigned i=0;i<count;++i) {
        uint32_t w=p[i];
        if(w>>26==2) {
            unsigned target=((pc+i*4u+4u)&0xf0000000u)|((w&0x3ffffffu)<<2);
            if(target!=pc+(quad?232u:204u))return 0;
            w=(w&0xfc000000u)|((target-pc)>>2);
        }
        a=(a^w)*16777619u;b=b*33u+w;
    }
    if(a!=(quad?0xf88cb477u:0x2edf5a36u)||b!=(quad?0x18f6a09eu:0xb9d733bbu)||token_count==64)return 0;
    Token &t=tokens[token_count++];t.pc=pc;t.count=count;t.quad=quad;
    for(unsigned i=0;i<count;++i)t.words[i]=p[i];
    t.full=suffix_matches(t);
    if(t.full)++h1_scene_hle_stats[8];
    h1_scene_hle_stats[4]=token_count;return token_count;
}
template<bool quad> static int execute_loop(unsigned pc,const Token &t) {
    const unsigned stride=quad?36u:28u,step=quad?20u:16u,required=quad?4u:20u;
    if(!psxRegs.writeok)return 0;
    uint32_t *r=psxRegs.GPR.r;unsigned n=0,current=psxRegs.cycle,end=psxRegs.io_cycle_counter;
    const uint32_t *code=memory(pc,t.count*4u);
    const uint32_t *tail=t.full?memory(pc+(quad?244u:476u),48):0;
    const uint32_t *setup=t.full&&!quad?memory(pc+216u,12):0;
    Window inputs=window(r[8],128u*step+4u),packets=window(r[6],128u*stride),vertices=window(r[16],2048);
    unsigned groups=128u;
    if(!inputs.data||inputs.bytes<required||!packets.data||vertices.bytes<8u||
       r[24]!=r[6]+(quad?32u:24u))return 0;
    if(groups>packets.bytes/stride)groups=packets.bytes/stride;
    unsigned available=(inputs.bytes-required)/step+1u;
    if(groups>available)groups=available;
    if(!groups)return 0;
    unsigned packet_bytes=groups*stride,input_bytes=(groups-1u)*step+required;
    if(overlap(packets.data,packet_bytes,code,t.count*4u)||
       (tail&&overlap(packets.data,packet_bytes,tail,48))||
       (setup&&overlap(packets.data,packet_bytes,setup,12))||
       overlap(packets.data,packet_bytes,inputs.data,input_bytes)||
       overlap(packets.data,packet_bytes,vertices.data,vertices.bytes))return 0;
    unsigned first_packet=r[6],ordering_min=0x200000u,ordering_max=0,return_pc=pc;
    for(;n<groups;++n) {
        bool last=r[7]+1u>=r[17],finish=last&&t.full&&(quad||!(r[30]>>24));
        if(last&&!finish)break;
        const uint32_t *frame=finish?memory(r[29]+72u,36):0;
        if(finish&&!frame)break;
        unsigned reserve=finish?160u:128u;
        if(end<=current || cycles(reserve)==0 || cycles(reserve)>=end-current){++h1_scene_hle_stats[3];break;}
        uint32_t *input=inputs.data+n*(step/4u),*packet=packets.data+n*(stride/4u);
        uint32_t packed=quad?input[0]:r[14],offsets[4]={
            (packed&255u)<<3,(packed&0xff00u)>>5,(packed>>13)&0x7f8u,(packed>>24)<<3};
        uint32_t *v[4],addresses[4];bool safe=true;
        #pragma GCC unroll 4
        for(unsigned j=0;j<(quad?4u:3u);++j) {
            if(offsets[j]+8u>vertices.bytes){safe=false;break;}
            v[j]=vertices.data+(offsets[j]>>2);addresses[j]=r[16]+offsets[j];
        }
        if(!safe)break;
        uint32_t x=v[0][0],y=v[1][0],z=v[2][0];
        int64_t area=(int64_t)(int16_t)x*((int16_t)(y>>16)-(int16_t)(z>>16))+
            (int64_t)(int16_t)y*((int16_t)(z>>16)-(int16_t)(x>>16))+
            (int64_t)(int16_t)z*((int16_t)(x>>16)-(int16_t)(y>>16));
        bool visible=(int32_t)(uint32_t)area>0;
        uint32_t *ordering=0,ordering_address=0;
        if(visible) {
            uint32_t index;
            if(quad) {
                uint32_t sum=v[0][1]+v[1][1]+v[2][1]+v[3][1];
                if((int32_t)sum<0)sum+=15u;
                index=(uint32_t)((int32_t)sum>>4);
            } else {
                uint32_t sum=(uint16_t)v[0][1]+(uint16_t)v[1][1]+(uint16_t)v[2][1];
                int32_t mac=(int32_t)(uint32_t)((int64_t)(int16_t)psxRegs.CP2C.r[29]*sum);
                int32_t depth=mac>>12;index=depth<0?0u:depth>65535?65535u:(uint32_t)depth;
            }
            ordering_address=r[18]+(index<<2);ordering=memory(ordering_address,4);
            if(!ordering||overlap(ordering,4,packets.data,packet_bytes)||overlap(ordering,4,code,t.count*4u)||
               (tail&&overlap(ordering,4,tail,48))||(setup&&overlap(ordering,4,setup,12))||
               overlap(ordering,4,inputs.data,input_bytes)||overlap(ordering,4,vertices.data,vertices.bytes))break;
        }
        // All fallbacks precede GTE, register or guest memory mutations.
        psxRegs.CP2D.r[12]=x;psxRegs.CP2D.r[13]=y;psxRegs.CP2D.r[14]=z;gteNCLIP();
        r[7]+=1u;r[8]+=quad?20u:16u;r[20]=packet[0];
        packet[2]=x;packet[4]=y;packet[6]=z;
        r[24]+=stride;
        if(quad) {
            r[25]=addresses[0];r[11]=addresses[1];r[10]=addresses[2];r[9]=addresses[3];
            r[3]=y;r[4]=z;r[5]=v[3][0];r[14]=r[20]&r[22];
            if(visible) {
                packet[8]=r[5];r[21]=v[1][1];r[12]=ordering_address;r[13]=ordering[0];
                r[3]=r[14]|(r[13]&r[19]);packet[0]=r[3];r[4]=r[6]&r[19];
                r[3]=(r[13]&r[22])|r[4];ordering[0]=r[3];
            } else packet[0]=r[14];
        } else {
            r[11]=addresses[0];r[10]=addresses[1];r[5]=addresses[2];r[3]=y;r[4]=z;
            if(visible) {
                psxRegs.CP2D.r[17]=v[0][1];psxRegs.CP2D.r[18]=v[1][1];psxRegs.CP2D.r[19]=v[2][1];
                gteAVSZ3();
                r[21]=r[6]&r[19];r[12]=ordering_address;r[4]=ordering[0];
                r[3]=(r[20]&r[22])|(r[4]&r[19]);packet[0]=r[3];
                ordering[0]=(r[4]&r[22])|r[21];
            } else packet[0]=r[20]&r[22];
            r[14]=input[4];
        }
        r[2]=r[7]<r[17];r[6]+=stride;
        unsigned suffix=finish?(quad?12u:3u):0;
        current+=cycles(quad?33u:28u)+(visible?cycles((quad?26u:22u)+suffix):cycles(quad?2u:4u)+cycles(3u+suffix));
        if(ordering) {
            unsigned off=ordering_address&0x1ffffcu;
            if(off<ordering_min)ordering_min=off;
            if(off>ordering_max)ordering_max=off;
        }
        ++h1_scene_hle_stats[quad?6:5];h1_scene_hle_stats[7]+=visible?(quad?6u:5u):4u;
        if(finish) {
            ++h1_scene_hle_stats[9];++h1_scene_hle_stats[quad?11:10];
            if(!quad){r[17]=r[30]>>24;r[7]=0;current+=cycles(12);}
            for(unsigned j=0;j<8;++j)r[16+j]=frame[j];
            r[30]=frame[8];r[29]+=112u;return_pc=r[31];++n;break;
        }
        if(!r[2]){++n;break;}
    }
    if(!n){++h1_scene_hle_stats[2];return 0;}
    psxCpu->Clear(first_packet,n*(stride/4u));
    if(ordering_min!=0x200000u)psxCpu->Clear(ordering_min,(ordering_max-ordering_min)/4u+1u);
    psxRegs.pc=return_pc;psxRegs.cycle=current;
    ++h1_scene_hle_stats[0];h1_scene_hle_stats[1]+=n;return 1;
}
extern "C" int h1_ps1_scene_hle_execute(unsigned pc,unsigned token) {
    if(!token||token>token_count||tokens[token-1].pc!=pc||!unchanged(tokens[token-1])) {
        if(token&&token<=token_count) {
            const Token &t=tokens[token-1];psxCpu->Clear(t.pc,t.count);
            if(t.full){psxCpu->Clear(t.pc+(t.quad?244u:476u),12);if(!t.quad)psxCpu->Clear(t.pc+216u,3);}
        }else psxCpu->Clear(pc,61);
        psxRegs.pc=pc;return 1;
    }
    const Token &t=tokens[token-1];return t.quad?execute_loop<true>(pc,t):execute_loop<false>(pc,t);
}
