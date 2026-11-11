#define _DEFAULT_SOURCE
#include "vm.h"
#include <stdio.h>
#include <stdlib.h>
#include <ctype.h>
#include <dirent.h>
#include <strings.h>
#include <sys/stat.h>
#include <errno.h>

/* Windows filenames on the CD are case insensitive. Resolve each component
 * against the original files rather than changing or duplicating the assets. */
int vm_asset_path(VM *v,const char *name,char *out,size_t capacity) {
    char relative[1024];
    size_t n=strlen(name);
    if(n>=sizeof relative || !capacity) return 0;
    for(size_t i=0;i<=n;++i) relative[i]=name[i]=='\\'?'/':name[i];
    const char *p=relative;
    if(!strncasecmp(p,"PCSONIC/",8)) p+=8;
    while(*p=='/') ++p; /* The bonus-stage filenames are CD-root relative. */
    if(strchr(p,':')) return 0;
    int k=snprintf(out,capacity,"%s/PCSONIC",v->root);
    if(k<0 || (size_t)k>=capacity) return 0;
    char component[260];
    while(*p) {
        while(*p=='/') ++p;
        if(!*p) break;
        size_t len=strcspn(p,"/");
        if(len>=sizeof component) return 0;
        memcpy(component,p,len); component[len]=0; p+=len;
        if(!strcmp(component,".")) continue;
        if(!strcmp(component,"..")) return 0;
        DIR *d=opendir(out);
        if(!d) return 0;
        struct dirent *e;
        int found=0;
        while((e=readdir(d))) if(!strcasecmp(component,e->d_name)) {
            size_t used=strlen(out), extra=strlen(e->d_name);
            if(used+extra+2<=capacity) {
                out[used]='/'; memcpy(out+used+1,e->d_name,extra+1); found=1;
            }
            break;
        }
        closedir(d);
        if(!found) return 0;
    }
    return 1;
}

static const char *guest_string(VM *v,uint32_t p) {
    if(!vm_valid(v,p,1,v->pc)) return "";
    size_t n=VM_MEMORY_SIZE-p;
    if(n>4096) n=4096;
    if(!memchr(v->mem+p,0,n)) {
        vm_fault(v,v->pc,"unterminated platform filename or string"); return "";
    }
    return (char *)v->mem+p;
}

static uint32_t return_to_game(VM *v,unsigned argument_bytes) {
    uint32_t sp=r4(v,16), pc=m4(v,sp,v->pc);
    sr4(v,16,sp+4+argument_bytes);
    return pc;
}

/* Indexed offscreen tile surface. Keep the game's original wrapping and dirty
 * tile renderer; only replace the DirectDraw storage and BltFast operation. */
#define TILE_BUFFER 0x03020000u
#define FONT_BUFFER 0x03040000u
#define DRAW_SURFACE 0x03820000u
#define TILE_SURFACE 0x03820020u
#define FONT_SURFACE 0x03820040u
#define SURFACE_VTABLE 0x03820100u
#define HOST_BLT_FAST 0x03810000u
#define HOST_LOCK 0x03810010u
#define HOST_UNLOCK 0x03810020u

static void surface(VM *v,uint32_t object,uint32_t pixels,unsigned pitch,unsigned w,unsigned h) {
    sm4(v,object,SURFACE_VTABLE,0);sm4(v,object+4,pixels,0);
    sm4(v,object+8,pitch,0);sm4(v,object+12,w,0);sm4(v,object+16,h,0);
}

void vm_draw_setup(VM *v) {
    int load_font=!m4(v,FONT_SURFACE,0);
    const uint32_t pitch=VM_FRAME_PITCH;
    unsigned w=m4(v,0x777770,0),h=m4(v,0x777774,0);
    if(w>320 || h>240) {vm_fault(v,v->pc,"invalid draw dimensions");return;}
    sm4(v,0xa056d4,VM_FRAMEBUFFER,0);sm4(v,0xa056c0,pitch,0);
    for(unsigned y=0;y<h;++y) sm4(v,0x777930+y*4,VM_FRAMEBUFFER+(y+8)*pitch,0);
    /* The original 411980 and 4101d6 renderer bindings, without a COM lock. */
    sm4(v,0x4b81bc,25,0); sm4(v,0x4b81c0,25,0);
    sm4(v,0x4b81c8,w,0); sm4(v,0x4b81d8,h,0);
    sm4(v,0x4b81dc,512,0);sm4(v,0x4b81e0,pitch,0);sm4(v,0x4b81e4,pitch,0);
    sm4(v,0x4b81c4,25<<8,0);sm4(v,0x4b81cc,w<<8,0);
    sm4(v,0x4b81d0,(w+50)<<8,0);sm4(v,0x4b81d4,h+50,0);
    sm4(v,0x778930,pitch,0);
    sm4(v,0x4b0014,0x777930,0);sm4(v,0x4b0018,pitch,0);
    sm4(v,0x4b0020,w,0);sm4(v,0x4b0024,h,0);
    unsigned tile=m4(v,0x4bcca8,0)*4;
    if(!tile || tile>128) {vm_fault(v,v->pc,"invalid original tile dimensions");return;}
    unsigned cols=(w+tile-1)/tile,rows=(h+tile-1)/tile;
    unsigned tw=(cols+1)*tile,th=(rows+1)*tile;
    sm4(v,0x7128c0,cols,0);sm4(v,0x7128c4,rows,0);
    sm4(v,0x7128b0,tw,0);sm4(v,0x7128b4,TILE_BUFFER,0);
    sm4(v,SURFACE_VTABLE+0x1c,HOST_BLT_FAST,0);
    sm4(v,SURFACE_VTABLE+0x64,HOST_LOCK,0);
    sm4(v,SURFACE_VTABLE+0x80,HOST_UNLOCK,0);
    /* BltFast uses physical surface coordinates, including the eight hidden
     * scanlines above the game. Software sprites use the row table instead. */
    surface(v,DRAW_SURFACE,VM_FRAMEBUFFER,pitch,w,h+16);
    surface(v,TILE_SURFACE,TILE_BUFFER,tw,tw,th);
    surface(v,FONT_SURFACE,FONT_BUFFER,640,640,480);
    sm4(v,0xa05600,DRAW_SURFACE,0);sm4(v,0xa05794,TILE_SURFACE,0);
    sm4(v,0xa05604,FONT_SURFACE,0);
    if(load_font) {
        /* Keep the original IFF/PBM decoder and the original font sheet. */
        uint8_t saved[sizeof v->r];memcpy(saved,v->r,sizeof saved);
        sr4(v,0,0x4c32b0);sr4(v,8,FONT_BUFFER);
        vm_call(v,0x489f30);
        memcpy(v->r,saved,sizeof saved);
    }
}

/* All writes go to a separate overlay. Never modify the extracted disc. */
static int overlay_path(VM *v,const char *name,char *out,size_t capacity,int create) {
    char relative[1024];size_t n=strlen(name);
    if(n>=sizeof relative) return 0;
    for(size_t i=0;i<=n;++i) relative[i]=tolower((unsigned char)(name[i]=='\\'?'/':name[i]));
    char *p=relative;
    if(!strncmp(p,"pcsonic/",8)) p+=8;
    while(*p=='/') ++p;
    if(strchr(p,':')) return 0;
    for(char *q=p;*q;) {
        size_t len=strcspn(q,"/");
        if((len==2 && !memcmp(q,"..",2)) || !len) return 0;
        q+=len;if(*q)++q;
    }
    const char *dir=getenv("SONIC3D_SAVE_DIR");
    int k=dir&&*dir?snprintf(out,capacity,"%s/%s",dir,p):
                       snprintf(out,capacity,"%s/../saves/%s",v->root,p);
    if(k<0 || (size_t)k>=capacity) return 0;
    if(create) for(char *q=out+1;*q;++q) if(*q=='/') {
        *q=0;int result=mkdir(out,0700);*q='/';
        if(result && errno!=EEXIST) return 0;
    }
    return 1;
}

static FILE *open_file(VM *v,const char *name,const char *mode) {
    char path[8192];
    int writing=strchr(mode,'w') || strchr(mode,'a') || strchr(mode,'+');
    if(overlay_path(v,name,path,sizeof path,writing)) {
        FILE *f=fopen(path,mode);
        if(f || writing) {
            if(v->verbose>1) fprintf(stderr,"%s %s\n",mode,path);
            return f;
        }
    }
    if(writing || !vm_asset_path(v,name,path,sizeof path)) return NULL;
    if(v->verbose>1) fprintf(stderr,"%s %s\n",mode,path);
    return fopen(path,mode);
}

#define FILE_OBJECTS 0x03900000u
static FILE *file_handle(VM *v,uint32_t p) {
    if(p<FILE_OBJECTS || (p-FILE_OBJECTS)%64 || (p-FILE_OBJECTS)/64>=64) {
        vm_fault(v,v->pc,"invalid original file handle");return NULL;
    }
    return v->files[(p-FILE_OBJECTS)/64].handle;
}

/* A small first-fit allocator for the original decoder's temporary buffers.
 * Headers live in the reserved arena, so instances remain independent. */
static uint32_t allocate(VM *v,uint32_t size) {
    if(!size)size=1;
    if(size>0x01e00000) return 0;
    size=(size+15)&~15u;
    for(uint32_t p=VM_HEAP_BASE;p<v->heap;) {
        uint32_t n=m4(v,p,0),used=m4(v,p+4,0);
        if(n<size || used) {p+=n+16;continue;}
        if(n>=size+32) {
            sm4(v,p+size+16,n-size-16,0);sm4(v,p+size+20,0,0);
            sm4(v,p,size,0);
        }
        sm4(v,p+4,1,0);return p+16;
    }
    uint32_t p=v->heap;
    if((uint64_t)p+size+16>=0x02f00000) return 0;
    sm4(v,p,size,0);sm4(v,p+4,1,0);v->heap+=size+16;
    return p+16;
}

static void deallocate(VM *v,uint32_t ptr) {
    if(!ptr)return;
    int found=0;
    for(uint32_t p=VM_HEAP_BASE;p<v->heap;) {
        uint32_t n=m4(v,p,0);
        if(p+16==ptr) {sm4(v,p+4,0,0);found=1;break;}
        p+=n+16;
    }
    if(!found) {vm_fault(v,v->pc,"invalid original heap pointer");return;}
    for(uint32_t p=VM_HEAP_BASE;p<v->heap;) {
        uint32_t n=m4(v,p,0),next=p+n+16;
        if(!m4(v,p+4,0) && next<v->heap && !m4(v,next+4,0))
            sm4(v,p,n+16+m4(v,next,0),0);
        else if(!m4(v,p+4,0) && next==v->heap) {v->heap=p;break;}
        else p=next;
    }
}

static uint32_t whole_file(VM *v,uint32_t name,uint32_t dest,uint32_t limit) {
    char path[4096];
    const char *s=guest_string(v,name);
    (void)path;
    FILE *f=open_file(v,s,"rb");
    if(!f) return UINT32_MAX;
    if(!vm_valid(v,dest,limit,v->pc)) {fclose(f);return UINT32_MAX;}
    size_t n=fread(v->mem+dest,1,limit,f);
    int bad=ferror(f); fclose(f);
    if(v->verbose>1) fprintf(stderr,"load %s -> %08x: %zu bytes\n",s,dest,n);
    return bad?UINT32_MAX:(uint32_t)n;
}

static uint32_t arg(VM *v,unsigned i) {return m4(v,r4(v,16)+4+i*4,v->pc);}

static void blt_fast(VM *v) {
    uint32_t dst=arg(v,0),src=arg(v,3),rect=arg(v,4);
    if((dst!=DRAW_SURFACE && dst!=TILE_SURFACE && dst!=FONT_SURFACE) ||
       (src!=DRAW_SURFACE && src!=TILE_SURFACE && src!=FONT_SURFACE)) {
        vm_fault(v,v->pc,"unknown indexed surface");return;
    }
    int dx=(int32_t)arg(v,1),dy=(int32_t)arg(v,2);
    int sx=(int32_t)m4(v,rect,v->pc),sy=(int32_t)m4(v,rect+4,v->pc);
    int w=(int32_t)m4(v,rect+8,v->pc)-sx,h=(int32_t)m4(v,rect+12,v->pc)-sy;
    int dw=m4(v,dst+12,0),dh=m4(v,dst+16,0),sw=m4(v,src+12,0),sh=m4(v,src+16,0);
    if(dx<0) {sx-=dx;w+=dx;dx=0;} if(dy<0) {sy-=dy;h+=dy;dy=0;}
    if(sx<0) {dx-=sx;w+=sx;sx=0;} if(sy<0) {dy-=sy;h+=sy;sy=0;}
    if(w>dw-dx) w=dw-dx;
    if(w>sw-sx) w=sw-sx;
    if(h>dh-dy) h=dh-dy;
    if(h>sh-sy) h=sh-sy;
    if(w<=0 || h<=0) return;
    uint32_t dp=m4(v,dst+4,0),sp=m4(v,src+4,0);
    unsigned dstride=m4(v,dst+8,0),sstride=m4(v,src+8,0);
    for(int y=0;y<h;++y)
        memmove(v->mem+dp+(dy+y)*dstride+dx,v->mem+sp+(sy+y)*sstride+sx,w);
}

static int host_import(VM *v,unsigned i,uint32_t *next) {
    const char *name=v->import_names[i];
    uint32_t result=0;
    unsigned pop=0;
    if(!strcmp(name,"timeGetTime")) result=v->ticks;
    else if(!strcmp(name,"mciSendStringA")) {
        const char *s=guest_string(v,arg(v,0));
        char lower[1024];size_t len=strlen(s);
        if(len>=sizeof lower) len=sizeof lower-1;
        for(size_t j=0;j<len;++j) lower[j]=tolower((unsigned char)s[j]);
        lower[len]=0;
        if(v->verbose>1) fprintf(stderr,"mci %s\n",s);
        unsigned track=0,minute=0,second=0;
        if(sscanf(lower,"play cdaudio from %u:%u:%u",&track,&minute,&second)>=1) {
            v->music_track=track;
            vm_event(v,2,track,minute*60+second,0);
        } else if(!strncmp(lower,"stop cdaudio",12) || !strncmp(lower,"close cdaudio",13)) {
            v->music_track=0;vm_event(v,2,0,0,0);
        }
        if(arg(v,1) && arg(v,2)) v->mem[arg(v,1)]=0;
        pop=16;
    } else if(!strcmp(name,"joyGetPos")) { result=167;pop=8; }
    else if(!strcmp(name,"joyGetDevCapsA")) { result=165;pop=12; }
    else if(!strcmp(name,"GetActiveWindow")) result=1;
    else if(!strcmp(name,"GetKeyboardState")) {result=1;pop=4;}
    else if(!strcmp(name,"GetLastError")) result=0;
    else if(!strcmp(name,"GetCurrentThreadId") || !strcmp(name,"GetCurrentProcessId")) result=1;
    else if(!strcmp(name,"GetVersion")) result=0x80000004;
    else if(!strcmp(name,"GetUserDefaultLangID")) result=0x409;
    else if(!strcmp(name,"CharNextA")) {result=arg(v,0)+(v->mem[arg(v,0)]!=0);pop=4;}
    else if(!strcmp(name,"VirtualAlloc")) {
        uint32_t size=(arg(v,1)+4095)&~4095u;
        if(v->heap+size<0x02f00000) {result=v->heap;v->heap+=size;}
        pop=16;
    } else if(!strcmp(name,"VirtualFree")) {result=1;pop=12;}
    else if(!strcmp(name,"timeKillEvent")) {pop=4;}
    else if(!strcmp(name,"timeSetEvent")) {result=1;pop=20;}
    else if(!strcmp(name,"GetSystemMetrics")) {result=arg(v,0)==0?640:480;pop=4;}
    else if(!strcmp(name,"GetClientRect")) {
        uint32_t p=arg(v,1);sm4(v,p,0,v->pc);sm4(v,p+4,0,v->pc);
        sm4(v,p+8,320,v->pc);sm4(v,p+12,224,v->pc);result=1;pop=8;
    } else if(!strcmp(name,"SetRectEmpty")) {
        uint32_t p=arg(v,0);if(vm_valid(v,p,16,v->pc)) memset(v->mem+p,0,16);
        result=1;pop=4;
    } else {
        char message[160];snprintf(message,sizeof message,"unimplemented host import: %s",name);
        vm_fault(v,v->pc,message);*next=VM_STOP;return 1;
    }
    sr4(v,0,result);
    *next=return_to_game(v,pop);
    return 1;
}

int vm_hook(VM *v,uint32_t pc,uint32_t *next) {
    v->pc=pc;
    if(pc>=0x03800000 && pc<0x03800000+(unsigned)v->import_count*16 && !(pc&15))
        return host_import(v,(pc-0x03800000)/16,next);
    unsigned pop=0;
    switch(pc) {
    case HOST_BLT_FAST:
        blt_fast(v);sr4(v,0,0);pop=24;break;
    case HOST_LOCK: {
        uint32_t obj=arg(v,0),desc=arg(v,2);
        if(obj!=DRAW_SURFACE && obj!=TILE_SURFACE && obj!=FONT_SURFACE) {
            vm_fault(v,pc,"lock of unknown indexed surface");break;
        }
        sm4(v,desc+8,m4(v,obj+16,pc),pc);sm4(v,desc+12,m4(v,obj+12,pc),pc);
        sm4(v,desc+16,m4(v,obj+8,pc),pc);sm4(v,desc+36,m4(v,obj+4,pc),pc);
        sr4(v,0,0);pop=20;break;
    }
    case HOST_UNLOCK:sr4(v,0,0);pop=8;break;
    case 0x4a3821: /* Watcom stack probe: its caller pushed the probe size. */
        pop=4;break;
    case 0x48f4a0:
        sr4(v,0,whole_file(v,r4(v,0),r4(v,8),r4(v,12)));break;
    case 0x48f41c: {
        FILE *f=open_file(v,guest_string(v,r4(v,0)),"rb");
        sr4(v,0,f!=NULL);if(f)fclose(f);break;
    }
    case 0x4a3e6b: { /* Watcom fopen(name, mode). */
        FILE *f=open_file(v,guest_string(v,r4(v,0)),guest_string(v,r4(v,8)));
        uint32_t result=0;
        if(f) {
            unsigned i=0;while(i<64 && v->files[i].handle)++i;
            if(i==64) {fclose(f);vm_fault(v,pc,"too many open original files");break;}
            result=FILE_OBJECTS+i*64;v->files[i].handle=f;v->files[i].id=result;
            memset(v->mem+result,0,64);
            sm1(v,result+12,0x43,pc);
        }
        sr4(v,0,result);break;
    }
    case 0x4a3a9e:case 0x4a4218: { /* fread/fwrite: EAX data, EDX size, EBX count, ECX FILE*. */
        uint32_t object=r4(v,4),data=r4(v,0),size=r4(v,8),count=r4(v,12);
        FILE *f=file_handle(v,object);size_t result=0;
        if(f && (uint64_t)size*count<=VM_MEMORY_SIZE && vm_valid(v,data,size*count,pc)) {
            result=pc==0x4a3a9e?fread(v->mem+data,size,count,f):fwrite(v->mem+data,size,count,f);
            if(feof(f))sm1(v,object+12,m1(v,object+12,pc)|0x10,pc);
            if(ferror(f))sm1(v,object+12,m1(v,object+12,pc)|0x20,pc);
        }
        sr4(v,0,result);break;
    }
    case 0x4a39aa: { /* fseek */
        uint32_t object=r4(v,0);FILE *f=file_handle(v,object);
        int result=f?fseek(f,(int32_t)r4(v,8),r4(v,12)):-1;
        if(!result)sm1(v,object+12,m1(v,object+12,pc)&~0x10,pc);
        sr4(v,0,result);break;
    }
    case 0x4a40c8: {FILE *f=file_handle(v,r4(v,0));sr4(v,0,f?ftell(f):-1);break;}
    case 0x4a3f57: {
        uint32_t object=r4(v,0);FILE *f=file_handle(v,object);int result=-1;
        if(f) {result=fclose(f);v->files[(object-FILE_OBJECTS)/64].handle=NULL;}
        sr4(v,0,result);break;
    }
    case 0x4a411c:case 0x4a68b4:sr4(v,0,allocate(v,r4(v,0)));break;
    case 0x4a4124:case 0x4a6900:deallocate(v,r4(v,0));break;
    case 0x4a2598:
        vm_draw_setup(v);sr4(v,0,VM_FRAME_PITCH);break;
    case 0x4a2668:break; /* Unlock: all renderer writes are already local. */
    case 0x4a2750:
        sr4(v,0,m4(v,0x7128b0,pc));break;
    case 0x4a27ac:break;
    case 0x4a2ca0:
        vm_draw_setup(v);sr4(v,0,1);break;
    case 0x4a2bcc:break;
    case 0x48865c:
        sm4(v,0x4ea158,1,pc);sm4(v,0x4ea154,0,pc);sr4(v,0,1);break;
    case 0x488978: {
        uint32_t slot=r4(v,8);
        if(slot>=48) {vm_fault(v,pc,"sound slot outside original table");break;}
        snprintf(v->sound_paths[slot],260,"%s",guest_string(v,r4(v,0)));
        sr4(v,0,1);break;
    }
    case 0x488b50:
        if(r4(v,0)<48 && !m1(v,0x4eaa5c,pc) && m4(v,0x4ea158,pc))
            vm_event(v,1,r4(v,0),r4(v,8),0);
        sr4(v,0,1);break;
    case 0x487af8:case 0x487c6c:
        vm_event(v,4,0,0,0);return 0; /* Keep the original per-stage sound table loader. */
    case 0x494340:
        snprintf(v->movie,sizeof v->movie,"%s",guest_string(v,r4(v,0)));
        sm4(v,0x77a1f4,1,pc);sr4(v,0,1);break;
    case 0x4941a0:break;
    case 0x494650:
        v->movie_playing=r4(v,8)!=0 && !v->movie_playing;
        sm4(v,0x77a1f0,v->movie_playing,pc);
        vm_event(v,3,v->movie_playing,0,0);break;
    case 0x4942f8:
        v->movie_playing=0;sm4(v,0x77a1f0,0,pc);sm4(v,0x77a1f4,0,pc);break;
    default:return 0;
    }
    *next=v->failed?VM_STOP:return_to_game(v,pop);
    return 1;
}
