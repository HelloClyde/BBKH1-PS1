/* Unencrypted PS1 EBOOT.PBP reader. GPL-2.0-or-later. */
#ifndef H1_PS1_PBP_H
#define H1_PS1_PBP_H
#include <stdint.h>
struct H1Pbp;
struct H1PbpTrack {unsigned first,start,end,audio;};
struct H1PbpInfo {
    unsigned discs,selected,tracks,sectors;
    H1PbpTrack track[100];
};
H1Pbp *h1_pbp_open(const char *path,unsigned selected,H1PbpInfo *info,const char **error);
void h1_pbp_close(H1Pbp *image);
int h1_pbp_read(H1Pbp *image,unsigned sector,uint8_t *output,bool audio);
#endif
