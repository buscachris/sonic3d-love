function love.conf(t)
    local system = require("love.system")
    local mobile = system.getOS() == "Android" or system.getOS() == "iOS"
    t.identity = "sonic3d-native"
    t.version = "11.5"
    t.window.title = "Sonic 3D Blast"
    t.window.icon = "icons/sonic.png"
    t.window.width = 960
    t.window.height = 672
    t.window.minwidth = 320
    t.window.minheight = 224
    t.window.resizable = not mobile
    t.window.fullscreen = mobile
    t.window.vsync = 1
    t.window.highdpi = not mobile
    t.modules.physics = false
    t.modules.video = false
end
