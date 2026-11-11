function love.conf(t)
    t.identity = "sonic3d-native"
    t.version = "11.5"
    t.window.title = "Sonic 3D Blast"
    t.window.width = 960
    t.window.height = 672
    t.window.minwidth = 320
    t.window.minheight = 224
    t.window.resizable = true
    t.window.vsync = 1
    t.window.highdpi = true
    t.modules.physics = false
    t.modules.video = false
end
