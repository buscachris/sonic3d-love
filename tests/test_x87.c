/* Exercise the Android conversion on the desktop too; compare canonical x87
   encodings with the host's x87 ABI when that is available. */
#define SONIC3D_PORTABLE_X87 1
#include "../game/native/vm.h"
#include <assert.h>
#include <stdio.h>

static void check(u128 bits) {
    long double f=fp_read(bits,10);
    assert(fp_write(f,10)==bits);
#if LDBL_MANT_DIG == 64 && LDBL_MAX_EXP == 16384
    long double native=0;
    memcpy(&native,&bits,10);
    assert(f==native && !!signbit(f)==!!signbit(native));
#endif
}

int main(void) {
    const uint64_t fractions[]={0,1,2,UINT64_C(0x7fffffffffffffff),
        UINT64_C(0x8000000000000000),UINT64_C(0x8000000000000001),UINT64_MAX};
    const unsigned exponents[]={0,1,2,16382,16383,16384,32765,32766};
    for(unsigned sign=0;sign<2;sign++) {
        for(unsigned e=0;e<sizeof exponents/sizeof *exponents;e++)
            for(unsigned m=0;m<sizeof fractions/sizeof *fractions;m++) {
                uint64_t mantissa=fractions[m];
                if(exponents[e]) mantissa|=UINT64_C(0x8000000000000000);
                else mantissa&=UINT64_C(0x7fffffffffffffff);
                check(((u128)sign<<79)|((u128)exponents[e]<<64)|mantissa);
            }
        u128 inf=((u128)sign<<79)|((u128)0x7fff<<64)|UINT64_C(0x8000000000000000);
        assert(isinf(fp_read(inf,10)) && fp_write(fp_read(inf,10),10)==inf);
        assert(isnan(fp_read(inf|UINT64_C(0x4000000000000000),10)));
        assert(isnan(fp_read(fp_write(sign ? -NAN : NAN,10),10)));
    }
    uint64_t rng=UINT64_C(0xb46d9e47a7621af3);
    for(unsigned i=0;i<100000;i++) {
        rng^=rng<<13; rng^=rng>>7; rng^=rng<<17;
        unsigned exponent=1+(rng%32766);
        check(((u128)(rng>>63)<<79)|((u128)exponent<<64)|rng|((u128)1<<63));
    }
    assert(fp_write(1.L,10)==(((u128)0x3fff<<64)|((u128)1<<63)));
    assert(fp_read(fp_write(1.25L,4),4)==1.25L);
    assert(fp_read(fp_write(-3.5L,8),8)==-3.5L);
    puts("x87 portability: boundaries, signed zeros, subnormals, infinities, NaNs and 100000 encodings passed");
    return 0;
}
