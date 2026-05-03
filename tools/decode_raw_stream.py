#!/usr/bin/env python3
"""
captures/*.raw.bin.{c2s,s2c} 의 원시 바이트를 line-delimited JSON 으로 디코드.

Phase 4 발견 (Windows 빌드, 2026-05-03):
  Phase 3의 [u32 len][type byte][payload] envelope 미사용.
  단순 NDJSON: 각 패킷은 `{...}\\n` 한 줄. 그게 전부.

실행:
  py -3.11 tools/decode_raw_stream.py captures/proxy_7942_*.raw.bin.s2c
  py -3.11 tools/decode_raw_stream.py ... --full
  py -3.11 tools/decode_raw_stream.py ... --filter login
"""
import argparse, io, json, pathlib, sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def split_lines(blob: bytes):
    """NDJSON 라인 단위 분해. 마지막 줄이 partial 이면 별도 반환."""
    parts = blob.split(b"\n")
    last_partial = parts[-1] if parts and parts[-1] else None
    lines = parts[:-1] if last_partial else parts
    return lines, last_partial


def decode(blob: bytes):
    lines, partial = split_lines(blob)
    parsed, errs = [], 0
    for raw in lines:
        if not raw.strip():
            continue
        try:
            parsed.append(json.loads(raw.decode("utf-8")))
        except Exception as e:
            errs += 1
            parsed.append({"__error__": str(e), "__raw__": raw[:80].decode("latin-1", "replace")})
    return parsed, partial, errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--full",   action="store_true", help="모든 패킷 dump")
    ap.add_argument("--filter", help="해당 type 만 출력")
    ap.add_argument("--summary", action="store_true", help="type 분포만")
    args = ap.parse_args()

    p = pathlib.Path(args.path)
    blob = p.read_bytes()
    print(f"파일 : {p}  ({len(blob):,} bytes)")
    pkts, partial, errs = decode(blob)
    print(f"패킷 : {len(pkts)}개  (parse 에러 {errs}개, 미완성 마지막 {len(partial) if partial else 0}B)")
    if partial:
        print(f"  partial preview: {partial[:80]!r}")

    type_counter = Counter()
    for p_ in pkts:
        type_counter[p_.get("type", "(no type)")] += 1

    print("\n=== JSON type 빈도 (top 30) ===")
    for t, n in type_counter.most_common(30):
        print(f"  {n:5d}  {t}")
    print(f"  (총 unique type: {len(type_counter)})")

    if args.full or args.filter:
        print("\n=== 패킷 상세 ===")
        for i, p_ in enumerate(pkts):
            if args.filter and p_.get("type") != args.filter:
                continue
            s = json.dumps(p_, ensure_ascii=False)
            if len(s) > 200:
                s = s[:200] + f"...(+{len(s)-200})"
            print(f"  #{i:5d}  {s}")


if __name__ == "__main__":
    main()
