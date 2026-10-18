/* Small direct LCD overlay, confined to the two 59-pixel side borders.
 * Display rate counts successful game-image copies, not panel refreshes. */
#include "hud.h"
#define G(a,b,c,d,e) (((a)<<12)|((b)<<9)|((c)<<6)|((d)<<3)|(e))
static unsigned initialized,base_tick,base_frames,base_displayed,base_hz;
static char rates[8]="--/--",frequency[5]="---M";
static unsigned glyph(char c){
    static const unsigned short digits[]={G(7,5,5,5,7),G(2,6,2,2,7),G(7,1,7,4,7),G(7,1,7,1,7),G(5,5,7,1,1),
        G(7,4,7,1,7),G(7,4,7,5,7),G(7,1,1,1,1),G(7,5,7,5,7),G(7,5,7,1,7)};
    if(c>='0'&&c<='9')return digits[c-'0'];
    switch(c){case '/':return G(1,1,2,4,4);case '-':return G(0,0,7,0,0);
    case 'F':return G(7,4,6,4,4);case 'P':return G(6,5,6,4,4);case 'S':return G(7,4,7,1,7);
    case 'C':return G(7,4,4,4,7);case 'U':return G(5,5,5,5,7);case 'M':return G(5,7,7,5,5);default:return 0;}
}
static unsigned length(const char *s){unsigned n=0;while(s[n])++n;return n;}
static unsigned width(const char *s,unsigned scale){unsigned n=length(s);return n?(n*4-1)*scale:0;}
static void text(uint32_t *lcd,unsigned x,unsigned y,const char *s,unsigned scale,uint32_t color){
    for(;*s;++s,x+=4*scale){unsigned bits=glyph(*s);
        for(unsigned row=0;row<5;++row)for(unsigned col=0;col<3;++col)
            if(bits&(1u<<(14-row*3-col)))for(unsigned dy=0;dy<scale;++dy)for(unsigned dx=0;dx<scale;++dx)
                lcd[(y+row*scale+dy)*480+x+col*scale+dx]=color;
    }
}
static char *decimal(char *s,unsigned value){
    if(value>999)value=999;
    if(value>=100)*s++=(char)('0'+value/100);
    if(value>=10)*s++=(char)('0'+value/10%10);
    *s++=(char)('0'+value%10);return s;
}
static void clock_text(void){
    unsigned cppcr=*(volatile uint32_t *)0xb0000010u,cpccr=*(volatile uint32_t *)0xb0000000u;
    static const unsigned char divs[]={1,2,3,4,6,8,12,16,24,32},ods[]={1,2,2,4};
    unsigned d=cpccr&15u,mhz=0;
    if(d<10){
        unsigned numerator=12,denominator=divs[d];
        if((cppcr&0x300u)==0x100u){numerator*=((cppcr>>23)&511u)+2;denominator*=(((cppcr>>18)&31u)+2)*ods[(cppcr>>16)&3u];}
        mhz=(numerator+denominator/2)/denominator;
    }
    if(!mhz){frequency[0]=frequency[1]=frequency[2]='-';frequency[3]='M';frequency[4]=0;return;}
    char *end=decimal(frequency,mhz);*end++='M';*end=0;
}
void h1_hud_reset(void){initialized=0;}
__attribute__((noinline,used,externally_visible))
void h1_hud_draw(uint32_t *lcd,unsigned tick,unsigned hz,unsigned frames,unsigned displayed,unsigned erased){
    if(!lcd)return;
    unsigned redraw=erased;
    if(!initialized||base_hz!=hz){
        initialized=1;base_tick=tick;base_frames=frames;base_displayed=displayed;base_hz=hz;
        rates[0]=rates[1]='-';rates[2]='/';rates[3]=rates[4]='-';rates[5]=0;clock_text();redraw=1;
    }else if(hz>=10&&hz<=2000&&(unsigned)(tick-base_tick)>=hz){
        unsigned elapsed=tick-base_tick;
        unsigned screen=(unsigned)(((uint64_t)(displayed-base_displayed)*hz+elapsed/2)/elapsed);
        unsigned logic=(unsigned)(((uint64_t)(frames-base_frames)*hz+elapsed/2)/elapsed);
        char *end=decimal(rates,screen);*end++='/';end=decimal(end,logic);*end=0;
        base_tick=tick;base_frames=frames;base_displayed=displayed;clock_text();redraw=1;
    }
    if(!redraw)return;
    for(unsigned y=0;y<24;++y)for(unsigned x=0;x<59;++x){lcd[y*480+x]=0;lcd[y*480+421+x]=0;}
    text(lcd,2,3,"FPS",1,0x00808080u);text(lcd,478-width("CPU",1),3,"CPU",1,0x00808080u);
    text(lcd,2,12,rates,2,0x00eeeeeeu);text(lcd,478-width(frequency,2),12,frequency,2,0x009fe7ffu);
}
