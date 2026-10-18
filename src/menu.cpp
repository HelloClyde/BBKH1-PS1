/* H1 GBA-style touch pause menu, adapted for the PS1 frontend. GPL-2.0-or-later. */
#include "h1_sdk.h"
#include "h1_port.h"
#include "menu.h"
#include "settings.h"
#include "touch.h"
#include "game_input.h"
#include "audio.h"
#include "menu_font.h"
#include <stdio.h>
#include <string.h>

extern "C" { volatile uint32_t h1_ps1_menu_stats[8] __attribute__((used,externally_visible)); }
enum {ROOT,KEYS,SOUND,DISPLAY,ABOUT};
static uint32_t *canvas;
static const unsigned logical[]={4,6,7,5,14,15,13,12,10,11,8,9,3,0};
static const char *logical_names[]={"上","下","左","右","叉键","方键","圆键","三角","L1","R1","L2","R2","START","SELECT"};
static const char *key_names[]={"未设置","Q","W","E","R","T","Y","U","A","S","D","F","G","H","J","上页",
    "Z","X","C","V","B","N","下页","空格","退出","回车","左ALT","下","右ALT","I","O","P","K","L","符号","右","M","上","删除","确认","左","返回","SHIFT","FN","电源"};
static void rect(int x,int y,int w,int h,uint32_t color){
    for(int r=y;r<y+h&&r<272;++r)for(int c=x;c<x+w&&c<480;++c)if(r>=0&&c>=0)canvas[r*480+c]=color;
}
static void text(const char *s,int x,int y,uint32_t color){
    while(*s&&x<470){
        unsigned cp=(uint8_t)*s++;
        if(cp>=0xe0){cp=(cp&15)<<12;cp|=((uint8_t)*s++&63)<<6;cp|=(uint8_t)*s++&63;}
        else if(cp>=0xc0){cp=(cp&31)<<6;cp|=(uint8_t)*s++&63;}
        unsigned lo=0,hi=MENU_GLYPH_COUNT,advance=cp<128?10:20;
        while(lo<hi){unsigned mid=(lo+hi)/2;if(menu_glyphs[mid].code<cp)lo=mid+1;else hi=mid;}
        if(lo<MENU_GLYPH_COUNT&&menu_glyphs[lo].code==cp){
            advance=menu_glyphs[lo].advance;
            for(unsigned r=0;r<21;++r)for(unsigned c=0;c<18;++c)if(menu_glyphs[lo].rows[r]&(1u<<c))rect(x+c,y+r,1,1,color);
        }
        x+=advance;
    }
}
static unsigned mapped_key(unsigned bit){for(unsigned k=1;k<=42;++k)if(h1_settings.mapping[k]==bit+1)return k;return 0;}
static int count(int page){return page==ROOT?6:page==KEYS?16:page==SOUND?4:page==DISPLAY?5:1;}
static void box(int page,int i,int *x,int *y,int *w,int *h){
    if(page==ABOUT){*x=338;*y=238;*w=124;*h=28;}
    else if(page==ROOT){*x=18+(i%2)*230;*y=58+(i/2)*64;*w=214;*h=48;}
    else if(page==KEYS){*x=18+(i%2)*230;*y=i<14?50+(i/2)*26:238;*w=214;*h=i<14?24:28;}
    else{*x=38;*y=54+i*(page==SOUND?38:36);*w=404;*h=32;}
}
static int hit(int page,int x,int y){
    for(int i=0;i<count(page);++i){int bx,by,w,h;box(page,i,&bx,&by,&w,&h);if(x>=bx&&x<bx+w&&y>=by&&y<by+h)return i;}
    return -1;
}
enum {VOLUME_X=38,VOLUME_Y=228,VOLUME_WIDTH=404};
static int volume_hit(int x,int y){return x>=26&&x<454&&y>=216&&y<254;}
static int volume_at(int x){
    int p=x-VOLUME_X;if(p<0)p=0;if(p>=VOLUME_WIDTH)p=VOLUME_WIDTH-1;
    unsigned volume=((p*20+(VOLUME_WIDTH-1)/2)/(VOLUME_WIDTH-1))*5;
    if(h1_settings.volume!=volume||h1_settings.mute){h1_settings.volume=volume;h1_settings.volume_set=1;h1_settings.mute=0;h1_settings_changed();h1_ps1_apply_settings();return 1;}
    return 0;
}
static int draw(int page,int cursor,int capture,const char *status){
    typedef uint32_t *(*fn_t)(uint16_t *,void *);uint16_t info[6]={0};
    fn_t fn=(fn_t)h1_runtime_entry(h1_runtime_table(H1_RUNTIME_GUI_TABLE_SLOT),0x8f4u);
    canvas=fn?fn(info,0):0;
    if(!canvas||info[1]!=480||info[2]!=272||info[3]!=1920||info[5]!=32)return 0;
    static const char *titles[]={"PS1 游戏已暂停","按键映射","声音设置","显示设置","关于 PS1模拟器"};
    static const char *root[]={"继续游戏","按键映射","声音设置","显示设置","关于","退出游戏"};
    rect(0,0,480,272,0x0b1720);text(titles[page],18,8,0xf0f7ff);
    char label[96];
    const char *hint=page==ABOUT?"确认／返回回到暂停菜单":capture>=0?"请按实体键，返回取消":status&&*status?status:"触摸选择，方向键／确认，返回继续";
    if(page==SOUND&&!(status&&*status)){
        snprintf(label,sizeof label,"音量：%u%%  左右键／滑动调节",h1_settings.volume);hint=label;
        rect(VOLUME_X,VOLUME_Y,VOLUME_WIDTH,12,0x253b4b);rect(VOLUME_X,VOLUME_Y,VOLUME_WIDTH*h1_settings.volume/100,12,0x00b397);
        rect(VOLUME_X+(VOLUME_WIDTH-1)*h1_settings.volume/100-4,VOLUME_Y-4,9,20,0xf0f7ff);
    }
    text(hint,18,30,0xabc4d4);
    if(page==ABOUT){
        text("作者：HelloClyde",38,62,0xf0f7ff);text("核心：PCSX4ALL",38,92,0xf0f7ff);
        text("MIPS JIT / MXU1 / VLC HLE",38,122,0xabc4d4);
        text("声音：32 kHz 单声道",38,152,0xf0f7ff);
        text("github.com/HelloClyde/BBKH1-PS1",38,182,0xabc4d4);
        text("版本：" H1_PS1_VERSION,38,212,0xf0f7ff);
    }
    for(int i=0;i<count(page);++i){
        const char *title=label;
        if(page==ROOT)title=root[i];
        else if(page==KEYS){if(i<14)snprintf(label,sizeof label,"%s：%s",logical_names[i],key_names[mapped_key(logical[i])]);else title=i==14?"恢复默认按键":"返回";}
        else if(page==SOUND){
            if(i==0)snprintf(label,sizeof label,"静音：%s",h1_settings.mute?"开":"关");
            if(i==1)snprintf(label,sizeof label,"极速音频：%s",h1_settings.turbo?"开":"关");
            if(i==2)snprintf(label,sizeof label,"插值与混响：%s",h1_settings.quality?"开":"关");
            if(i==3)title="返回";
        }else if(page==DISPLAY){
            if(i==0)snprintf(label,sizeof label,"GPU 跳帧：%u",h1_settings.gpu_skip);
            if(i==1)snprintf(label,sizeof label,"画面输出：每 %u 帧",h1_settings.lcd_skip+1);
            if(i==2)snprintf(label,sizeof label,"帧率与频率：%s",h1_settings.hud?"显示":"隐藏");
            if(i==3)title="恢复默认显示";if(i==4)title="返回";
        }else title="返回";
        int x,y,w,h;box(page,i,&x,&y,&w,&h);rect(x,y,w,h,i==cursor?0x008c7a:0x253b4b);text(title,x+12,y+(h-21)/2,0xf0f7ff);
    }
    h1_ps1_menu_stats[2]=page;h1_ps1_menu_stats[3]=cursor;h1_ps1_menu_stats[4]=capture+1;++h1_ps1_menu_stats[5];
    return 1;
}
extern "C" int h1_ps1_pause_menu(uint8_t held[45],unsigned opening_touch,unsigned opening_key){
    int page=ROOT,cursor=0,capture=-1,pen=-1,dirty=1,volume_drag=0,result=0,armed=0,save_failed=0;
    unsigned opening_pen=opening_touch;
    const char *status=h1_settings_writable()?"":"设置只在本次生效";
    h1_ps1_menu_stats[0]=0x314d5350;h1_ps1_menu_stats[1]=1;h1_ps1_menu_stats[5]=0;
    if(!h1_settings.volume_set&&!h1_settings.mute)h1_settings.volume=gba_audio_get_volume();
    h1_ps1_log("PAUSE_MENU_BEGIN");
    for(;;){
        if(dirty){if(!draw(page,cursor,capture,status))h1_ps1_escape(11);dirty=0;}
        int code=-1,key=-1,x=0,y=0,activate=0,back=0;h1_event_fetch(&code,&key);
        if(!armed){
            if(code==11)opening_pen=1;if(code==8)opening_pen=0;
            if(code==H1_EVENT_KEY_UP&&key>=1&&key<=44)held[key]=0;
            int opening_held=opening_key>=1&&opening_key<=42&&held[opening_key];
            if(code==-1&&opening_held&&!h1_game_code_down(h1_game_key_code(opening_key)))held[opening_key]=0,opening_held=0;
            if(!opening_pen&&!opening_held)armed=1;
            continue; /* The opening touch/release never activates a menu item. */
        }
        if(code==H1_EVENT_KEY_UP&&key>=1&&key<=44)held[key]=0;
        /* The firmware can synthesize Escape for touch. Real Back/P provide
         * keyboard navigation; Escape cannot close a menu or capture a key. */
        if((code==H1_EVENT_KEY_DOWN||code==H1_EVENT_KEY_UP)&&key==H1_KEY_ESCAPE)continue;
        if(code==11&&page==SOUND&&h1_touch_position(&x,&y)&&volume_hit(x,y)){volume_drag=1;pen=-1;}
        if(volume_drag){
            if(h1_touch_position(&x,&y)){if(volume_at(x))dirty=1;status="";}
            if(code==8)volume_drag=0;
            continue;
        }
        if(code==11){pen=h1_touch_position(&x,&y)?hit(page,x,y):-1;if(pen>=0&&capture<0){cursor=pen;dirty=1;}}
        else if(code==8){if(capture<0&&pen>=0&&h1_touch_position(&x,&y)&&hit(page,x,y)==pen){cursor=pen;activate=1;}pen=-1;}
        else if(code==H1_EVENT_KEY_DOWN&&key>=1&&key<=44){
            if(held[key])continue;held[key]=1;back=key==H1_KEY_BACK||key==H1_KEY_P;
            if(capture>=0){
                if(back){capture=-1;status="已取消";}
                else if(h1_mapping_assign(logical[capture],key)){capture=-1;status="按键已修改";}
                else status="此键保留，请选择其他键";
                dirty=1;continue;
            }
            activate=key==H1_KEY_CONFIRM||key==H1_KEY_ENTER||key==H1_KEY_Z;
            if(page==SOUND&&(key==H1_KEY_LEFT||key==H1_KEY_RIGHT)){
                unsigned v=h1_settings.volume;
                h1_settings.volume=key==H1_KEY_LEFT?(v>5?v-5:0):(v<95?v+5:100);
                h1_settings.volume_set=1;h1_settings.mute=0;h1_settings_changed();h1_ps1_apply_settings();status="";dirty=1;continue;
            }
            int delta=key==H1_KEY_LEFT?-1:key==H1_KEY_RIGHT?1:key==H1_KEY_UP?(page<=KEYS?-2:-1):key==H1_KEY_DOWN?(page<=KEYS?2:1):0;
            if(delta){cursor=(cursor+delta+count(page))%count(page);dirty=1;}
        }
        if(back){if(!page){activate=1;cursor=0;}else{cursor=page==KEYS?1:page==SOUND?2:page==DISPLAY?3:4;page=ROOT;capture=-1;pen=-1;status="";dirty=1;continue;}}
        if(!activate)continue;status="";dirty=1;pen=-1;
        if(page==ROOT){
            if(cursor==0||cursor==5){
                int saved=h1_settings_save();h1_ps1_menu_stats[7]=(unsigned)saved;
                if(saved<0&&h1_settings_writable()&&!save_failed){status="设置未保存，再次选择可继续";save_failed=1;continue;}
                result=cursor==5;break;
            }
            page=cursor==1?KEYS:cursor==2?SOUND:cursor==3?DISPLAY:ABOUT;cursor=0;
        }else if(page==KEYS){
            if(cursor<14)capture=cursor;
            else if(cursor==14){h1_mapping_defaults();status="已恢复默认按键";}
            else{page=ROOT;cursor=1;}
        }else if(page==SOUND){
            if(cursor==0){h1_settings.mute=!h1_settings.mute;h1_settings.volume_set=1;}
            if(cursor==1)h1_settings.turbo=!h1_settings.turbo;
            if(cursor==2)h1_settings.quality=!h1_settings.quality;
            if(cursor==3){page=ROOT;cursor=2;continue;}
            h1_settings_changed();h1_ps1_apply_settings();
        }else if(page==DISPLAY){
            if(cursor==0)h1_settings.gpu_skip=(h1_settings.gpu_skip+1)%4;
            if(cursor==1)h1_settings.lcd_skip=(h1_settings.lcd_skip+1)%3;
            if(cursor==2)h1_settings.hud=!h1_settings.hud;
            if(cursor==3){h1_settings.gpu_skip=H1_GPU_SKIP;h1_settings.lcd_skip=H1_GPU_SKIP?0:1;h1_settings.hud=1;}
            if(cursor==4){page=ROOT;cursor=3;continue;}
            h1_settings_changed();h1_ps1_apply_settings();
        }else{page=ROOT;cursor=4;}
    }
    h1_ps1_menu_stats[1]=0;h1_ps1_menu_stats[6]=result;h1_ps1_log("PAUSE_MENU_END action=%d",result);return result;
}
