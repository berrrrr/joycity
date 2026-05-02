#!/usr/bin/env python3
"""
RMM Parser - RedMoon Map Data 1.0 format
Used by JoyTalk for 2D tile/object map layout

Structure:
  [1]   u8    header_len
  [N]   str   "RedMoon MapData 1.0"
  [4]   u32   width  (map columns)
  [4]   u32   height (map rows)
  [1]   u8    version_len
  [N]   bytes version string (EUC-KR, skipped)
  [4]   u32   (skipped)
  [4]   u32   tile_type_count
  For each tile_type:
    [2]   u16   tile_id
    [4]   u32   a
    [4]   u32   b
    [4]   u32   c
    [4]   u32   d
  Grid[height][width] - 8 bytes each:
    tileId  = ((b1 & 0x7F) << 4) | ((b0 & 0xF0) >> 4)   # 11 bits
    unk1    = b7 >> 1                                      # 7 bits
    objCode = ((b3 & 0xFF) << 2) | ((b2 & 0xC0) >> 6)    # 10 bits
    subType = ((b2 & 0x3F) << 1) | ((b1 & 0x80) >> 7)    # 7 bits
    frame   = b6                                           # 8 bits
    rotation = b4 // 8                                     # 5 bits
"""

import struct
import sys
from dataclasses import dataclass, field
from typing import Optional


HEADER_MAGIC = "RedMoon MapData 1.0"


@dataclass
class TileType:
    id: int
    a: int
    b: int
    c: int
    d: int


@dataclass
class Cell:
    tile_id: int    # ground tile sprite index
    obj_code: int   # object sprite index (0 = empty)
    sub_type: int   # object sub-type
    frame: int      # animation frame
    rotation: int   # rotation (0-4, multiply by 90 deg)
    unk1: int       # unknown flags


@dataclass
class RmmMap:
    width: int
    height: int
    version: str
    tile_types: list[TileType]
    grid: list[list[Cell]]  # grid[y][x]


def parse(filepath: str) -> RmmMap:
    with open(filepath, 'rb') as f:
        data = f.read()

    pos = 0

    # Header
    hdr_len = data[pos]; pos += 1
    header = data[pos:pos + hdr_len].decode('ascii'); pos += hdr_len
    if header != HEADER_MAGIC:
        raise ValueError(f"Not an RMM file: header='{header}'")

    # Dimensions
    width  = struct.unpack_from('<I', data, pos)[0]; pos += 4
    height = struct.unpack_from('<I', data, pos)[0]; pos += 4

    # Version string (EUC-KR, skip)
    ver_len = data[pos]; pos += 1
    version = data[pos:pos + ver_len].decode('cp949', errors='replace'); pos += ver_len

    # Skip unknown u32
    pos += 4

    # Tile type table
    tile_type_count = struct.unpack_from('<I', data, pos)[0]; pos += 4
    tile_types = []
    for _ in range(tile_type_count):
        tid = struct.unpack_from('<H', data, pos)[0]; pos += 2
        a, b, c, d = struct.unpack_from('<IIII', data, pos); pos += 16
        tile_types.append(TileType(id=tid, a=a, b=b, c=c, d=d))

    # Grid
    grid = []
    for y in range(height):
        row = []
        for x in range(width):
            b = data[pos:pos + 8]; pos += 8
            tile_id  = ((b[1] & 0x7F) << 4) | ((b[0] & 0xF0) >> 4)
            unk1     = b[7] >> 1
            obj_code = ((b[3] & 0xFF) << 2) | ((b[2] & 0xC0) >> 6)
            sub_type = ((b[2] & 0x3F) << 1) | ((b[1] & 0x80) >> 7)
            frame    = b[6]
            rotation = b[4] // 8
            row.append(Cell(tile_id=tile_id, obj_code=obj_code,
                           sub_type=sub_type, frame=frame,
                           rotation=rotation, unk1=unk1))
        grid.append(row)

    return RmmMap(width=width, height=height, version=version,
                  tile_types=tile_types, grid=grid)


def main():
    if len(sys.argv) < 2:
        path = "/Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Street/MS/Map02034.rmm"
    else:
        path = sys.argv[1]

    print(f"Parsing: {path}")
    m = parse(path)
    print(f"  Size: {m.width} x {m.height}")
    print(f"  Version: '{m.version}'")
    print(f"  Tile types: {len(m.tile_types)}")
    print(f"  First 5 cells (row 0):")
    for cell in m.grid[0][:5]:
        print(f"    tile={cell.tile_id} obj={cell.obj_code} sub={cell.sub_type} "
              f"frame={cell.frame} rot={cell.rotation}")


if __name__ == "__main__":
    main()
