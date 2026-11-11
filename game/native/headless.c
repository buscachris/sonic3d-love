#include "api.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {unsigned first,duration,keys;} Press;
static void screenshot(Sonic3D *s,const char *path) {
    Sonic3DInfo info;sonic3d_info(s,&info);
    FILE *f=fopen(path,"wb");if(!f) {perror(path);return;}
    fprintf(f,"P6\n%u %u\n255\n",info.width,info.height);
    const uint8_t *p=sonic3d_pixels(s);
    for(unsigned i=0;i<info.width*info.height;++i) fwrite(p+i*4,1,3,f);
    fclose(f);
}
int main(int argc,char **argv) {
    const char *root="source",*capture=NULL;unsigned frames=600;int verbose=0,skip=0;
    Press presses[128];unsigned count=0;
    for(int i=1;i<argc;++i) {
        if(!strcmp(argv[i],"--source") && i+1<argc) root=argv[++i];
        else if(!strcmp(argv[i],"--frames") && i+1<argc) frames=strtoul(argv[++i],NULL,0);
        else if(!strcmp(argv[i],"--capture") && i+1<argc) capture=argv[++i];
        else if(!strcmp(argv[i],"--skip-movies")) skip=1;
        else if(!strcmp(argv[i],"--verbose")) ++verbose;
        else if(!strcmp(argv[i],"--press") && i+1<argc && count<128) {
            if(sscanf(argv[++i],"%u:%u:%i",&presses[count].first,&presses[count].duration,(int *)&presses[count].keys)!=3) return 2;
            ++count;
        } else {
            fprintf(stderr,"Usage: %s [--source source] [--frames N] [--skip-movies] [--press first:duration:mask] [--capture image.ppm] [--verbose]\n",argv[0]);
            return 2;
        }
    }
    Sonic3D *s=sonic3d_create(root,verbose);
    if(!s || *sonic3d_error(s)) goto failure;
    clock_t begin=clock();int previous=-999,sub=-999;
    for(unsigned f=0;f<frames;++f) {
        unsigned keys=0;
        for(unsigned p=0;p<count;++p) if(f>=presses[p].first && f<presses[p].first+presses[p].duration) keys|=presses[p].keys;
        if(!sonic3d_step(s,keys)) goto failure;
        Sonic3DInfo info;sonic3d_info(s,&info);
        if(info.state!=previous || info.substate!=sub) {
            printf("frame %llu: state %d/%d\n",(unsigned long long)info.frame,info.state,info.substate);
            previous=info.state;sub=info.substate;
        }
        Sonic3DEvent e;
        while(sonic3d_poll_event(s,&e)) {
            if(verbose) printf("event %u %u %u %u\n",e.type,e.a,e.b,e.c);
            if(e.type==3 && skip) sonic3d_movie_done(s);
        }
    }
    if(capture) screenshot(s,capture);
    Sonic3DInfo info;sonic3d_info(s,&info);
    uint32_t hash=2166136261u;
    const uint8_t *pixels=sonic3d_pixels(s);
    for(unsigned i=0;i<info.width*info.height*4;++i) hash=(hash^pixels[i])*16777619u;
    printf("Ran %llu frames, %llu code blocks in %.3fs; %ux%u, pixel FNV1a %08x\n",
        (unsigned long long)info.frame,(unsigned long long)info.blocks,(double)(clock()-begin)/CLOCKS_PER_SEC,info.width,info.height,hash);
    sonic3d_destroy(s);return 0;
failure:
    fprintf(stderr,"%s\n",sonic3d_error(s));
    if(s) {
        uint32_t trace[256];unsigned n=sonic3d_trace(s,trace,256);
        fprintf(stderr,"Last code blocks:\n");
        for(unsigned i=0;i<n;++i) fprintf(stderr,"%08x%c",trace[i],i%8==7?'\n':' ');
        fprintf(stderr,"\n");
    }
    sonic3d_destroy(s);return 1;
}
