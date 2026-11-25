-- Run under an isolated X server with tools/check_frontend.sh.
function love.errorhandler(message)
    io.stderr:write(debug.traceback(tostring(message), 2) .. "\n")
    io.stderr:flush()
    return function() return 1 end
end

function love.load(args)
    local root = assert(os.getenv("SONIC3D_TEST_ROOT"), "Set SONIC3D_TEST_ROOT")
    package.path = package.path .. ";" .. root .. "/game/?.lua"
    local Movie = require("movie")
    local completed = 0
    local movie = Movie.new({movieDone=function() completed = completed + 1 end})
    local canvas = love.graphics.newCanvas(320, 224)
    love.graphics.setDefaultFilter("nearest", "nearest")
    for index, name in ipairs({"SO3DOP", "SO3DEDA", "SO3DEDB"}) do
        movie:start("CDDATA\\" .. name .. ".AVI")
        assert(movie.active and movie.audio:isPlaying(), "Movie audio did not start")
        assert(movie.audio:getDuration() > 20, "Incomplete movie audio")
        movie:update(1)
        assert(movie.frame == 16, "Incorrect 15 fps playback")
        love.graphics.setCanvas(canvas)
        love.graphics.clear(0, 0, 0, 1)
        love.graphics.setColor(1, 1, 1, 1)
        movie:draw(320, 224)
        love.graphics.setCanvas()
        local actual = canvas:newImageData()
        local expected = love.image.newImageData("movies/" .. name:lower() .. "/000016.png")
        -- Verify centering, nearest-neighbor output, and the decoded RGB pixels.
        for y = 0, 223 do
            for x = 0, 319 do
                local r, g, b, a = actual:getPixel(x, y)
                local er, eg, eb = 0, 0, 0
                if x >= 20 and x < 300 and y >= 32 and y < 192 then
                    er, eg, eb = expected:getPixel(x - 20, y - 32)
                end
                assert(math.abs(r-er) < 1/256 and math.abs(g-eg) < 1/256 and
                       math.abs(b-eb) < 1/256 and a == 1, "Movie pixels differ")
            end
        end
        local png = actual:encode("png")
        local file = assert(io.open(root .. "/captures/movie-" .. name:lower() .. ".png", "wb"))
        file:write(png:getString()); file:close()
        png:release(); actual:release(); expected:release()
        while movie.active do movie:update(8) end
        assert(completed == index and not movie.audio and not movie.image, "Movie completion/cleanup failed")
        print(name .. ": PCM audio, frame 16 pixels, centering and completion OK")
    end
    movie:start("SO3DOP.AVI")
    movie:finish()
    assert(completed == 4 and not movie.active, "Movie skip failed")
    canvas:release()
    love.event.quit(0)
end
