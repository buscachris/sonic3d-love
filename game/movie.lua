local Movie = {}
Movie.__index = Movie

function Movie.new(core)
    return setmetatable({core=core}, Movie)
end

function Movie:start(name)
    self:stop()
    if not self.index then
        assert(love.filesystem.getInfo("movies/index.lua"),
               "Movie frames are missing. Run python3 tools/prepare_movies.py in the project directory.")
        self.index = love.filesystem.load("movies/index.lua")()
    end
    local key = name:gsub("\\", "/"):match("([^/]+)%.[^.]+$"):lower()
    self.meta = assert(self.index[key], "Unknown original movie: " .. name)
    self.directory = "movies/" .. key
    self.time, self.frame = 0, 1
    self.image = love.graphics.newImage(self.directory .. "/000001.png")
    self.image:setFilter("nearest", "nearest")
    self.audio = love.audio.newSource(self.directory .. "/audio.wav", "stream")
    self.audio:play()
    self.active = true
end

function Movie:stop()
    if self.audio then self.audio:stop(); self.audio:release(); self.audio = nil end
    if self.image then self.image:release(); self.image = nil end
    self.active = false
end

function Movie:finish()
    self:stop()
    self.core:movieDone()
end

function Movie:update(dt)
    if not self.active then return end
    self.time = self.time + dt
    local frame = math.floor(self.time * self.meta.fps_n / self.meta.fps_d) + 1
    if frame > self.meta.frames then self:finish(); return end
    if frame ~= self.frame then
        local data = love.image.newImageData(string.format("%s/%06d.png", self.directory, frame))
        self.image:replacePixels(data)
        data:release()
        self.frame = frame
    end
end

function Movie:draw(width, height)
    -- The original MCI child movie is centered in the game client area.
    love.graphics.draw(self.image, math.floor((width - self.meta.width) / 2),
                       math.floor((height - self.meta.height) / 2))
end

return Movie
