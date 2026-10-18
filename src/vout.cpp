#include "h1_port.h"
#include "port.h"
#include "gpu/gpulib/gpu.h"
int vout_init(void){return 0;}
int vout_finish(void){return 0;}
void vout_update(void){h1_ps1_present();}
void vout_blank(void){video_clear();}
void vout_set_config(const gpulib_config_t *){}
