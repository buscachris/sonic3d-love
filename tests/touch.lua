package.path = "game/?.lua;" .. package.path
local touches = {}
local width, height, inset = 800, 360, 0
love = {
    graphics = {getDimensions = function() return width, height end},
    window = {getSafeArea = function() return inset, 0, width - inset, height end},
    touch = {
        getTouches = function()
            local ids = {}
            for id in pairs(touches) do ids[#ids + 1] = id end
            return ids
        end,
        getPosition = function(id) return unpack(touches[id]) end,
    },
}
local Touch = require("touch")
local function expect(wanted, message)
    assert(Touch.read() == wanted, message .. ": " .. Touch.read() .. " ~= " .. wanted)
end
for _, size in ipairs({{2400, 1080}, {800, 360}, {960, 672}}) do
    width, height = unpack(size)
    inset = width * 0.025
    Touch.enabled = true
    local layout = Touch.layout()
    local d, a, b, c, start = layout.dpad, unpack(layout.buttons)
    touches = {move = {d.x + d.r * 0.7, d.y}, jump = {b.x, b.y}}
    expect(0x84, "right and B together")
    touches.move = {d.x - d.r * 0.6, d.y + d.r * 0.6}
    expect(0x64, "diagonal and B together")
    touches.jump = nil
    expect(0x60, "releasing B keeps direction held")
    touches.move = {d.x, d.y}
    expect(0, "neutral dpad")
    touches = {outside = {width / 2, height / 2}}
    expect(0, "game view does not press controls")
    touches = {a = {a.x, a.y}, c = {c.x, c.y}, start = {start.x, start.y}}
    expect(0x0b, "A C and Start use the original PC button bits")
    Touch.enabled = false
    expect(0, "desktop touch disabled")
    Touch.enabled = true
    touches = {}
    expect(0, "no stale input after release")
end
print("Sonic 3D touch controls passed at three sizes, with cutout insets and multitouch")
