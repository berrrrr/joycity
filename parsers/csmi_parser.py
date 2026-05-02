#!/usr/bin/env python3
"""
CSMI Parser - "CSMI File 2.0" object placement format
Used by JoyTalk for map object data (e.g. Street/M/A/obj.gpd)

Structure (obj.gpd):
  [4]   u32    object_count
  For each object:
    [1]  u8   len; [N] str "CSMI File 2.0"  (magic check)
    [4]  u32  object_id  (num4)
    [4]  u32  (skip)
    [4]  u32  (skip)
    [1]  u8   len; [N] str type_code (e.g. "ubb", "chr")
    [4]  u32  (skip)
    [4]  u32  (skip)
    [1]  u8   len; [N] str transform_str   (UTF-8, via _1680)
    [1]  u8   len; [N] str name            (ASCII)
    [4]  u32  layer_count
    For each layer:
      [4]  u32  sprite_count
      For each sprite:
        [4]  u32  x           (num10)
        [4]  u32  y           (num11)
        [4]  u32  z           (num12)
        [4]  u32  sprite_id   (num13)
        [4]  u32  w           (num14)
        [4]  u32  h           (num15)
        [4]  i32  flip_x      (num16, signed)
        [4]  i32  flip_y      (num17, signed)
        [4]  i32  alpha       (num18, signed)
        [4]  u32  frame       (num19)
        [4]  u32  anim_count  (num20)
        [N*4] u32[] anim_frames
    [4]  u32  collision_layer_count
    For each collision layer:
      [4]  u32  point_count
      [N*2] u16[] collision_point_ids
    [4]  u32  (trailing skip)
"""

import struct
import sys
from dataclasses import dataclass, field
from typing import Optional

MAGIC = "CSMI File 2.0"


@dataclass
class SpriteEntry:
    x: int
    y: int
    z: int
    sprite_id: int
    w: int
    h: int
    flip_x: int
    flip_y: int
    alpha: int
    frame: int
    anim_frames: list[int]


@dataclass
class CollisionLayer:
    point_ids: list[int]


@dataclass
class CsmiObject:
    object_id: int
    type_code: str
    transform: str
    name: str
    layers: list[list[SpriteEntry]]
    collision_layers: list[CollisionLayer]


def read_pstring(data: bytes, pos: int, encoding: str = 'ascii') -> tuple[str, int]:
    """Read pascal-style string with variable-length prefix.
    If length byte == 0xFF, the actual length is the next u16 (little-endian).
    """
    slen = data[pos]; pos += 1
    if slen == 0xFF:
        slen = struct.unpack_from('<H', data, pos)[0]; pos += 2
    if slen == 0:
        return '', pos
    s = data[pos:pos + slen].decode(encoding, errors='replace'); pos += slen
    return s, pos


def parse(filepath: str) -> list[CsmiObject]:
    with open(filepath, 'rb') as f:
        data = f.read()

    pos = 0
    object_count = struct.unpack_from('<I', data, pos)[0]; pos += 4

    objects = []
    for _ in range(object_count):
        # Magic check
        magic, pos = read_pstring(data, pos, 'ascii')
        if magic != MAGIC:
            raise ValueError(f"Expected '{MAGIC}', got '{magic}'")

        object_id = struct.unpack_from('<I', data, pos)[0]; pos += 4
        pos += 4  # skip
        pos += 4  # skip

        type_code, pos = read_pstring(data, pos, 'ascii')
        pos += 4  # skip
        pos += 4  # skip

        transform, pos = read_pstring(data, pos, 'utf-8')
        name, pos = read_pstring(data, pos, 'ascii')

        layer_count = struct.unpack_from('<I', data, pos)[0]; pos += 4
        layers = []
        for _ in range(layer_count):
            sprite_count = struct.unpack_from('<I', data, pos)[0]; pos += 4
            sprites = []
            for _ in range(sprite_count):
                x, y, z, sid, w, h = struct.unpack_from('<6I', data, pos); pos += 24
                fx, fy, alpha = struct.unpack_from('<3i', data, pos); pos += 12
                frame, anim_count = struct.unpack_from('<II', data, pos); pos += 8
                anim_frames = list(struct.unpack_from(f'<{anim_count}I', data, pos))
                pos += anim_count * 4
                sprites.append(SpriteEntry(x=x, y=y, z=z, sprite_id=sid, w=w, h=h,
                                           flip_x=fx, flip_y=fy, alpha=alpha,
                                           frame=frame, anim_frames=anim_frames))
            layers.append(sprites)

        collision_layer_count = struct.unpack_from('<I', data, pos)[0]; pos += 4
        collision_layers = []
        for _ in range(collision_layer_count):
            pt_count = struct.unpack_from('<I', data, pos)[0]; pos += 4
            pts = list(struct.unpack_from(f'<{pt_count}H', data, pos))
            pos += pt_count * 2
            collision_layers.append(CollisionLayer(point_ids=pts))

        pos += 4  # trailing skip

        objects.append(CsmiObject(object_id=object_id, type_code=type_code,
                                   transform=transform, name=name,
                                   layers=layers, collision_layers=collision_layers))

    return objects


def main():
    import os
    if len(sys.argv) < 2:
        # Find a gpd file
        base = "/Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Street"
        path = None
        for root, dirs, files in os.walk(base):
            for fname in files:
                if fname == 'obj.gpd':
                    path = os.path.join(root, fname)
                    break
            if path:
                break
        if not path:
            print("No obj.gpd found"); return
    else:
        path = sys.argv[1]

    print(f"Parsing: {path}")
    try:
        objs = parse(path)
        print(f"  Objects: {len(objs)}")
        for obj in objs[:5]:
            print(f"  [{obj.object_id}] type='{obj.type_code}' name='{obj.name}' "
                  f"layers={len(obj.layers)} collision={len(obj.collision_layers)}")
    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    main()
