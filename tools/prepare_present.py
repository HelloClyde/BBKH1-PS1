"""Build-only fusion of LCD conversion/copy; preserve normal frontend source."""
from prepare import replace
def prepare_present(root,build):
    path=build/'platform-present.cpp';path.write_bytes((root/'src/platform.cpp').read_bytes())
    replace(path,'#include "h1_port.h"','#include "h1_port.h"\n#include "present_fast.h"')
    replace(path,'static uint32_t colors[32768];\nstatic uint32_t row_cache[480] __attribute__((aligned(32)));\nstatic unsigned colors_ready,clear_screen=1;',
                 'static unsigned clear_screen=1;')
    text=path.read_text(encoding='utf-8');start=text.index('    if(!colors_ready){');end=text.index('    ++h1_ps1_stats.displayed;',start)
    text=text[:start]+'''    if(clear_screen){memset(out,0,480*272*4);clear_screen=0;}
    h1_ps1_present_fused(out,(const uint16_t*)s.vram,s.x,s.y,s.w,s.h,s.depth24);
'''+text[end:]
    path.write_text(text,encoding='utf-8');return path
