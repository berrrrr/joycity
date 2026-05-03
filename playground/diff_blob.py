#!/usr/bin/env python3
"""
Windows Joytalk.dll에 임베드된 _4 문자열 블롭을 decrypt + 통계.

목적:
  - macOS 추출본 (playground/string_blob.bin) 과 byte-level diff
  - Windows 빌드의 진짜 블롭 길이 추정 (printable ratio sliding window)
  - 새로 추가된 문자열 후보 미리보기

실행: py -3.11 playground/diff_blob.py
"""
import io, pathlib, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent
BLOB = REPO / "playground" / "string_blob.bin"
DLL  = pathlib.Path(r"C:/Users/berrr/AppData/Local/Joytalk/Joytalk.dll")

blob = BLOB.read_bytes()
dll  = DLL.read_bytes()

print(f"기존 blob   : {len(blob):,} bytes  (macOS Phase 1 결과)")
print(f"Windows DLL : {len(dll):,} bytes  ({DLL})")

off = dll.find(blob[:256])
print(f"\nblob 시작 offset in DLL : {off} (0x{off:x})")

# 공통 prefix 길이
n = 0
while n < len(blob) and off + n < len(dll) and dll[off + n] == blob[n]:
    n += 1
print(f"공통 prefix : {n:,} / {len(blob):,} bytes ({100*n/len(blob):.1f}%)")

def dec(b, base=0):
    return bytes(b[i] ^ ((base + i) & 0xFF) ^ 0xAA for i in range(len(b)))

# ASCII 인쇄 가능 비율을 슬라이딩 윈도우로 추적 → 블롭 끝 추정
# 한글 UTF-8 영역(0x80~0xBF, 0xE0~0xEF)은 노이즈도 잘 걸리므로 strict ASCII 기준
WINDOW = 512
RATIO_END = 0.30
SCAN_MAX = 400_000

dec_buf = dec(dll[off:off + SCAN_MAX])

def is_printable(b):
    # strict ASCII printable + 줄바꿈/탭만 (UTF-8 한글은 의도적으로 제외)
    return (32 <= b < 127) or b in (0x09, 0x0A, 0x0D)

# rolling printable count
rolling = sum(1 for b in dec_buf[:WINDOW] if is_printable(b))
end_offset = None
for i in range(WINDOW, len(dec_buf)):
    out = dec_buf[i - WINDOW]
    inn = dec_buf[i]
    if is_printable(out): rolling -= 1
    if is_printable(inn): rolling += 1
    ratio = rolling / WINDOW
    if ratio < RATIO_END:
        # 끝점: 마지막으로 printable이 끝난 자리 근처
        # 최근 64바이트에서 마지막 printable 위치
        for j in range(i, max(i - 256, 0), -1):
            if is_printable(dec_buf[j]):
                end_offset = j + 1
                break
        else:
            end_offset = i
        break

if end_offset is None:
    print(f"\n경계 못 찾음 (>{SCAN_MAX:,} bytes 까지 printable 유지)")
else:
    win_blob_len = end_offset
    print(f"\n추정 Windows blob 길이 : {win_blob_len:,} bytes")
    print(f"  vs macOS blob ({len(blob):,}) : {win_blob_len - len(blob):+,} bytes")

# 첫 번째 분기 직전/이후 strings 일부 출력
print("\n--- 분기점 직전 디코드 ---")
print(dec(dll[off+max(n-200,0):off+n]).decode("utf-8", "replace"))
print("\n--- 분기점 이후 디코드 (Windows-only 일부) ---")
print(dec(dll[off+n:off+n+512], base=n).decode("utf-8", "replace"))
