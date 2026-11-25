#include "vm.h"
#include "api.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static VM *vm(Sonic3D *s) {return (VM *)s;}

Sonic3D *sonic3d_create(const char *source_root,int verbose) {
    VM *v=calloc(1,sizeof *v);
    if(!v) return NULL;
    v->mem=calloc(1,VM_MEMORY_SIZE);
    v->verbose=verbose;
    if(!v->mem) {free(v);return NULL;}
    if(!source_root || !realpath(source_root,v->root)) {
        v->failed=1;snprintf(v->error,sizeof v->error,"Cannot resolve the original game data directory");
        return (Sonic3D *)v;
    }
    char path[8192];snprintf(path,sizeof path,"%s/PCSONIC.EXE",v->root);
    if(vm_load_pe(v,path)) vm_boot(v);
    return (Sonic3D *)v;
}

void sonic3d_destroy(Sonic3D *s) {
    VM *v=vm(s);if(!v) return;
    for(int i=0;i<64;++i) if(v->files[i].handle) fclose(v->files[i].handle);
    free(v->mem);free(v);
}
int sonic3d_step(Sonic3D *s,uint32_t buttons) {return vm_tick(vm(s),buttons);}
int sonic3d_quit_requested(Sonic3D *s) {return m4(vm(s),0xa05260,0)!=0;}
const uint8_t *sonic3d_pixels(Sonic3D *s) {return vm(s)->rgba;}
const char *sonic3d_error(Sonic3D *s) {return s?vm(s)->error:"Cannot allocate the game runtime";}
void sonic3d_info(Sonic3D *s,Sonic3DInfo *out) {
    VM *v=vm(s);
    *out=(Sonic3DInfo){v->frame,v->blocks,m4(v,0x777770,0),m4(v,0x777774,0),
        (int32_t)m4(v,0x610874,0),(int32_t)m4(v,0x610878,0),v->movie_playing,v->music_track};
}
int sonic3d_poll_event(Sonic3D *s,Sonic3DEvent *out) {
    VM *v=vm(s);if(!v->event_count) return 0;
    memcpy(out,&v->events[0],sizeof *out);
    memmove(v->events,v->events+1,(--v->event_count)*sizeof v->events[0]);return 1;
}
const char *sonic3d_sound(Sonic3D *s,uint32_t slot) {return slot<48?vm(s)->sound_paths[slot]:"";}
const char *sonic3d_movie(Sonic3D *s) {return vm(s)->movie;}
void sonic3d_movie_done(Sonic3D *s) {
    VM *v=vm(s);v->movie_playing=0;sm4(v,0x77a1f0,0,0);
}
int sonic3d_asset_path(Sonic3D *s,const char *name,char *out,unsigned capacity) {
    return vm_asset_path(vm(s),name,out,capacity);
}
uint32_t sonic3d_read(Sonic3D *s,uint32_t p,unsigned n) {
    VM *v=vm(s);
    switch(n) {case 1:return m1(v,p,0);case 2:return m2(v,p,0);case 4:return m4(v,p,0);default:return 0;}
}
int sonic3d_write(Sonic3D *s,uint32_t p,uint32_t a,unsigned n) {
    VM *v=vm(s);
    switch(n) {case 1:sm1(v,p,a,0);break;case 2:sm2(v,p,a,0);break;case 4:sm4(v,p,a,0);break;default:return 0;}
    return !v->failed;
}
int sonic3d_call(Sonic3D *s,uint32_t p,uint32_t eax,uint32_t edx,uint32_t ebx,uint32_t ecx) {
    VM *v=vm(s);sr4(v,0,eax);sr4(v,8,edx);sr4(v,12,ebx);sr4(v,4,ecx);return vm_call(v,p);
}
uint32_t sonic3d_register(Sonic3D *s,unsigned n) {return n<8?r4(vm(s),n*4):0;}
int sonic3d_copy_memory(Sonic3D *s,uint32_t p,void *out,unsigned n) {
    VM *v=vm(s);if(!vm_valid(v,p,n,0)) return 0;
    memcpy(out,v->mem+p,n);return 1;
}
unsigned sonic3d_trace(Sonic3D *s,uint32_t *out,unsigned capacity) {
    VM *v=vm(s);unsigned n=v->trace_index<256?v->trace_index:256;
    if(n>capacity)n=capacity;
    for(unsigned i=0;i<n;++i) out[i]=v->trace[(v->trace_index-n+i)&255];
    return n;
}
