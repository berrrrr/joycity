#!/usr/bin/env python3
"""
Step 3 검증용 — 파서 결과를 PPM 파일로 저장.

지원:
  .jcr — Joycity RAW. 임베디드 팔레트 사용. 모든 non-null frame → PPM.
  .irs — Resource File. 외부 팔레트 필요 (생성/시스템 팔레트로 fallback).

실행:
  py -3.11 tools/render_sprite.py <input> [output_dir]
"""
import argparse, io, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "parsers"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def write_ppm(path: pathlib.Path, w: int, h: int, rgb: bytes):
    with open(path, "wb") as f:
        f.write(f"P6\n{w} {h}\n255\n".encode())
        f.write(rgb)


def render_jcr(src: pathlib.Path, outdir: pathlib.Path):
    import jcr_parser as J
    frames = J.parse(str(src))
    written = 0
    for i, fr in enumerate(frames):
        if fr is None or fr.pixels is None:
            continue
        out = outdir / f"{src.stem}_frame{i:02d}.ppm"
        write_ppm(out, fr.width, fr.height, fr.pixels)
        print(f"  → {out}  ({fr.width}x{fr.height})")
        written += 1
    print(f"  총 {written} 프레임 저장")


def render_irs(src: pathlib.Path, outdir: pathlib.Path):
    """외부 팔레트 없이는 RGB 못 만듦 — 16색 grayscale 로 디버그 출력."""
    import irs_parser as I
    frames = I.parse(str(src))
    written = 0
    for i, fr in enumerate(frames):
        if fr is None:
            continue
        # palette index 를 256 으로 나눠서 grayscale 매핑 (검증용)
        rgb = bytearray()
        for idx in fr.pixel_indices:
            v = (idx & 0xFF)
            rgb += bytes([v, v, v])
        out = outdir / f"{src.stem}_frame{i:02d}_GRAY.ppm"
        write_ppm(out, fr.width, fr.height, bytes(rgb))
        print(f"  → {out}  ({fr.width}x{fr.height}, grayscale debug)")
        written += 1
    print(f"  총 {written} 프레임 저장 (grayscale debug — 진짜 색은 외부 .pal 필요)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("outdir", nargs="?", default="captures/sprites")
    args = ap.parse_args()

    src = pathlib.Path(args.input)
    out = pathlib.Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"입력 : {src}")
    print(f"출력 : {out}\n")

    ext = src.suffix.lower()
    if ext == ".jcr":
        render_jcr(src, out)
    elif ext == ".irs":
        render_irs(src, out)
    else:
        sys.exit(f"미지원 포맷: {ext}")


if __name__ == "__main__":
    main()
