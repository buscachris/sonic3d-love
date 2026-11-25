local bit = require("bit")
local Touch = {enabled = false}

-- Coordinates are in LÖVE's logical pixels, like love.touch.getPosition.
function Touch.layout()
    local width, height = love.graphics.getDimensions()
    local left, top, safeWidth, safeHeight = love.window.getSafeArea()
    if safeWidth <= 0 or safeHeight <= 0 then
        left, top, safeWidth, safeHeight = 0, 0, width, height
    end
    local u = math.min(safeWidth / 800, safeHeight / 480)
    local right, bottom = left + safeWidth, top + safeHeight
    return {
        unit = u,
        dpad = {x = left + 100 * u, y = bottom - 106 * u, r = 80 * u},
        buttons = {
            {label = "A", mask = 0x02, x = right - 204 * u, y = bottom - 82 * u, r = 33 * u},
            {label = "B", mask = 0x04, x = right - 125 * u, y = bottom - 112 * u, r = 33 * u},
            {label = "C", mask = 0x08, x = right - 46 * u, y = bottom - 142 * u, r = 33 * u},
            {label = "START", mask = 0x01, x = right - 90 * u, y = top + 44 * u, w = 104 * u, h = 44 * u},
        },
    }
end

function Touch.read()
    if not Touch.enabled then return 0 end
    local layout, pad = Touch.layout(), 0
    for _, id in ipairs(love.touch.getTouches()) do
        local x, y = love.touch.getPosition(id)
        local d = layout.dpad
        local dx, dy = (x - d.x) / d.r, (y - d.y) / d.r
        if dx * dx + dy * dy <= 1.2 * 1.2 then
            if dx < -0.30 then pad = bit.bor(pad, 0x40) end
            if dx > 0.30 then pad = bit.bor(pad, 0x80) end
            if dy < -0.30 then pad = bit.bor(pad, 0x10) end
            if dy > 0.30 then pad = bit.bor(pad, 0x20) end
        end
        for _, button in ipairs(layout.buttons) do
            local bx, by = x - button.x, y - button.y
            local inside
            if button.r then
                inside = bx * bx + by * by <= (button.r + 5 * layout.unit) ^ 2
            else
                inside = math.abs(bx) <= button.w / 2 and math.abs(by) <= button.h / 2
            end
            if inside then pad = bit.bor(pad, button.mask) end
        end
    end
    return pad
end

function Touch.draw()
    if not Touch.enabled then return end
    local g, layout, pad = love.graphics, Touch.layout(), Touch.read()
    local u, d = layout.unit, layout.dpad
    g.push("all")
    g.setLineWidth(2 * u)
    g.setColor(0, 0, 0, 0.35)
    g.circle("fill", d.x, d.y, d.r)
    g.setColor(1, 1, 1, 0.55)
    g.circle("line", d.x, d.y, d.r)
    local arrows = {
        {0x10, 0, -1}, {0x20, 0, 1}, {0x40, -1, 0}, {0x80, 1, 0},
    }
    for _, arrow in ipairs(arrows) do
        local dx, dy = arrow[2], arrow[3]
        local x, y = d.x + dx * d.r * 0.6, d.y + dy * d.r * 0.6
        g.setColor(1, 1, 1, bit.band(pad, arrow[1]) ~= 0 and 1 or 0.55)
        g.polygon("fill", x + dx * 13 * u, y + dy * 13 * u,
            x - dx * 8 * u - dy * 12 * u, y - dy * 8 * u + dx * 12 * u,
            x - dx * 8 * u + dy * 12 * u, y - dy * 8 * u - dx * 12 * u)
    end
    local font = g.getFont()
    for _, button in ipairs(layout.buttons) do
        local down = bit.band(pad, button.mask) ~= 0
        g.setColor(down and 0.15 or 0, down and 0.45 or 0, down and 0.75 or 0, down and 0.75 or 0.40)
        if button.r then
            g.circle("fill", button.x, button.y, button.r)
        else
            g.rectangle("fill", button.x - button.w / 2, button.y - button.h / 2, button.w, button.h, 10 * u)
        end
        g.setColor(1, 1, 1, down and 1 or 0.75)
        if button.r then
            g.circle("line", button.x, button.y, button.r)
        else
            g.rectangle("line", button.x - button.w / 2, button.y - button.h / 2, button.w, button.h, 10 * u)
        end
        local textScale = (button.r and 20 or 14) * u / font:getHeight()
        g.print(button.label, button.x - font:getWidth(button.label) * textScale / 2,
            button.y - font:getHeight() * textScale / 2, 0, textScale, textScale)
    end
    g.pop()
end

return Touch
