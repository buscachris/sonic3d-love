#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$project_dir"
make --no-print-directory -s -j2
skip_movies=false
for argument in "$@"; do
    if [[ "$argument" == --skip-movies ]]; then skip_movies=true; fi
done
if [[ "$skip_movies" == false && ! -f game/movies/index.lua ]]; then
    python3 tools/prepare_movies.py
fi
exec love "$project_dir/game" "$@"
