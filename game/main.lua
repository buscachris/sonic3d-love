local bit = require("bit")
local Core = require("core")
local Audio = require("audio")
local Movie = require("movie")

local game, audio, movie, image, pixels
local accumulator, elapsed, focused = 0, 0, true
local options = {}
local step = 1 / 60

local function arguments(args)
    local i = 1
    while i <= #args do
        local name = args[i]
        if name == "--source" or name == "--quit-after" or name == "--capture" or name == "--replay" then
            i = i + 1
            options[name:sub(3)] = assert(args[i], "Missing value for " .. name)
        elseif name == "--skip-movies" or name == "--verbose" then options[name:sub(3)] = true
        end
        i = i + 1
    end
end

local function buttons()
    local result = 0
    local function key(mask, ...)
        if love.keyboard.isDown(...) then result = bit.bor(result, mask) end
    end
    key(1, "return", "kpenter", "escape")
    key(2, "a", "z")
    key(4, "b", "x")
    key(8, "c")
    key(16, "up")
    key(32, "down")
    key(64, "left")
    key(128, "right")
    key(256, "s")
    key(512, "d")
    key(1024, "f")
    for _, joystick in ipairs(love.joystick.getJoysticks()) do
        if joystick:isGamepad() then
            local function pad(mask, ...)
                if joystick:isGamepadDown(...) then result = bit.bor(result, mask) end
            end
            pad(1, "start"); pad(2, "a"); pad(4, "b"); pad(8, "x", "y")
            pad(16, "dpup"); pad(32, "dpdown"); pad(64, "dpleft"); pad(128, "dpright")
            local x, y = joystick:getGamepadAxis("leftx"), joystick:getGamepadAxis("lefty")
            if x < -0.35 then result = bit.bor(result, 64) elseif x > 0.35 then result = bit.bor(result, 128) end
            if y < -0.35 then result = bit.bor(result, 16) elseif y > 0.35 then result = bit.bor(result, 32) end
        end
    end
    return result
end

local function events()
    while true do
        local kind, a, b = game:poll()
        if not kind then return end
        if kind == 1 then audio:sound(a, b)
        elseif kind == 2 then audio:music(a, b)
        elseif kind == 3 then
            if a ~= 0 then
                if options["skip-movies"] then game:movieDone() else movie:start(game:movie()) end
            else movie:stop() end
        elseif kind == 4 then audio:stopSounds()
        end
    end
end

local function refresh()
    if not pixels or pixels:getWidth() ~= game.width or pixels:getHeight() ~= game.height then
        if image then image:release(); pixels:release() end
        pixels = love.image.newImageData(game.width, game.height, "rgba8")
        image = love.graphics.newImage(pixels)
        image:setFilter("nearest", "nearest")
    end
    game:copyPixels(pixels)
    image:replacePixels(pixels)
end

function love.load(args)
    arguments(args)
    local directory = love.filesystem.getSource()
    local source = options.source or os.getenv("SONIC3D_SOURCE") or directory .. "/../source"
    love.graphics.setDefaultFilter("nearest", "nearest")
    love.keyboard.setKeyRepeat(false)
    game = Core.new(source, options.verbose and 1 or 0)
    audio = Audio.new(game, source)
    movie = Movie.new(game)
    if options.replay then
        local file = assert(io.open(options.replay, "rb"))
        local program = file:read("*a"); file:close()
        options.replay = assert(loadstring(program, "@" .. options.replay))()
    end
    events()
    refresh()
end

function love.update(dt)
    if not focused then return end
    accumulator = accumulator + math.min(dt, 0.25)
    local updates = 0
    while accumulator >= step and updates < 15 do
        local keys = buttons()
        if type(options.replay) == "table" then
            keys = 0
            for _, press in ipairs(options.replay) do
                if elapsed >= press[1] and elapsed < press[1] + press[2] then keys = bit.bor(keys, press[3]) end
            end
        end
        game:step(keys)
        events()
        movie:update(step)
        elapsed, updates = elapsed + 1, updates + 1
        accumulator = accumulator - step
        if options["quit-after"] and elapsed >= tonumber(options["quit-after"]) then
            refresh()
            if options.capture then
                local encoded = pixels:encode("png")
                local file = assert(io.open(options.capture, "wb"))
                file:write(encoded:getString()); file:close(); encoded:release()
            end
            print(string.format("Sonic 3D: %d frames, state %d/%d", elapsed,
                                tonumber(game.info[0].state), tonumber(game.info[0].substate)))
            love.event.quit()
            return
        end
    end
    if updates > 0 then refresh() end
end

function love.draw()
    love.graphics.clear(0, 0, 0, 1)
    if not image then return end
    local width, height = love.graphics.getDimensions()
    local scale = math.min(width / game.width, height / game.height)
    if scale >= 1 then scale = math.floor(scale) end
    local x, y = math.floor((width - game.width * scale) / 2), math.floor((height - game.height * scale) / 2)
    love.graphics.push()
    love.graphics.translate(x, y)
    love.graphics.scale(scale, scale)
    love.graphics.setColor(1, 1, 1, 1)
    if movie.active then movie:draw(game.width, game.height) else love.graphics.draw(image) end
    love.graphics.pop()
end

function love.keypressed(key)
    if key == "f11" then love.window.setFullscreen(not love.window.getFullscreen(), "desktop") end
    if key == "q" and love.keyboard.isDown("lctrl", "rctrl") then love.event.quit() end
    if movie and movie.active and (key == "escape" or key == "return" or key == "space") then movie:finish() end
end

function love.focus(hasFocus)
    focused = hasFocus or options["quit-after"] ~= nil
    accumulator = 0
    if audio then
        if focused then audio:resume() else audio:pause() end
    end
end

function love.quit()
    if movie then movie:stop() end
    if audio then audio:close() end
    if game then game:close() end
end
