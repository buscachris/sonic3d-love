#!/usr/bin/env python3
"""Record source hashes without modifying the disc or extracted files."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def describe(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return {'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--iso', type=Path, default=Path('/home/anon/Sonic3D.iso'))
    args = ap.parse_args()
    manifest = {
        'disc': {'path': str(args.iso), **describe(args.iso)},
        'version': 'Sonic 3D Blast for Windows PC (1997), repackaged disc',
        'source_files': {str(p.relative_to(ROOT / 'source')): describe(p)
                         for p in sorted((ROOT / 'source').rglob('*')) if p.is_file()},
    }
    dest = ROOT / 'research/source-manifest.json'
    dest.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'{len(manifest["source_files"])} source files recorded in {dest}')

if __name__ == '__main__':
    main()
