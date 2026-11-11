"""Headless inspection and deterministic replay of the native game core."""
from __future__ import annotations

import ctypes as C
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START, A, B, C_BUTTON, UP, DOWN, LEFT, RIGHT = (1 << i for i in range(8))


class Info(C.Structure):
    _fields_ = [("frame", C.c_uint64), ("blocks", C.c_uint64),
                ("width", C.c_uint32), ("height", C.c_uint32),
                ("state", C.c_int32), ("substate", C.c_int32),
                ("movie_playing", C.c_uint32), ("music_track", C.c_uint32)]


class Event(C.Structure):
    _fields_ = [(key, C.c_uint32) for key in ("type", "a", "b", "c")]


class Game:
    def __init__(self, source=ROOT / "source", verbose=0, skip_movies=True):
        self.lib = C.CDLL(str(ROOT / "game/libsonic3d.so"))
        types = {
            "create": (C.c_void_p, [C.c_char_p, C.c_int]),
            "destroy": (None, [C.c_void_p]),
            "step": (C.c_int, [C.c_void_p, C.c_uint32]),
            "pixels": (C.c_void_p, [C.c_void_p]),
            "error": (C.c_char_p, [C.c_void_p]),
            "info": (None, [C.c_void_p, C.POINTER(Info)]),
            "poll_event": (C.c_int, [C.c_void_p, C.POINTER(Event)]),
            "movie_done": (None, [C.c_void_p]),
            "read": (C.c_uint32, [C.c_void_p, C.c_uint32, C.c_uint]),
            "write": (C.c_int, [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint]),
            "call": (C.c_int, [C.c_void_p] + [C.c_uint32] * 5),
            "register": (C.c_uint32, [C.c_void_p, C.c_uint]),
            "copy_memory": (C.c_int, [C.c_void_p, C.c_uint32, C.c_void_p, C.c_uint]),
            "trace": (C.c_uint, [C.c_void_p, C.POINTER(C.c_uint32), C.c_uint]),
        }
        for name, (result, args) in types.items():
            fn = getattr(self.lib, "sonic3d_" + name)
            fn.restype, fn.argtypes = result, args
        self.handle = self.lib.sonic3d_create(str(source).encode(), verbose)
        self.skip_movies = skip_movies
        self.events = []
        self.check()

    def close(self):
        if self.handle:
            self.lib.sonic3d_destroy(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def check(self):
        error = self.lib.sonic3d_error(self.handle)
        if error:
            trace = (C.c_uint32 * 256)()
            n = self.lib.sonic3d_trace(self.handle, trace, 256) if self.handle else 0
            raise RuntimeError(error.decode() + "\nLast blocks: " + " ".join(f"{p:08x}" for p in trace[:n]))

    @property
    def info(self):
        result = Info()
        self.lib.sonic3d_info(self.handle, C.byref(result))
        return result

    @property
    def state(self):
        i = self.info
        return i.state, i.substate

    def step(self, keys=0, frames=1):
        for _ in range(frames):
            if not self.lib.sonic3d_step(self.handle, keys):
                self.check()
            event = Event()
            while self.lib.sonic3d_poll_event(self.handle, C.byref(event)):
                self.events.append((self.info.frame, event.type, event.a, event.b, event.c))
                if event.type == 3 and event.a and self.skip_movies:
                    self.lib.sonic3d_movie_done(self.handle)
        return self.state

    def until(self, predicate, limit=4000, keys=0):
        for _ in range(limit):
            if predicate(self):
                return
            self.step(keys)
        raise TimeoutError(f"Condition not reached at frame {self.info.frame}, state {self.state}")

    def read(self, address, size=4):
        value = self.lib.sonic3d_read(self.handle, address, size)
        self.check()
        return value

    def be(self, address, size=2, signed=False):
        return int.from_bytes(self.memory(address, size), "big", signed=signed)

    def write(self, address, value, size=4):
        if not self.lib.sonic3d_write(self.handle, address, value, size):
            self.check()

    def write_be(self, address, value, size=2):
        self.write(address, int.from_bytes(value.to_bytes(size, "big", signed=value < 0), "little"), size)

    def memory(self, address, size):
        buf = C.create_string_buffer(size)
        if not self.lib.sonic3d_copy_memory(self.handle, address, buf, size):
            self.check()
        return buf.raw

    def call(self, address, eax=0, edx=0, ebx=0, ecx=0):
        if not self.lib.sonic3d_call(self.handle, address, eax, edx, ebx, ecx):
            self.check()
        return self.lib.sonic3d_register(self.handle, 0)

    @property
    def pixels(self):
        i = self.info
        return C.string_at(self.lib.sonic3d_pixels(self.handle), i.width * i.height * 4)

    def capture(self, path):
        from PIL import Image
        i = self.info
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.frombytes("RGBA", (i.width, i.height), self.pixels).save(path)

    def new_game(self, level=1):
        """Drive New Game through the original title; select its existing level index."""
        self.until(lambda g: g.state == (1, 6))
        self.step(frames=120)
        self.write(0x4bdf00, level)
        self.step(START)
        self.step()
        self.until(lambda g: g.info.state == 10000)
        self.until(lambda g: g.read(0x61071c) == 0, limit=600)
        self.step(frames=10)

    @property
    def sonic(self):
        p = self.read(0x4d0028)
        return {"address": p, "x": self.be(p + 8, 4, True),
                "y": self.be(p + 12, 4, True), "z": self.be(p + 16, 4, True)}
