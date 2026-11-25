#!/usr/bin/env python3
"""Build the native Sonic 3D core from the supplied, unmodified PC disc."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ISO_SHA256 = "6f1d49b2cde457e3b195f9f2bc7f618179ce3d0e2f290c07c14d3fe2f8f197f2"
EXE_SHA256 = "2cb33a8629e1de8c4f9688123a35f6c0bffb5ba53f05f75a3e2aae8c1e3a25dd"


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def verify_source(source):
    executable = source / "PCSONIC.EXE"
    if not executable.is_file() or digest(executable) != EXE_SHA256:
        raise RuntimeError("Unsupported PCSONIC.EXE; this translation requires the supplied disc version. "
                           "Existing source files have been left untouched.")
    for path in ("PCSONIC/CDDATA", "PCSONIC/SYSTEM/NEW.LBM", "Music/02.ogg"):
        if not (source / path).exists():
            raise RuntimeError(f"Incomplete original data directory: missing {path}")


def run(*command):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso", type=Path, default=ROOT.parent / "Sonic3D.iso")
    parser.add_argument("--source", type=Path, default=ROOT / "source")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--analyze", action="store_true", help="regenerate instruction semantics in a new Ghidra project")
    parser.add_argument("--skip-movies", action="store_true", help="omit movie decoding; play with --skip-movies")
    args = parser.parse_args()
    source = args.source.resolve()
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    if not source.exists():
        iso = args.iso.resolve()
        if not iso.is_file() or digest(iso) != ISO_SHA256:
            raise RuntimeError("Expected the supplied Sonic3D.iso. Pass --iso PATH, or --source an existing extraction.")
        unpack = shutil.which("7z") or shutil.which("7zz")
        if not unpack:
            raise RuntimeError("7-Zip (7z or 7zz) is required to extract the disc.")
        source.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".sonic3d-extract-", dir=source.parent) as temporary:
            run(unpack, "x", "-y", f"-o{temporary}", iso)
            verify_source(Path(temporary))
            Path(temporary).rename(source)
            # TemporaryDirectory cleanup also accepts its directory being moved.
    verify_source(source)
    instructions = ROOT / "research/pcode/instructions.jsonl"
    if args.analyze or not instructions.exists():
        (ROOT / "research").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="pcode-", dir=ROOT / "research") as temporary:
            output = Path(temporary) / "pcode"
            run("bash", ROOT / "tools/analyze.sh", "--exe", source / "PCSONIC.EXE",
                "--output", output)
            recovered = output / "instructions.jsonl"
            if not recovered.is_file() or sum(1 for _ in recovered.open()) != 164603:
                raise RuntimeError("Incomplete Ghidra export; existing instruction semantics have been preserved.")
            instructions.parent.mkdir(parents=True, exist_ok=True)
            for path in output.iterdir():
                path.replace(instructions.parent / path.name)
    count = sum(1 for _ in instructions.open())
    if count != 164603:
        raise RuntimeError(f"Expected 164603 recovered instructions, found {count}. See research and Ghidra logs.")
    run(os.sys.executable, ROOT / "tools/recompile.py")
    run("make", f"-j{args.jobs}")
    if not args.skip_movies:
        run(os.sys.executable, ROOT / "tools/prepare_movies.py", "--source", source)
    if source == ROOT / "source":
        command = "./play.sh"
    else:
        command = f"./play.sh --source {str(source)!r}"
    if args.skip_movies:
        command += " --skip-movies"
    print(f"\nReady: {command}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
