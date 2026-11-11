#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$project_dir"
if [[ ! -f game/libsonic3d.so ]]; then
    make -j2
fi
if [[ ! -f game/movies/index.lua ]]; then
    python3 tools/prepare_movies.py
fi
exec love "$project_dir/game" "$@"
