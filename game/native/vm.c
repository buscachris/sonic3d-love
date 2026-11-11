#include "vm.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>

uint32_t vm_fault(VM *v, uint32_t pc, const char *message) {
    if (!v->failed) {
        v->failed = 1;
        v->pc = pc;
        snprintf(v->error, sizeof v->error,
                 "%s at %08x (frame %llu, state %d/%d, eax=%08x edx=%08x esp=%08x)",
                 message, pc, (unsigned long long)v->frame,
                 (int32_t)m4(v,0x610874,0), (int32_t)m4(v,0x610878,0),
                 r4(v,0),r4(v,8),r4(v,16));
        if (v->verbose) fprintf(stderr,"%s\n",v->error);
    }
    return VM_STOP;
}

int vm_budget(VM *v, uint32_t pc) {
    v->pc = pc;
    v->trace[v->trace_index++ & 255] = pc;
    ++v->blocks;
    if (v->failed) return 0;
    if (!v->fuel--) {
        vm_fault(v,pc,"translated code exceeded the per-call work limit");
        return 0;
    }
    return 1;
}

void vm_event(VM *v,uint32_t type,uint32_t a,uint32_t b,uint32_t c) {
    if (v->event_count == 256) {
        vm_fault(v,v->pc,"platform event queue overflow");
        return;
    }
    int n=v->event_count++;
    v->events[n].type=type;
    v->events[n].a=a; v->events[n].b=b; v->events[n].c=c;
    if (v->verbose>1) fprintf(stderr,"event %u %u %u %u\n",type,a,b,c);
}

uint32_t vm_dispatch(VM *v,uint32_t pc) {
    uint32_t next;
    if (v->failed || pc==VM_STOP) return VM_STOP;
    v->pc=pc;
    if (vm_hook(v,pc,&next)) return next;
    return vm_translated(v,pc);
}

static int call_with_args(VM *v,uint32_t pc,unsigned arg_bytes) {
    uint32_t sp=r4(v,16);
    if (sp<0x1000000 || sp>VM_MEMORY_SIZE-4) {
        vm_fault(v,pc,"invalid game stack");
        return 0;
    }
    if(arg_bytes) memset(v->mem+sp-arg_bytes,0,arg_bytes);
    sm4(v,sp-arg_bytes-4,VM_STOP,pc);
    sr4(v,16,sp-arg_bytes-4);
    v->fuel=100000000;
    while (pc!=VM_STOP && !v->failed) pc=vm_dispatch(v,pc);
    if (!v->failed && r4(v,16)!=sp) vm_fault(v,pc,"unbalanced translated function stack");
    return !v->failed;
}

int vm_call(VM *v,uint32_t pc) { return call_with_args(v,pc,0); }

int vm_load_pe(VM *v,const char *path) {
    FILE *f=fopen(path,"rb");
    if (!f) { snprintf(v->error,sizeof v->error,"Cannot open original game data: %.400s",path); v->failed=1; return 0; }
    fseek(f,0,SEEK_END); long size=ftell(f); rewind(f);
    uint8_t *data=malloc(size>0?(size_t)size:1);
    if (size<0x400 || !data || fread(data,1,size,f)!=(size_t)size) {
        fclose(f); free(data); vm_fault(v,0,"Cannot read original game executable"); return 0;
    }
    fclose(f);
    uint32_t pe; memcpy(&pe,data+0x3c,4);
    if (data[0]!='M' || data[1]!='Z' || pe+0x108>(uint32_t)size || memcmp(data+pe,"PE\0\0",4)) {
        free(data); vm_fault(v,0,"Invalid original game executable"); return 0;
    }
    uint16_t sections,os; uint32_t image,headers;
    memcpy(&sections,data+pe+6,2); memcpy(&os,data+pe+20,2);
    memcpy(&image,data+pe+24+28,4); memcpy(&headers,data+pe+24+60,4);
    if (image!=0x400000 || headers>(uint32_t)size) {
        free(data); vm_fault(v,0,"Unexpected original game image layout"); return 0;
    }
    memcpy(v->mem+image,data,headers);
    for (unsigned i=0;i<sections;++i) {
        uint8_t *s=data+pe+24+os+i*40;
        uint32_t va,n,raw;
        memcpy(&va,s+12,4);memcpy(&n,s+16,4);memcpy(&raw,s+20,4);
        /* Watcom puts the uninitialized extent in SizeOfRawData with no
         * file offset; that section is already zero in the reserved arena. */
        if (!raw) continue;
        if ((uint64_t)raw+n>(uint64_t)size || (uint64_t)image+va+n>VM_MEMORY_SIZE) {
            free(data);vm_fault(v,0,"Invalid original game section");return 0;
        }
        memcpy(v->mem+image+va,data+raw,n);
    }
    free(data);
    /* Imports become explicit host entry points. No Windows binary is executed. */
    uint32_t dir=image+m4(v,image+pe+24+104,0);
    while (m4(v,dir+12,0)) {
        uint32_t name=image+m4(v,dir+12,0);
        uint32_t look=image+m4(v,dir,0), iat=image+m4(v,dir+16,0);
        if (look==image) look=iat;
        for (unsigned i=0;m4(v,look+i*4,0);++i) {
            uint32_t n=m4(v,look+i*4,0);
            if (v->import_count>=256) {vm_fault(v,dir,"Too many host imports");return 0;}
            unsigned k=v->import_count++;
            v->imports[k]=iat+i*4;
            if (n&0x80000000) snprintf(v->import_names[k],80,"%s:#%u",v->mem+name,n&0xffff);
            else snprintf(v->import_names[k],80,"%s",v->mem+image+n+2);
            sm4(v,iat+i*4,0x03800000+k*16,0);
        }
        dir+=20;
    }
    return !v->failed;
}

int vm_boot(VM *v) {
    v->heap=VM_HEAP_BASE;
    sr4(v,16,VM_STACK_TOP);
    sr2(v,0x10a0,0x037f); /* x87 defaults: extended precision, nearest even. */
    sr1(v,0x20a,0);      /* DF: original startup's CLD. */
    /* Watcom's game initializers construct object arrays and the big-endian
     * stage-code table. These precede WinMain in the original executable. */
    if (!vm_call(v,0x41d530) || !vm_call(v,0x47d980) || !vm_call(v,0x489110)) return 0;
    sm4(v,0x5eab14,0x610888,0); sm4(v,0x5eab18,0x620888,0);
    sm4(v,0x5eab1c,0x620088,0); sm4(v,0x5eaae8,0x55aae8,0);
    sm4(v,0x777770,320,0); sm4(v,0x777774,224,0);
    sm4(v,0xa056d4,VM_FRAMEBUFFER,0); sm4(v,0xa056c0,VM_FRAME_PITCH,0);
    sm4(v,0x4bdf40,1,0); sm4(v,0x4bdf44,0,0);
    sm4(v,0x4bdf4c,1,0); /* Original palette fades enabled. */
    v->mem[0x7777c0]=0; /* Assets are relative to source/PCSONIC. */
    v->ticks=1000;
    if (!vm_call(v,0x48865c) || !vm_call(v,0x48a7c4)) return 0;
    sm4(v,0x610880,0,0); sm4(v,0x77755c,0,0);
    sm4(v,0x610884,v->ticks,0); sm4(v,0xa05958,v->ticks,0);
    sm4(v,0xa0595c,v->ticks,0); sm4(v,0xa052d4,0x5b8d80,0);
    vm_draw_setup(v);
    vm_present(v);
    return !v->failed;
}

int vm_tick(VM *v,uint32_t keys) {
    if (v->failed) return 0;
    v->keys=keys;
    uint32_t previous=v->ticks;
    v->ticks=1000+(uint32_t)(v->frame*1000/60);
    /* The PC edition's 16 ms multimedia callback animates its palettes even
     * while the main thread waits. Execute that original callback, including
     * its five stdcall arguments, on a deterministic clock. */
    for(uint32_t timer=previous/16;timer<v->ticks/16;++timer)
        if(!call_with_args(v,0x49fa20,20)) return 0;
    sm4(v,0x610884,v->ticks,0);
    sm4(v,0xa05960,previous,0);sm4(v,0xa0595c,v->ticks,0);
    if(m4(v,0xa0597c,0)==1) {
        int32_t remaining=(int32_t)m4(v,0xa052d4,0)-(int32_t)(v->ticks-previous);
        sm4(v,0xa052d4,(uint32_t)remaining,0);
        if(remaining<1 && m4(v,0xa05978,0)==1) {
            sr4(v,0,m4(v,0x4bdf54,0));sr4(v,8,1);
            if(!vm_call(v,0x4a3490)) return 0;
        }
    }
    /* Feed the original keyboard reader, preserving its edge/opposite-key logic. */
    memset(v->mem+0x777568,0,0x200);
    static const uint32_t byte_addr[]={0x77757b,0x777569,0x77756a,0x77756b,
                                      0x7775a0,0x77759a,0x77759c,0x77759e,
                                      0x777580,0x777581,0x777582};
    for(unsigned i=0;i<sizeof byte_addr/sizeof byte_addr[0];++i) v->mem[byte_addr[i]]=(keys>>i)&1;
    sm4(v,0x777790,0,0);
    sm4(v,0x4bcc48,1,0);
    if (!vm_call(v,0x48aba4)) return 0;
    /* DirectDraw consumes this flag when presenting the palette. */
    v->mem[0x777564]=0;
    vm_present(v);
    ++v->frame;
    return !v->failed;
}

void vm_present(VM *v) {
    unsigned w=m4(v,0x777770,0),h=m4(v,0x777774,0);
    if (w>320 || h>240) {vm_fault(v,v->pc,"unsupported original display dimensions");return;}
    for(unsigned y=0;y<h;++y) {
        uint32_t row=m4(v,0x777930+y*4,0);
        if (!vm_valid(v,row,w,0)) return;
        for(unsigned x=0;x<w;++x) {
            unsigned p=0x779710+4*v->mem[row+x];
            uint8_t *out=v->rgba+(y*w+x)*4;
            out[0]=v->mem[p];out[1]=v->mem[p+1];out[2]=v->mem[p+2];out[3]=255;
        }
    }
}
