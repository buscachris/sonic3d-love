CC ?= cc
PYTHON ?= python3
CFLAGS ?= -O1 -g -std=gnu11 -fPIC -fno-strict-aliasing -fwrapv
CFLAGS += -Wall -Wno-unused-variable -Wno-unused-but-set-variable -Wno-unused-label -Wno-parentheses -Wno-type-limits
LDFLAGS ?=
GEN := $(wildcard game/native/generated/page_*.c) game/native/generated/dispatch.c
OBJ := $(GEN:.c=.o) game/native/vm.o game/native/platform.o game/native/api.o

.PHONY: all generate clean check
all: game/libsonic3d.so game/sonic3d-headless

generate:
	$(PYTHON) tools/recompile.py

game/native/generated/%.o: game/native/generated/%.c game/native/vm.h
	$(CC) $(CFLAGS) -c $< -o $@

game/native/%.o: game/native/%.c game/native/vm.h
	$(CC) $(CFLAGS) -c $< -o $@

game/libsonic3d.so: $(OBJ)
	$(CC) -shared $(LDFLAGS) -o $@ $^ -lm

game/sonic3d-headless: game/native/headless.c game/libsonic3d.so
	$(CC) -std=gnu11 -g -O2 -o $@ $< -Lgame -lsonic3d -Wl,-rpath,'$$ORIGIN'

check: all
	$(PYTHON) tests/test_core.py

clean:
	$(RM) game/native/*.o game/native/generated/*.o game/libsonic3d.so game/sonic3d-headless
