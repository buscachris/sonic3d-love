#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd -- "$project_dir"
mkdir -p research captures
temporary="$(mktemp -d /tmp/sonic3d-frontend-XXXXXXXX)"
server_pid=""
cleanup() {
    if [[ -n "$server_pid" ]]; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    rm -rf -- "$temporary"
}
trap cleanup EXIT
Xvfb -displayfd 3 -screen 0 1024x768x24 -nolisten tcp \
    3>"$temporary/display" >research/xvfb.log 2>&1 &
server_pid=$!
for ((attempt=0; attempt<100; attempt++)); do
    if [[ -s "$temporary/display" ]]; then break; fi
    if ! kill -0 "$server_pid" 2>/dev/null; then cat research/xvfb.log >&2; exit 1; fi
    sleep 0.1
done
if [[ ! -s "$temporary/display" ]]; then echo 'Xvfb did not start' >&2; exit 1; fi
export DISPLAY=":$(cat "$temporary/display")"
export SDL_VIDEODRIVER=x11 LIBGL_ALWAYS_SOFTWARE=1 ALSOFT_DRIVERS=null
export SONIC3D_SAVE_DIR="$temporary/saves"
export SONIC3D_TEST_ROOT="$project_dir"
mkdir -p "$SONIC3D_SAVE_DIR"
# Keep the test entrypoint and the real movie module/assets in one LÖVE source.
# A stored zip avoids relying on mounts outside LÖVE's source directory.
python3 - "$project_dir" "$temporary/movies.love" <<'PY'
import pathlib, sys, zipfile
root = pathlib.Path(sys.argv[1])
with zipfile.ZipFile(sys.argv[2], "w", compression=zipfile.ZIP_STORED) as archive:
    for name in ("main.lua", "conf.lua"):
        archive.write(root / "tests/love" / name, name)
    archive.write(root / "game/movie.lua", "movie.lua")
    for path in (root / "game/movies").rglob("*"):
        if path.is_file():
            archive.write(path, str(path.relative_to(root / "game")))
PY
timeout --kill-after=3 60 love "$temporary/movies.love" >research/frontend-movies.log 2>&1 || {
    cat research/frontend-movies.log >&2; exit 1;
}
cat research/frontend-movies.log
timeout --kill-after=3 60 love game --skip-movies --replay tests/gameplay.lua --quit-after 1700 \
    --capture "$project_dir/captures/love-gameplay.png" >research/frontend-gameplay.log 2>&1 || {
    cat research/frontend-gameplay.log >&2; exit 1;
}
cat research/frontend-gameplay.log
timeout --kill-after=3 30 love game --skip-movies --replay tests/exit.lua --quit-after 1200 \
    >research/frontend-exit.log 2>&1 || {
    cat research/frontend-exit.log >&2; exit 1;
}
if rg -q 'Sonic 3D: 1200 frames' research/frontend-exit.log; then
    echo 'Original Exit menu did not quit' >&2; exit 1
fi
cat research/frontend-exit.log
echo 'LÖVE movies, gameplay replay and original Exit menu passed.'
