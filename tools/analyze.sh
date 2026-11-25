#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "$0")/.." && pwd)"
executable="$project_dir/source/PCSONIC.EXE"
output="$project_dir/research/pcode"
workspace=""
decompile=false
while (($#)); do
    case "$1" in
        --exe) executable="$2"; shift 2 ;;
        --output) output="$2"; shift 2 ;;
        --workspace) workspace="$2"; shift 2 ;;
        --decompile) decompile=true; shift ;;
        *) echo "Usage: $0 [--exe FILE] [--output DIR] [--workspace NEW_DIR] [--decompile]" >&2; exit 2 ;;
    esac
done
analyzer="${ANALYZE_HEADLESS:-${GHIDRA_HOME:+$GHIDRA_HOME/support/analyzeHeadless}}"
if [[ -z "$analyzer" ]]; then
    analyzer="$(command -v analyzeHeadless || true)"
fi
if [[ -z "$analyzer" && -x /usr/libexec/ghidra/support/analyzeHeadless ]]; then
    analyzer=/usr/libexec/ghidra/support/analyzeHeadless
fi
if [[ ! -x "$analyzer" ]]; then
    echo 'Set GHIDRA_HOME or ANALYZE_HEADLESS to a Ghidra installation (Java 21+).' >&2
    exit 1
fi
mkdir -p "$project_dir/research" "$output"
if [[ -z "$workspace" ]]; then
    workspace="$(mktemp -d "$project_dir/research/ghidra-build-XXXXXXXX")"
else
    # Never replace an existing analysis project.
    mkdir -- "$workspace"
fi
"$analyzer" "$workspace" Sonic3D \
    -import "$executable" -scriptPath "$project_dir/tools" \
    -postScript RecoverInitializers.java -analysisTimeoutPerFile 600
# The first invocation completes analysis of the recovered initializer functions.
# Then recover the inline jump tables before exporting the final instruction set.
extra=()
if [[ "$decompile" == true ]]; then
    mkdir -p "$project_dir/research/decomp"
    extra=(-postScript ExportSonic.java "$project_dir/research/decomp")
fi
"$analyzer" "$workspace" Sonic3D \
    -process "$(basename -- "$executable")" -noanalysis -scriptPath "$project_dir/tools" \
    -postScript RecoverComputedTargets.java \
    -postScript ExportPcode.java "$output" "${extra[@]}"
