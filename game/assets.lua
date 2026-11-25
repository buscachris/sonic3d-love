-- The native PC game uses stdio, so Android assets must first be copied from
-- the APK to private app storage. Saves live beside this directory, not in it.
local Assets = {}
Assets.__index = Assets

function Assets.new()
    local manifest = require("android-assets")
    local self = setmetatable({manifest = manifest, index = 0, copied = 0}, Assets)
    self.root = love.filesystem.getSaveDirectory() .. "/source"
    self.ready = love.filesystem.read("source/.asset-version") == manifest.version
    if self.ready then
        for _, entry in ipairs(manifest.files) do
            local info = love.filesystem.getInfo("source/" .. entry.path, "file")
            if not info or info.size ~= entry.size then self.ready = false; break end
        end
    end
    return self
end

function Assets:step()
    if self.ready then return true end
    local entry = self.manifest.files[self.index + 1]
    if not entry then
        assert(love.filesystem.write("source/.asset-version", self.manifest.version))
        self.ready = true
        return true
    end
    local bytes = assert(love.filesystem.read("original/" .. entry.path))
    assert(#bytes == entry.size, "Incomplete packaged game data: " .. entry.path)
    local hash = love.data.encode("string", "hex", love.data.hash("sha256", bytes))
    assert(hash == entry.sha256, "Damaged packaged game data: " .. entry.path)
    local dest = "source/" .. entry.path
    assert(love.filesystem.createDirectory(dest:match("^(.*)/")))
    assert(love.filesystem.write(dest .. ".part", bytes))
    local save = love.filesystem.getSaveDirectory() .. "/"
    assert(os.rename(save .. dest .. ".part", save .. dest))
    self.index = self.index + 1
    self.copied = self.copied + entry.size
    return false
end

function Assets:progress()
    return self.ready and 1 or self.copied / math.max(1, self.manifest.bytes)
end

return Assets
