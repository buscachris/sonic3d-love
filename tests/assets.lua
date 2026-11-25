-- Exercise interrupted installs and updates without touching a player's files.
package.path = "game/?.lua;" .. package.path
local Assets = require("assets")
local manifest = {version = "version-one", bytes = 16, files = {
    {path = "PCSONIC.EXE", size = 6, sha256 = "hash-engine"},
    {path = "PCSONIC/LEVEL.BIN", size = 5, sha256 = "hash-level"},
    {path = "Music/01.ogg", size = 5, sha256 = "hash-music"},
}}
package.loaded["android-assets"] = manifest
local packaged = {
    ["original/PCSONIC.EXE"] = "engine",
    ["original/PCSONIC/LEVEL.BIN"] = "level",
    ["original/Music/01.ogg"] = "music",
}
local hashes = {engine = "hash-engine", level = "hash-level", music = "hash-music"}
local saved, writes, packageReads, failWrite, failRename
local function reset()
    saved = {["saves/pcsonic.sav"] = "existing progress"}
    writes, packageReads, failWrite, failRename = 0, 0, nil, false
    manifest.version = "version-one"
    packaged["original/PCSONIC.EXE"] = "engine"
end
love = {
    filesystem = {
        getSaveDirectory = function() return "/private/game" end,
        read = function(path)
            if packaged[path] then packageReads = packageReads + 1; return packaged[path] end
            return saved[path]
        end,
        getInfo = function(path, kind)
            assert(kind == "file")
            return saved[path] and {size = #saved[path]} or nil
        end,
        createDirectory = function(path) assert(path:match("^source")); return true end,
        write = function(path, bytes)
            if path == failWrite then return false, "simulated disk full" end
            writes = writes + 1
            saved[path] = bytes
            return true
        end,
    },
    data = {
        hash = function(algorithm, bytes)
            assert(algorithm == "sha256")
            return hashes[bytes] or "wrong-hash"
        end,
        encode = function(container, encoding, hash)
            assert(container == "string" and encoding == "hex")
            return hash
        end,
    },
}
local realRename = os.rename
os.rename = function(from, to)
    if failRename then return nil, "simulated interruption" end
    from = assert(from:match("^/private/game/(.+)$"))
    to = assert(to:match("^/private/game/(.+)$"))
    assert(saved[from] and from == to .. ".part", "copy must be installed atomically")
    saved[to], saved[from] = saved[from], nil
    return true
end
local function complete(assets)
    for _ = 1, #manifest.files + 1 do if assets:step() then break end end
    assert(assets.ready and assets:progress() == 1)
    assert(saved["source/.asset-version"] == manifest.version)
    assert(saved["saves/pcsonic.sav"] == "existing progress", "install must preserve saves")
    for _, entry in ipairs(manifest.files) do
        assert(saved["source/" .. entry.path] == packaged["original/" .. entry.path])
        assert(not saved["source/" .. entry.path .. ".part"])
    end
end

reset()
local first = Assets.new()
assert(not first.ready and first.root == "/private/game/source" and first:progress() == 0)
assert(not first:step() and first:progress() == 6 / 16)
assert(not saved["source/.asset-version"], "version marker must be written last")
complete(first)
local previousWrites, previousReads = writes, packageReads
local cached = Assets.new()
assert(cached.ready and cached:step())
assert(writes == previousWrites and packageReads == previousReads, "valid install must not recopy")

saved["source/PCSONIC/LEVEL.BIN"] = nil
local missing = Assets.new()
assert(not missing.ready)
complete(missing)
saved["source/Music/01.ogg"] = "truncated"
local truncated = Assets.new()
assert(not truncated.ready)
complete(truncated)
manifest.version = "version-two"
local updated = Assets.new()
assert(not updated.ready)
complete(updated)

reset()
packaged["original/PCSONIC.EXE"] = "broken" -- Same length; checksum must detect it.
assert(not pcall(function() Assets.new():step() end))
assert(not saved["source/PCSONIC.EXE"] and not saved["source/.asset-version"])
packaged["original/PCSONIC.EXE"] = "engine"
complete(Assets.new())

reset()
failWrite = "source/PCSONIC.EXE.part"
assert(not pcall(function() Assets.new():step() end))
assert(not saved["source/.asset-version"])
failWrite = nil
complete(Assets.new())

reset()
failRename = true
assert(not pcall(function() Assets.new():step() end))
assert(saved["source/PCSONIC.EXE.part"] and not saved["source/PCSONIC.EXE"])
assert(not saved["source/.asset-version"])
failRename = false
complete(Assets.new())

reset()
failWrite = "source/.asset-version"
assert(not pcall(function() complete(Assets.new()) end))
assert(not saved["source/.asset-version"])
failWrite = nil
complete(Assets.new())
os.rename = realRename
print("Android assets: first launch, cache, repair, update, checksum, interruption and save preservation passed")
