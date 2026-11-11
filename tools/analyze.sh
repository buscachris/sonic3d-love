#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "$0")/.." && pwd)"
mkdir -p "$project_dir/research/ghidra-project" "$project_dir/research/decomp"
exec /usr/libexec/ghidra/support/analyzeHeadless \
  "$project_dir/research/ghidra-project" Sonic3D \
  -import "$project_dir/source/PCSONIC.EXE" -overwrite \
  -scriptPath "$project_dir/tools" \
  -postScript ExportSonic.java "$project_dir/research/decomp" \
  -analysisTimeoutPerFile 600
