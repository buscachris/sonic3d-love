local bit = require("bit")
local Audio = {}
Audio.__index = Audio

local function fileData(path)
    local file, message = io.open(path, "rb")
    assert(file, message)
    local bytes = file:read("*a")
    file:close()
    return love.filesystem.newFileData(bytes, path:match("[^/]+$"))
end

function Audio.new(core, source)
    return setmetatable({core=core, source=source, sounds={}, paused={}}, Audio)
end

function Audio:sound(slot, flags)
    local name = self.core:sound(slot)
    if name == "" then return end
    local sound = self.sounds[name]
    if not sound then
        local path = self.core:assetPath(name)
        local data = fileData(path)
        sound = {data=love.sound.newSoundData(data), voices={}}
        data:release()
        self.sounds[name] = sound
    end
    -- DirectSound's original bank has twelve independent buffers per effect.
    local voice
    for _, candidate in ipairs(sound.voices) do
        if not candidate:isPlaying() then voice = candidate; break end
    end
    if not voice and #sound.voices < 12 then
        voice = love.audio.newSource(sound.data, "static")
        sound.voices[#sound.voices + 1] = voice
    end
    if voice then
        voice:stop()
        voice:setLooping(bit.band(flags, 1) ~= 0)
        voice:play()
    end
end

function Audio:stopSounds()
    for _, sound in pairs(self.sounds) do
        for _, voice in ipairs(sound.voices) do voice:stop(); voice:release() end
        sound.data:release()
    end
    self.sounds = {}
end

function Audio:music(track, seconds)
    if self.bgm then self.bgm:stop(); self.bgm:release(); self.bgm = nil end
    if track == 0 then return end
    local name = self.source .. string.format("/Music/%02d.ogg", track)
    local data = fileData(name)
    self.bgm = love.audio.newSource(data, "stream")
    data:release()
    if seconds > 0 then self.bgm:seek(seconds, "seconds") end
    -- Track restarts and pause/resume seeks come from the original CD routines.
    self.bgm:play()
end

function Audio:pause()
    self.paused = love.audio.pause()
end

function Audio:resume()
    for _, source in ipairs(self.paused) do source:play() end
    self.paused = {}
end

function Audio:close()
    self:stopSounds()
    if self.bgm then self.bgm:stop(); self.bgm:release(); self.bgm = nil end
end

return Audio
