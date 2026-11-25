CC ?= cc
PYTHON ?= python3
CFLAGS ?= -O1 -g -std=gnu11 -fPIC -fno-strict-aliasing -fwrapv
CFLAGS += -Wall -Wno-unused-variable -Wno-unused-but-set-variable -Wno-unused-label -Wno-parentheses -Wno-type-limits
LDFLAGS ?=
BUILD ?= game
GEN := $(wildcard game/native/generated/page_*.c) game/native/generated/dispatch.c
OBJ := $(patsubst game/%.c,$(BUILD)/%.o,$(GEN)) $(BUILD)/native/vm.o $(BUILD)/native/platform.o $(BUILD)/native/api.o

.PHONY: all generate clean check android
all: $(BUILD)/libsonic3d.so $(BUILD)/sonic3d-headless

generate:
	$(PYTHON) tools/recompile.py

$(BUILD)/native/generated/%.o: game/native/generated/%.c game/native/vm.h
	@mkdir -p $(@D)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/native/%.o: game/native/%.c game/native/vm.h
	@mkdir -p $(@D)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/libsonic3d.so: $(OBJ)
	$(CC) -shared $(LDFLAGS) -o $@ $^ -lm

$(BUILD)/sonic3d-headless: game/native/headless.c $(BUILD)/libsonic3d.so
	$(CC) -std=gnu11 -g -O2 -o $@ $< -L$(BUILD) -lsonic3d -Wl,-rpath,'$$ORIGIN'

check: all
	$(PYTHON) tests/test_core.py
	$(CC) -std=gnu11 -O2 -o $(BUILD)/test-x87 tests/test_x87.c -lm
	$(BUILD)/test-x87
	luajit tests/touch.lua
	luajit tests/assets.lua

android:
	$(PYTHON) tools/build_android.py

clean:
	$(RM) $(BUILD)/native/*.o $(BUILD)/native/generated/*.o $(BUILD)/libsonic3d.so $(BUILD)/sonic3d-headless $(BUILD)/test-x87
