#!/usr/bin/env python3
"""Statically lower Ghidra's instruction semantics to the portable game core.

No instruction decoder, PE execution, or CPU emulator is needed by the game at
runtime.  The original data addresses remain explicit so relocation tables,
object routines and the assembly rasterizers retain their original semantics.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UT = {1: 'uint8_t', 2: 'uint16_t', 4: 'uint32_t', 6: 'uint64_t',
      8: 'uint64_t', 10: 'u128'}
ST = {1: 'int8_t', 2: 'int16_t', 4: 'int32_t', 6: 'int64_t',
      8: 'int64_t', 10: 'i128'}
PAGE_BITS = 13


def constant(n):
    if n <= 0xffffffff:
        return f'0x{n:x}u'
    if n <= 0xffffffffffffffff:
        return f'UINT64_C(0x{n:x})'
    return f'(((u128)UINT64_C(0x{n >> 64:x}) << 64) | UINT64_C(0x{n & ((1 << 64)-1):x}))'


def name(v):
    return f'u_{v[1]:x}_{v[2]}'


def read(v, pc):
    sp, off, size = v
    if sp == 'c':
        return constant(off)
    if sp == 'u':
        return name(v)
    if sp == 'r':
        return f'r{size}(v, 0x{off:x})'
    if sp == 'm':
        return f'm{size}(v, 0x{off:x}u, {pc})'
    raise ValueError(v)


def write(v, expr, pc):
    sp, off, size = v
    cast = f'({UT[size]})({expr})'
    if sp == 'u':
        return f'{name(v)} = {cast};'
    if sp == 'r':
        return f'sr{size}(v, 0x{off:x}, {cast});'
    if sp == 'm':
        return f'sm{size}(v, 0x{off:x}u, {cast}, {pc});'
    raise ValueError(v)


def generate_op(op, addr, local):
    code, out, *args = op
    pc = constant(addr)
    a = [read(v, pc) for v in args]
    sz = args[0][2] if args else 0
    cast = lambda x, s=sz: f'(({ST[s]})({x}))'
    expr = None
    if code == 'COPY':
        expr = a[0]
    elif code == 'LOAD':
        expr = f'm{out[2]}(v, (uint32_t)({a[1]}), {pc})'
    elif code == 'STORE':
        return f'sm{args[2][2]}(v, (uint32_t)({a[1]}), {a[2]}, {pc});'
    elif code in ('BRANCH', 'CALL', 'CBRANCH', 'BRANCHIND', 'CALLIND', 'RETURN'):
        if code in ('BRANCH', 'CALL', 'CBRANCH'):
            assert args[0][0] == 'm', (addr, op)
            dest = args[0][1]
            # Calls always pass through the dispatcher, including host hooks.
            go = f'goto L_{dest:x};' if dest in local and code != 'CALL' else f'return 0x{dest:x}u;'
        else:
            go = f'return (uint32_t)({a[0]});'
        return f'if ({a[1]}) {{ {go} }}' if code == 'CBRANCH' else go
    elif code in ('INT_ZEXT', 'INT_SEXT'):
        expr = a[0] if code == 'INT_ZEXT' else cast(a[0])
    elif code in ('INT_ADD', 'INT_SUB', 'INT_MULT', 'INT_AND', 'INT_OR', 'INT_XOR'):
        sym = dict(INT_ADD='+', INT_SUB='-', INT_MULT='*', INT_AND='&', INT_OR='|', INT_XOR='^')[code]
        # Widen first: C's signed integer promotions must not overflow for u16.
        expr = f'((u128)({a[0]}) {sym} (u128)({a[1]}))'
    elif code in ('INT_DIV', 'INT_REM', 'INT_SDIV', 'INT_SREM'):
        expr = f'vm_div(v, (uint64_t)({a[0]}), (uint64_t)({a[1]}), {sz}, {int(code in ("INT_SDIV", "INT_SREM"))}, {int(code in ("INT_REM", "INT_SREM"))}, {pc})'
    elif code in ('INT_LEFT', 'INT_RIGHT', 'INT_SRIGHT'):
        expr = f'vm_shift((u128)({a[0]}), (uint64_t)({a[1]}), {sz * 8}, {dict(INT_LEFT=0, INT_RIGHT=1, INT_SRIGHT=2)[code]})'
    elif code == 'INT_CARRY':
        expr = f'((((u128)({a[0]}) + (u128)({a[1]})) >> {sz * 8}) != 0)'
    elif code in ('INT_SCARRY', 'INT_SBORROW'):
        signbit = constant(1 << (sz * 8 - 1))
        sym = '+' if code == 'INT_SCARRY' else '-'
        first = f'~((u128)({a[0]}) ^ (u128)({a[1]}))' if code == 'INT_SCARRY' else f'((u128)({a[0]}) ^ (u128)({a[1]}))'
        expr = f'(({first} & ((u128)({a[0]}) ^ ((u128)({a[0]}) {sym} (u128)({a[1]}))) & {signbit}) != 0)'
    elif code in ('INT_EQUAL', 'INT_NOTEQUAL', 'INT_LESS', 'INT_LESSEQUAL', 'INT_SLESS', 'INT_SLESSEQUAL'):
        sym = dict(INT_EQUAL='==', INT_NOTEQUAL='!=', INT_LESS='<', INT_LESSEQUAL='<=', INT_SLESS='<', INT_SLESSEQUAL='<=')[code]
        expr = f'({cast(a[0])} {sym} {cast(a[1])})' if code.startswith('INT_S') else f'({a[0]} {sym} {a[1]})'
    elif code == 'INT_2COMP':
        expr = f'(0 - (u128)({a[0]}))'
    elif code == 'INT_NEGATE':
        expr = f'(~(u128)({a[0]}))'
    elif code == 'BOOL_NEGATE':
        expr = f'(!({a[0]}))'
    elif code in ('BOOL_AND', 'BOOL_OR', 'BOOL_XOR'):
        sym = dict(BOOL_AND='&&', BOOL_OR='||', BOOL_XOR='!=')[code]
        expr = f'(!!({a[0]}) {sym} !!({a[1]}))'
    elif code == 'SUBPIECE':
        expr = f'((u128)({a[0]}) >> ({a[1]} * 8))'
    elif code == 'PIECE':
        expr = f'(((u128)({a[0]}) << {args[1][2] * 8}) | (u128)({a[1]}))'
    elif code == 'POPCOUNT':
        expr = f'__builtin_popcountll((uint64_t)({a[0]}))'
    elif code == 'LZCOUNT':
        expr = f'vm_clz((uint64_t)({a[0]}), {sz * 8})'
    elif code in ('FLOAT2FLOAT', 'INT2FLOAT', 'TRUNC', 'ROUND', 'CEIL', 'FLOOR') or code.startswith('FLOAT_'):
        fa = [f'fp_read((u128)({s}), {x[2]})' for s, x in zip(a, args)]
        if code == 'FLOAT2FLOAT':
            expr = f'fp_write({fa[0]}, {out[2]})'
        elif code == 'INT2FLOAT':
            expr = f'fp_write((long double){cast(a[0])}, {out[2]})'
        elif code == 'TRUNC':
            expr = f'fp_trunc(v, {fa[0]}, {out[2]}, {pc})'
        elif code in ('ROUND', 'CEIL', 'FLOOR'):
            fn = dict(ROUND='fp_round', CEIL='ceill', FLOOR='floorl')[code]
            rounded = f'{fn}(v, {fa[0]})' if code == 'ROUND' else f'{fn}({fa[0]})'
            expr = f'fp_write({rounded}, {out[2]})'
        elif code in ('FLOAT_ADD', 'FLOAT_SUB', 'FLOAT_MULT', 'FLOAT_DIV'):
            sym = dict(FLOAT_ADD='+', FLOAT_SUB='-', FLOAT_MULT='*', FLOAT_DIV='/')[code]
            expr = f'fp_write(({fa[0]} {sym} {fa[1]}), {out[2]})'
        elif code in ('FLOAT_EQUAL', 'FLOAT_NOTEQUAL', 'FLOAT_LESS', 'FLOAT_LESSEQUAL'):
            sym = dict(FLOAT_EQUAL='==', FLOAT_NOTEQUAL='!=', FLOAT_LESS='<', FLOAT_LESSEQUAL='<=')[code]
            expr = f'({fa[0]} {sym} {fa[1]})'
        elif code in ('FLOAT_NAN', 'FLOAT_NEG', 'FLOAT_ABS', 'FLOAT_SQRT'):
            val = dict(FLOAT_NAN=f'isnan({fa[0]})', FLOAT_NEG=f'-({fa[0]})', FLOAT_ABS=f'fabsl({fa[0]})', FLOAT_SQRT=f'sqrtl({fa[0]})')[code]
            expr = val if code == 'FLOAT_NAN' else f'fp_write({val}, {out[2]})'
        else:
            raise ValueError((addr, op))
    elif code == 'CALLOTHER':
        user = args[0][1]
        if user in (17, 18):  # LOCK / UNLOCK: game runs on a single thread.
            return ';'
        if user in (109, 115, 120):
            fn = {109: 'cosl', 115: 'sinl', 120: 'log2l'}[user]
            expr = f'fp_write({fn}(fp_read((u128)({a[1]}), {args[1][2]})), {out[2]})'
        elif user == 67:  # SLDT in Watcom's DOS/Windows stack probe.
            expr = '0'
        elif user == 85:  # VERR, only used by the original stack probe.
            return 'sr1(v, 0x206, 1);'
        else:
            return f'return vm_fault(v, {pc}, "unsupported user operation {user}");'
    else:
        raise ValueError((addr, op))
    assert expr is not None and out is not None, (addr, op)
    return write(out, expr, pc)


def write_changed(path, content):
    """Keep unchanged translation units so incremental builds stay small."""
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', type=Path, default=ROOT/'research/pcode/instructions.jsonl')
    ap.add_argument('--output', type=Path, default=ROOT/'game/native/generated')
    ns = ap.parse_args()
    instructions = {i['a']: i for i in map(json.loads, ns.input.open())}
    pages = collections.defaultdict(list)
    entries = set()
    for i in instructions.values():
        pages[i['a'] >> PAGE_BITS].append(i)
        for op in i['ops']:
            if op[0] in ('BRANCH', 'CBRANCH', 'CALL') and op[2][0] == 'm':
                entries.add(op[2][1])
            if op[0] in ('BRANCH', 'CBRANCH', 'CALL', 'BRANCHIND', 'CALLIND', 'RETURN'):
                entries.add(i['a'] + i['n'])
    ns.output.mkdir(parents=True, exist_ok=True)
    for page, seq in sorted(pages.items()):
        seq.sort(key=lambda x: x['a'])
        local = {i['a'] for i in seq}
        lines = ['/* Generated by tools/recompile.py; do not edit. */', '#include "../vm.h"',
                 f'uint32_t page_{page:x}(VM *v, uint32_t pc) {{', '  switch (pc) {']
        lines += [f'    case 0x{i["a"]:x}u: goto L_{i["a"]:x};' for i in seq]
        lines += ['    default: return vm_fault(v, pc, "untranslated instruction");', '  }']
        for idx, i in enumerate(seq):
            addr = i['a']
            lines.append(f'L_{addr:x}: {{ /* {i["s"].replace("*/", "* /")} */')
            if addr in entries or idx == 0:
                lines.append(f'  if (!vm_budget(v, 0x{addr:x}u)) return VM_STOP;')
            uniques = sorted({tuple(v) for op in i['ops'] for v in op[1:] if isinstance(v, list) and v[0] == 'u'}, key=lambda v: (v[1], v[2]))
            for v in uniques:
                lines.append(f'  {UT[v[2]]} {name(v)};')
            for op in i['ops']:
                lines.append('  ' + generate_op(op, addr, local))
            nextpc = addr + i['n']
            terminal = i['ops'] and i['ops'][-1][0] in ('BRANCH', 'CALL', 'BRANCHIND', 'CALLIND', 'RETURN')
            if not terminal and (idx+1 == len(seq) or seq[idx+1]['a'] != nextpc):
                lines.append(f'  return 0x{nextpc:x}u;')
            lines.append('}')
        lines += ['}']
        write_changed(ns.output/f'page_{page:x}.c', '\n'.join(lines)+'\n')
    dispatch = ['/* Generated by tools/recompile.py; do not edit. */', '#include "../vm.h"']
    dispatch += [f'uint32_t page_{p:x}(VM *, uint32_t);' for p in sorted(pages)]
    dispatch += ['uint32_t vm_translated(VM *v, uint32_t pc) {', f'  switch(pc >> {PAGE_BITS}) {{']
    dispatch += [f'    case 0x{p:x}: return page_{p:x}(v, pc);' for p in sorted(pages)]
    dispatch += ['    default: return vm_fault(v, pc, "untranslated address");', '  }', '}']
    write_changed(ns.output/'dispatch.c', '\n'.join(dispatch)+'\n')
    metadata = {'instructions': len(instructions), 'pages': len(pages), 'page_bits': PAGE_BITS,
                'ops': dict(collections.Counter(op[0] for i in instructions.values() for op in i['ops']))}
    write_changed(ns.output/'metadata.json', json.dumps(metadata, indent=2)+'\n')
    print(f'Lowered {len(instructions):,} instructions into {len(pages)} native C pages.')


if __name__ == '__main__':
    main()
