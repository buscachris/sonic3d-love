function love.conf(t)
    t.identity = "sonic3d-frontend-tests"
    t.window.title = "Sonic 3D frontend checks"
    t.window.width, t.window.height = 320, 224
    t.window.vsync = 0
    t.modules.physics = false
    t.modules.video = false
end
