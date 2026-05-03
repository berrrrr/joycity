#!/usr/bin/env python3
"""
RMM 셀 필드 통계 + 시각화 dump.

목적: 어떤 필드 (obj_code, tile_id, unk1) 가 collision (벽/장애물) 인지 추정.
정상적으로 큰 맵이면 대부분 walkable, 일부가 obj_code != 0 (벽/나무/물)일 듯.

실행: py -3.11 playground/rmm_stats.py [path]
"""
import io, sys, pathlib, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "parsers"))

import rmm_parser

path = sys.argv[1] if len(sys.argv) > 1 else r"C:/Users/berrr/AppData/Local/Joytalk/Street/M/Map01006.rmm"
m = rmm_parser.parse(path)
print(f"Map: {path}")
print(f"  size = {m.width} x {m.height}  version='{m.version}'  tile_types={len(m.tile_types)}")
total = m.width * m.height
print(f"  total cells = {total}")

# 필드별 분포
def dist(name, vals):
    c = collections.Counter(vals)
    print(f"\n=== {name} 분포 (top 10 / unique={len(c)}) ===")
    for v, n in c.most_common(10):
        pct = 100 * n / total
        print(f"  {v:6} : {n:6}  ({pct:5.1f}%)")

dist("tile_id",  [c.tile_id  for r in m.grid for c in r])
dist("obj_code", [c.obj_code for r in m.grid for c in r])
dist("sub_type", [c.sub_type for r in m.grid for c in r])
dist("unk1",     [c.unk1     for r in m.grid for c in r])
dist("frame",    [c.frame    for r in m.grid for c in r])

# obj_code 0 의 위치 분포 (walkable 후보 — 연속 영역인지)
zero_obj = sum(1 for r in m.grid for c in r if c.obj_code == 0)
nonzero_obj = total - zero_obj
print(f"\nobj_code == 0  : {zero_obj}  ({100*zero_obj/total:.1f}%)")
print(f"obj_code != 0  : {nonzero_obj}  ({100*nonzero_obj/total:.1f}%)")

# ASCII 시각화 — 일부 영역 (캡처상 본인 위치 (89,92) 근처)
print("\n=== 시각화 — obj_code 기반 ===")
print("    . = obj_code 0 (walkable 후보)   # = obj_code != 0 (blocked 후보)")
print("    M = 본인 위치 (89, 92) 근처       0 = unk1 == 0\n")

cx, cy = 89, 92
half = 30
x0 = max(0, cx - half); x1 = min(m.width, cx + half)
y0 = max(0, cy - half); y1 = min(m.height, cy + half)
print(f"  x={x0}~{x1-1}, y={y0}~{y1-1}")
for y in range(y0, y1):
    line = ""
    for x in range(x0, x1):
        c = m.grid[y][x]
        if (x, y) == (cx, cy):
            line += "M"
        elif c.obj_code == 0:
            line += "."
        else:
            line += "#"
    print(f"  {y:3d} {line}")

print("\n=== 시각화 — unk1 기반 (같은 영역) ===")
for y in range(y0, y1):
    line = ""
    for x in range(x0, x1):
        c = m.grid[y][x]
        if (x, y) == (cx, cy):
            line += "M"
        else:
            line += str(c.unk1) if c.unk1 < 10 else "+"
    print(f"  {y:3d} {line}")
