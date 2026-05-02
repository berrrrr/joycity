#!/usr/bin/env python3
"""
IRS Parser - "Resource File" sprite container format
Used by JoyTalk for tile sprites (e.g. Street/MS/_/T/Tile00036.irs)

Structure:
  [14]  bytes  "Resource File\x00"  (magic, exact 14 bytes)
  [4]   u32    (skip/version)
  [4]   u32    frame_count
  [N*4] u32[]  offset table (one u32 per frame; 0 = empty frame)

  For each non-zero offset:
    At offset:
    [4]   u32  data_size     (total encoded payload bytes, num4)
    [4]   u32  origin_x      (sprite canvas left padding, num6)
    [4]   u32  origin_y      (sprite canvas top padding, num7)
    [4]   u32  sprite_w      (sprite image width, num8)
    [4]   u32  sprite_h      (sprite image height, num9)
    [4]   u32  (skip)
    [4]   u32  (skip)
    [4]   u32  (skip)
    [4]   u32  (skip)
    Canvas size = (origin_x + sprite_w) x (origin_y + sprite_h)
    Image starts at canvas position (origin_x, origin_y)

    Encoded pixel stream (byte commands):
      0  -> end of frame
      1  -> pixel run:  [4] u32 count, then count x [2] u16 palette_index -> RGBA lookup
      2  -> skip run:   [4] u32 skip_count, advance skip_count/2 pixels
      3  -> next row (col counter resets, row counter increments)

    Palette is global (loaded separately from .pal or system palette).
    Palette index is a u16 referencing a 256-color or larger RGBA table.

Note: palette lookup requires an external palette (not embedded in IRS).
      Without palette, only raw index maps are available.
"""

import struct
import sys
from dataclasses import dataclass
from typing import Optional

MAGIC = b"Resource File\x00"  # 14 bytes


@dataclass
class SpriteFrame:
    origin_x: int   # canvas left padding
    origin_y: int   # canvas top padding
    width: int      # sprite image width
    height: int     # sprite image height
    canvas_w: int   # total canvas width  = origin_x + width
    canvas_h: int   # total canvas height = origin_y + height
    pixel_indices: list[int]  # raw palette indices, length = width * height (row-major)


def decode_frame(data: bytes, frame_offset: int) -> Optional[SpriteFrame]:
    pos = frame_offset

    data_size = struct.unpack_from('<I', data, pos)[0]; pos += 4
    byte_count = 0  # tracks consumed payload bytes (num5)

    origin_x = struct.unpack_from('<I', data, pos)[0]; pos += 4; byte_count += 4
    origin_y = struct.unpack_from('<I', data, pos)[0]; pos += 4; byte_count += 4
    sprite_w  = struct.unpack_from('<I', data, pos)[0]; pos += 4; byte_count += 4
    sprite_h  = struct.unpack_from('<I', data, pos)[0]; pos += 4; byte_count += 4

    # 4 more skipped u32s
    for _ in range(4):
        pos += 4; byte_count += 4

    canvas_w = origin_x + sprite_w
    canvas_h = origin_y + sprite_h
    total_pixels = canvas_w * canvas_h

    if total_pixels == 0 or total_pixels >= 64_000_000:
        return None

    # Canvas index map: origin_y rows of empty, then sprite rows starting at col origin_x
    pixel_indices = [0] * total_pixels  # 0 = transparent

    # Position trackers: col within row, row within canvas
    col = origin_x
    row = origin_y
    sprite_pixel_pos = row * canvas_w + col

    while byte_count <= data_size and pos < len(data):
        cmd = data[pos]; pos += 1; byte_count += 1

        if cmd == 0:  # end of frame
            break

        elif cmd == 1:  # pixel run
            count = struct.unpack_from('<I', data, pos)[0]; pos += 4; byte_count += 4
            for _ in range(count):
                if pos + 2 > len(data):
                    break
                palette_idx = struct.unpack_from('<H', data, pos)[0]; pos += 2; byte_count += 2
                if sprite_pixel_pos < total_pixels:
                    pixel_indices[sprite_pixel_pos] = palette_idx
                sprite_pixel_pos += 1
                col += 1

        elif cmd == 2:  # skip pixels
            skip = struct.unpack_from('<I', data, pos)[0]; pos += 4; byte_count += 4
            advance = skip // 2
            sprite_pixel_pos += advance
            col += advance

        elif cmd == 3:  # next row
            row += 1
            col = origin_x
            sprite_pixel_pos = row * canvas_w + col

        if byte_count > data_size:
            break

    return SpriteFrame(origin_x=origin_x, origin_y=origin_y,
                       width=sprite_w, height=sprite_h,
                       canvas_w=canvas_w, canvas_h=canvas_h,
                       pixel_indices=pixel_indices)


def parse(filepath: str) -> list[Optional[SpriteFrame]]:
    with open(filepath, 'rb') as f:
        data = f.read()

    magic = data[:14]
    if magic != MAGIC:
        raise ValueError(f"Not an IRS file: magic={magic!r}")

    pos = 14
    pos += 4  # skip version u32
    frame_count = struct.unpack_from('<I', data, pos)[0]; pos += 4
    offsets = list(struct.unpack_from(f'<{frame_count}I', data, pos))
    pos += frame_count * 4

    frames = []
    for offset in offsets:
        if offset == 0:
            frames.append(None)
        else:
            frame = decode_frame(data, offset)
            frames.append(frame)

    return frames


def main():
    if len(sys.argv) < 2:
        path = "/Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Street/MS/_/T/Tile00036.irs"
    else:
        path = sys.argv[1]

    print(f"Parsing: {path}")
    frames = parse(path)
    print(f"  Total frames: {len(frames)}")
    for i, f in enumerate(frames):
        if f is None:
            print(f"  [{i}] empty")
        else:
            print(f"  [{i}] canvas={f.canvas_w}x{f.canvas_h} "
                  f"origin=({f.origin_x},{f.origin_y}) "
                  f"sprite={f.width}x{f.height} "
                  f"pixels={len(f.pixel_indices)}")


if __name__ == "__main__":
    main()
