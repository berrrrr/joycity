#!/usr/bin/env python3
"""
JCR Parser - "Joycity #$@(RAW! #!#(!# #!TS" sprite format
Used by JoyTalk for character/object sprites (e.g. Res/jcr/j0005.jcr)

Structure:
  [28]  bytes  "Joycity #$@(RAW! #!#(!# #!TS"  (magic)
  [2]   u16    frame_count
  [N*2] u16[]  frame_data_sizes (one per frame)

  For each frame:
    [2]   u16   width
    [2]   u16   height
    [1]   u8    palette_type:
                  0   = grayscale (256 auto-generated: R=G=B=i, transparent at 0)
                  1   = custom palette: [1] u8 pal_count, then pal_count x [3] RGB bytes
                  57  = special (skip 864 bytes, emit 35x35 null frame)
                  93  = special (reset to offset 3927, emit 35x35 null frame)
                  197 = end sentinel

    Pixel data: RLE-encoded palette indices
      RLE marker: bytes 0xFF 0xFE -> index=[1 byte], count=[u16 2 bytes] (5 bytes total)
      Otherwise:  single index byte (count=1)
    Output: width * height pixels of (R, G, B) using palette lookup
    Transparent color: palette entry 0 with R=0xFF, G=0x00, B=0xFF (magenta)
"""

import struct
import sys
from dataclasses import dataclass
from typing import Optional

MAGIC = b"Joycity #$@(RAW! #!#(!# #!TS"  # 28 bytes


@dataclass
class JcrFrame:
    width: int
    height: int
    pixels: Optional[bytes]   # width*height*3 bytes (RGB), None = empty/sentinel


def decode_palette_type0() -> list[tuple[int,int,int]]:
    """Grayscale palette: index 0 = transparent (magenta), 1-255 = gray"""
    pal = [(i, i, i) for i in range(256)]
    pal[0] = (255, 0, 255)  # transparent = magenta
    return pal


def decode_palette_type1(data: bytes, pos: int) -> tuple[list[tuple[int,int,int]], int]:
    """Custom RGB palette"""
    count = data[pos]; pos += 1
    pal = []
    for _ in range(count):
        r, g, b = data[pos], data[pos+1], data[pos+2]; pos += 3
        pal.append((r, g, b))
    return pal, pos


def parse(filepath: str) -> list[Optional[JcrFrame]]:
    with open(filepath, 'rb') as f:
        data = f.read()

    magic = data[:28]
    if magic != MAGIC:
        raise ValueError(f"Not a JCR file: magic={magic!r}")

    pos = 28
    frame_count = struct.unpack_from('<H', data, pos)[0]; pos += 2
    frame_sizes = list(struct.unpack_from(f'<{frame_count}H', data, pos))
    pos += frame_count * 2

    frames = []

    for j in range(frame_count):
        frame_start_bytes = 0  # num5: tracks consumed payload bytes

        width  = struct.unpack_from('<H', data, pos)[0]; pos += 2; frame_start_bytes += 2
        height = struct.unpack_from('<H', data, pos)[0]; pos += 2; frame_start_bytes += 2

        pal_type = data[pos]; pos += 1; frame_start_bytes += 1

        if pal_type == 197:  # end sentinel
            break

        if pal_type == 93:   # special: skip 864 bytes
            pos += 864; frame_start_bytes += 864
            # don't advance past it, but skip rest: actual advance tracked by frame_sizes
            frames.append(JcrFrame(width=35, height=35, pixels=None))
            continue

        if pal_type == 57:   # special: reset offset
            pos = 3927; frame_start_bytes = 3927
            frames.append(JcrFrame(width=35, height=35, pixels=None))
            continue

        # Build palette
        if pal_type == 1:
            palette, pos = decode_palette_type1(data, pos)
            frame_start_bytes += 1 + len(palette) * 3
        else:
            palette = decode_palette_type0()

        if width == 0:
            frames.append(None)
            continue

        total_pixels = width * height
        pixels_rgb = bytearray(total_pixels * 3)
        pixel_pos = 0

        while (frame_start_bytes <= frame_sizes[j] or pixel_pos < total_pixels) and pos < len(data):
            # Check for RLE marker: 0xFF 0xFE
            if (frame_start_bytes + 4 <= frame_sizes[j]
                    and pos + 1 < len(data)
                    and data[pos] == 0xFF and data[pos+1] == 0xFE):
                idx   = data[pos+2]
                count = struct.unpack_from('<H', data, pos+3)[0]
                pos += 5; frame_start_bytes += 5
            else:
                idx   = data[pos]
                count = 1
                pos += 1; frame_start_bytes += 1

            for _ in range(count):
                if pixel_pos >= total_pixels:
                    break
                if 0 <= idx < len(palette):
                    r, g, b = palette[idx]
                else:
                    r, g, b = 0, 0, 0
                pixels_rgb[pixel_pos*3]     = r
                pixels_rgb[pixel_pos*3 + 1] = g
                pixels_rgb[pixel_pos*3 + 2] = b
                pixel_pos += 1

            if pixel_pos >= total_pixels or frame_start_bytes > frame_sizes[j]:
                break

        frames.append(JcrFrame(width=width, height=height, pixels=bytes(pixels_rgb)))

    return frames


def save_ppm(frame: JcrFrame, path: str):
    """Save a single JcrFrame as PPM (viewable with most image viewers)"""
    with open(path, 'wb') as f:
        f.write(f"P6\n{frame.width} {frame.height}\n255\n".encode())
        f.write(frame.pixels)


def main():
    if len(sys.argv) < 2:
        path = "/Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Res/jcr/j0005.jcr"
    else:
        path = sys.argv[1]

    print(f"Parsing: {path}")
    frames = parse(path)
    print(f"  Total frames: {len(frames)}")
    for i, f in enumerate(frames):
        if f is None:
            print(f"  [{i}] empty")
        elif f.pixels is None:
            print(f"  [{i}] sentinel {f.width}x{f.height}")
        else:
            print(f"  [{i}] {f.width}x{f.height} ({len(f.pixels)} bytes RGB)")

    # Save first non-null frame as PPM if output dir given
    if len(sys.argv) >= 3:
        import os
        out_dir = sys.argv[2]
        os.makedirs(out_dir, exist_ok=True)
        for i, f in enumerate(frames):
            if f and f.pixels:
                out = os.path.join(out_dir, f"frame_{i:03d}.ppm")
                save_ppm(f, out)
                print(f"  Saved: {out}")


if __name__ == "__main__":
    main()
