#ifndef SONIC3D_API_H
#define SONIC3D_API_H
#include <stdint.h>

typedef struct Sonic3D Sonic3D;
typedef struct { uint32_t type,a,b,c; } Sonic3DEvent;
typedef struct {
    uint64_t frame,blocks;
    uint32_t width,height;
    int32_t state,substate;
    uint32_t movie_playing,music_track;
} Sonic3DInfo;

Sonic3D *sonic3d_create(const char *source_root,int verbose);
void sonic3d_destroy(Sonic3D *);
int sonic3d_step(Sonic3D *,uint32_t buttons);
const uint8_t *sonic3d_pixels(Sonic3D *);
const char *sonic3d_error(Sonic3D *);
void sonic3d_info(Sonic3D *,Sonic3DInfo *);
int sonic3d_poll_event(Sonic3D *,Sonic3DEvent *);
const char *sonic3d_sound(Sonic3D *,uint32_t slot);
const char *sonic3d_movie(Sonic3D *);
void sonic3d_movie_done(Sonic3D *);
int sonic3d_quit_requested(Sonic3D *);
int sonic3d_asset_path(Sonic3D *,const char *,char *,unsigned capacity);
/* Inspection tools used by the headless verifier and deterministic replays. */
uint32_t sonic3d_read(Sonic3D *,uint32_t address,unsigned bytes);
int sonic3d_write(Sonic3D *,uint32_t address,uint32_t value,unsigned bytes);
int sonic3d_call(Sonic3D *,uint32_t address,uint32_t eax,uint32_t edx,uint32_t ebx,uint32_t ecx);
uint32_t sonic3d_register(Sonic3D *,unsigned reg);
int sonic3d_copy_memory(Sonic3D *,uint32_t address,void *,unsigned bytes);
unsigned sonic3d_trace(Sonic3D *,uint32_t *,unsigned capacity);

#endif
