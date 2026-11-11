#ifndef SONIC3D_VM_H
#define SONIC3D_VM_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <math.h>
#include <limits.h>

typedef unsigned __int128 u128;
typedef __int128 i128;

#define VM_MEMORY_SIZE (64u * 1024u * 1024u)
#define VM_STOP 0xfffffff0u
#define VM_STACK_TOP 0x03f00000u
#define VM_FRAMEBUFFER 0x03000000u
#define VM_FRAME_PITCH 336u
#define VM_HEAP_BASE 0x01000000u

typedef struct VM {
    uint8_t *mem;
    uint8_t r[8192];
    uint32_t pc;
    uint64_t fuel;
    uint64_t blocks;
    uint32_t trace[256];
    unsigned trace_index;
    int failed;
    char error[512];
    char root[4096];
    uint64_t frame;
    uint32_t ticks;
    uint32_t keys;
    uint32_t heap;
    int verbose;
    int event_count;
    struct { uint32_t type, a, b, c; } events[256];
    char movie[260];
    char sound_paths[48][260];
    uint32_t music_track;
    int movie_playing;
    uint8_t rgba[320 * 240 * 4];
    uint32_t imports[256];
    char import_names[256][80];
    int import_count;
    int file_count;
    struct { void *handle; uint32_t id; } files[64];
} VM;

uint32_t vm_fault(VM *, uint32_t pc, const char *message);
uint32_t vm_translated(VM *, uint32_t pc);
uint32_t vm_dispatch(VM *, uint32_t pc);
int vm_call(VM *, uint32_t pc);
int vm_load_pe(VM *, const char *path);
int vm_boot(VM *);
int vm_tick(VM *, uint32_t keys);
int vm_hook(VM *, uint32_t pc, uint32_t *next);
void vm_present(VM *);
void vm_event(VM *, uint32_t type, uint32_t a, uint32_t b, uint32_t c);
int vm_budget(VM *, uint32_t pc);
int vm_asset_path(VM *, const char *name, char *out, size_t capacity);
void vm_draw_setup(VM *);

static inline int vm_valid(VM *v, uint32_t addr, unsigned size, uint32_t pc) {
    if ((uint64_t)addr + size <= VM_MEMORY_SIZE) return 1;
    vm_fault(v, pc, "memory access outside the reconstructed address space");
    return 0;
}

#define VM_RW(N,T) \
static inline T r##N(VM *v, unsigned p) { T x; memcpy(&x,v->r+p,N); return x; } \
static inline void sr##N(VM *v,unsigned p,T x) { memcpy(v->r+p,&x,N); } \
static inline T m##N(VM *v,uint32_t p,uint32_t pc) { T x=0; if(vm_valid(v,p,N,pc)) memcpy(&x,v->mem+p,N); return x; } \
static inline void sm##N(VM *v,uint32_t p,T x,uint32_t pc) { if(vm_valid(v,p,N,pc)) memcpy(v->mem+p,&x,N); }
VM_RW(1,uint8_t)
VM_RW(2,uint16_t)
VM_RW(4,uint32_t)
VM_RW(8,uint64_t)
#undef VM_RW
static inline u128 r10(VM *v,unsigned p) { u128 x=0; memcpy(&x,v->r+p,10); return x; }
static inline void sr10(VM *v,unsigned p,u128 x) { memcpy(v->r+p,&x,10); }
static inline u128 m10(VM *v,uint32_t p,uint32_t pc) { u128 x=0; if(vm_valid(v,p,10,pc))memcpy(&x,v->mem+p,10); return x; }
static inline void sm10(VM *v,uint32_t p,u128 x,uint32_t pc) { if(vm_valid(v,p,10,pc))memcpy(v->mem+p,&x,10); }
static inline uint64_t r6(VM *v,unsigned p) { uint64_t x=0; memcpy(&x,v->r+p,6); return x; }
static inline void sr6(VM *v,unsigned p,uint64_t x) { memcpy(v->r+p,&x,6); }
static inline uint64_t m6(VM *v,uint32_t p,uint32_t pc) { uint64_t x=0; if(vm_valid(v,p,6,pc))memcpy(&x,v->mem+p,6); return x; }
static inline void sm6(VM *v,uint32_t p,uint64_t x,uint32_t pc) { if(vm_valid(v,p,6,pc))memcpy(v->mem+p,&x,6); }

static inline u128 vm_shift(u128 x,uint64_t n,unsigned bits,unsigned kind) {
    if(n>=bits) return kind==2 && ((x>>(bits-1))&1) ? ~(u128)0 : 0;
    if(kind==0) return x<<n;
    if(kind==1) return x>>n;
    if(bits<128 && ((x>>(bits-1))&1)) x |= (~(u128)0)<<bits;
    return (u128)(((i128)x)>>n);
}

static inline unsigned vm_clz(uint64_t x,unsigned bits) {
    return x ? __builtin_clzll(x)-(64-bits) : bits;
}

static inline uint64_t vm_div(VM *v,uint64_t a,uint64_t b,unsigned size,int sign,int rem,uint32_t pc) {
    if(!b) { vm_fault(v,pc,"integer division by zero"); return 0; }
    if(sign) {
        i128 aa=(i128)(int64_t)(a << (64-size*8)) >> (64-size*8);
        i128 bb=(i128)(int64_t)(b << (64-size*8)) >> (64-size*8);
        return (uint64_t)(rem ? aa%bb : aa/bb);
    }
    return rem ? a%b : a/b;
}

static inline long double fp_read(u128 x,unsigned n) {
    if(n==4) { float f; memcpy(&f,&x,4); return f; }
    if(n==8) { double f; memcpy(&f,&x,8); return f; }
    long double f=0; memcpy(&f,&x,10); return f;
}
static inline u128 fp_write(long double f,unsigned n) {
    u128 x=0;
    if(n==4) { float a=(float)f; memcpy(&x,&a,4); }
    else if(n==8) { double a=(double)f; memcpy(&x,&a,8); }
    else memcpy(&x,&f,10);
    return x;
}
static inline long double fp_round(VM *v,long double f) {
    switch((r2(v,0x10a0)>>10)&3) {
        case 1:return floorl(f);
        case 2:return ceill(f);
        case 3:return truncl(f);
        default:return nearbyintl(f);
    }
}
static inline uint64_t fp_trunc(VM *v,long double f,unsigned n,uint32_t pc) {
    (void)v; (void)pc;
    if(!isfinite(f) || f < -ldexpl(1,n*8-1) || f >= ldexpl(1,n*8-1)) return UINT64_C(1)<<(n*8-1);
    return (uint64_t)(int64_t)truncl(f);
}

#endif
