local ffi = require("ffi")
ffi.cdef [[
typedef struct Sonic3D Sonic3D;
typedef struct { uint32_t type,a,b,c; } Sonic3DEvent;
typedef struct {
    uint64_t frame,blocks;
    uint32_t width,height;
    int32_t state,substate;
    uint32_t movie_playing,music_track;
} Sonic3DInfo;
Sonic3D *sonic3d_create(const char *,int);
void sonic3d_destroy(Sonic3D *);
int sonic3d_step(Sonic3D *,uint32_t);
const uint8_t *sonic3d_pixels(Sonic3D *);
const char *sonic3d_error(Sonic3D *);
void sonic3d_info(Sonic3D *,Sonic3DInfo *);
int sonic3d_poll_event(Sonic3D *,Sonic3DEvent *);
const char *sonic3d_sound(Sonic3D *,uint32_t);
const char *sonic3d_movie(Sonic3D *);
void sonic3d_movie_done(Sonic3D *);
int sonic3d_asset_path(Sonic3D *,const char *,char *,unsigned);
]]

local Core = {}
Core.__index = Core

function Core.new(source, verbose)
    local self = setmetatable({}, Core)
    local directory = love.filesystem.getSource()
    self.lib = ffi.load(directory .. "/libsonic3d.so")
    self.handle = self.lib.sonic3d_create(source, verbose or 0)
    assert(self.handle ~= nil, "Unable to allocate the native game core")
    ffi.gc(self.handle, self.lib.sonic3d_destroy)
    self.event = ffi.new("Sonic3DEvent[1]")
    self.info = ffi.new("Sonic3DInfo[1]")
    self.pathBuffer = ffi.new("char[4096]")
    self:check()
    self:updateInfo()
    return self
end

function Core:check()
    local message = self.lib.sonic3d_error(self.handle)
    if message ~= nil and message[0] ~= 0 then error(ffi.string(message), 2) end
end

function Core:updateInfo()
    self.lib.sonic3d_info(self.handle, self.info)
    self.width, self.height = tonumber(self.info[0].width), tonumber(self.info[0].height)
end

function Core:step(buttons)
    if self.lib.sonic3d_step(self.handle, buttons) == 0 then self:check() end
    self:updateInfo()
end

function Core:poll()
    if self.lib.sonic3d_poll_event(self.handle, self.event) == 0 then return end
    local event = self.event[0]
    return tonumber(event.type), tonumber(event.a), tonumber(event.b), tonumber(event.c)
end

function Core:copyPixels(data)
    ffi.copy(data:getFFIPointer(), self.lib.sonic3d_pixels(self.handle), self.width * self.height * 4)
end

function Core:sound(slot)
    return ffi.string(self.lib.sonic3d_sound(self.handle, slot))
end

function Core:movie()
    return ffi.string(self.lib.sonic3d_movie(self.handle))
end

function Core:movieDone()
    self.lib.sonic3d_movie_done(self.handle)
end

function Core:assetPath(name)
    if self.lib.sonic3d_asset_path(self.handle, name, self.pathBuffer, 4096) == 0 then
        error("Original game asset missing: " .. name, 2)
    end
    return ffi.string(self.pathBuffer)
end

function Core:close()
    if self.handle ~= nil then
        ffi.gc(self.handle, nil)
        self.lib.sonic3d_destroy(self.handle)
        self.handle = nil
    end
end

return Core
