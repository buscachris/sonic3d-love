# Sonic 3D Blast — LÖVE runtime experiment

An experimental Linux runtime and LÖVE frontend for the PC version of Sonic 3D Blast. Python tooling translates Ghidra instruction semantics into generated C; a native runtime provides platform services, and Lua handles presentation, input, audio and movies.

This is an incomplete development snapshot. It is not a complete reconstruction or a standalone game distribution. Original game data, executable-derived generated code and media are not included.

## Included source

- `game/*.lua`: LÖVE frontend and native-library bindings.
- `game/native/`: handwritten C runtime, platform hooks, API and headless runner.
- `tools/`: Ghidra scripts, C generation, movie preparation and inspection tools.
- `Makefile` and `play.sh`: current local build and launch entry points.

## Development requirements

The current scripts target Linux and require a C compiler supporting GNU C11, Make, Python 3, Bash, Ghidra with its Java runtime, and LÖVE 11.5 with LuaJIT FFI. Movie preparation also uses `ffmpeg` and `ffprobe`. Dependency versions beyond the LÖVE configuration have not been pinned or verified by this export.

The expected local data layout is:

```text
source/
  PCSONIC.EXE
  PCSONIC/             # original extracted game data, including CDDATA
research/
  pcode/
    instructions.jsonl
```

Supply original files locally from your own copy. No downloads of original game files are provided here. Keep these files and generated translations outside version control.

## Build status and local workflow

**A fresh checkout is not yet a reproducible build.** `make generate` expects `research/pcode/instructions.jsonl`, which is intentionally excluded. The Ghidra recovery and export procedure still needs end-to-end validation from a clean checkout.

`tools/analyze.sh` has a machine-specific Ghidra path and exports decompilation through `ExportSonic.java`; it does not export the P-code input required by `tools/recompile.py`. The separate `RecoverInitializers.java`, `RecoverComputedTargets.java` and `ExportPcode.java` scripts are included, but their complete invocation sequence is not yet documented or verified. `ExportPcode.java` takes an output directory argument.

Once matching original data and the required local P-code export exist, the current build commands are:

```sh
make generate
make -j2
python3 tools/prepare_movies.py
./play.sh
```

These commands describe the existing scripts; this export has not been built or played. `play.sh` builds the native library if absent and prepares movies if their index is absent. It does not generate C automatically. `make check` references `tests/test_core.py`, which was absent at snapshot time; that target is currently incomplete.

The frontend accepts `--source /path/to/extracted-data` or `SONIC3D_SOURCE`. Movie preparation has its own `--source` option. The launcher still prepares movies from the default local `source/` directory, so prepare movies explicitly before using an external data path. `tools/inventory.py` also retains a machine-specific default ISO path; pass an explicit `--iso` when using it.

## Controls

| Input | Mapping |
|---|---|
| Arrow keys | Direction |
| Enter / Escape | Start |
| A / Z | A button |
| B / X | B button |
| C | C button |
| F11 | Toggle fullscreen |
| Ctrl+Q | Quit |

Gamepads are supported by the frontend. Enter, Escape or Space skips an active movie.

## Verification and remaining work

Only static checks of this export are recorded in the accompanying preparation report. No gameplay acceptance, Ghidra integration, native linking or full-game completion is claimed here.

Before a release: document and validate clean data extraction and code generation, restore or replace the missing test target, verify gameplay and save paths, establish dependency versions, and decide licensing and attribution for the selected source.

See [NOTICE.md](NOTICE.md) for the current distribution and licensing status.
