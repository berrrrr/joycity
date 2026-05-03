#!/usr/bin/env python3
"""
Windows Joytalk.dll에서 _4 블롭을 raw로 추출 + decrypt + 문자열 통계.

산출물:
  playground/string_blob_windows.bin  — raw blob
  playground/string_blob_windows.dec  — decrypted (UTF-8)
  playground/windows_strings.txt      — 길이 4+ 문자열 모두 (offset 포함)

실행: py -3.11 playground/extract_blob_windows.py
"""
import io, pathlib, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO  = pathlib.Path(__file__).resolve().parent.parent
PLAY  = REPO / "playground"
OLD   = PLAY / "string_blob.bin"
DLL   = pathlib.Path(r"C:/Users/berrr/AppData/Local/Joytalk/Joytalk.dll")

dll = DLL.read_bytes()
old = OLD.read_bytes()

# 1) blob 시작 위치 — 기존 blob의 초기 256B 패턴이 동일하므로 거기서 찾는다
off = dll.find(old[:256])
assert off > 0, "blob 시작점을 찾지 못함"

def dec_byte(b, p): return b ^ (p & 0xFF) ^ 0xAA

def decrypt_range(buf, base):
    return bytes(dec_byte(buf[i], base + i) for i in range(len(buf)))

# 2) 블롭 끝 추정: 두 가지 신호로 교차 확인
#   (a) printable ASCII 비율 윈도우 (strict)
#   (b) 디코드 결과에서 4글자 이상 ASCII run 빈도

SCAN = min(400_000, len(dll) - off)
raw_scan = dll[off:off + SCAN]
dec_scan = decrypt_range(raw_scan, 0)

WINDOW = 512
THRESH = 0.30
def is_p(b): return (32 <= b < 127) or b in (0x09, 0x0A, 0x0D)

rolling = sum(1 for b in dec_scan[:WINDOW] if is_p(b))
end_a = None
for i in range(WINDOW, len(dec_scan)):
    if is_p(dec_scan[i - WINDOW]): rolling -= 1
    if is_p(dec_scan[i]):          rolling += 1
    if rolling / WINDOW < THRESH:
        for j in range(i, max(0, i - 1024), -1):
            if is_p(dec_scan[j]):
                end_a = j + 1
                break
        else:
            end_a = i
        break

# (b) 4글자 ASCII run 마지막 위치 (대안 추정)
end_b = 0
run = 0
for i, b in enumerate(dec_scan):
    if is_p(b):
        run += 1
        if run >= 4:
            end_b = i + 1
    else:
        run = 0

print(f"DLL 크기      : {len(dll):,}")
print(f"blob 시작     : offset {off} (0x{off:x})")
print(f"끝 추정 (a)   : {end_a}  (printable ratio < {THRESH})")
print(f"끝 추정 (b)   : {end_b}  (마지막 4글자+ ASCII run)")
print(f"기존 blob 크기: {len(old):,}")

# 보수적으로 둘 중 큰 값 사용 (한글이 섞인 영역도 포함하기 위해)
end = max(end_a or 0, end_b)
blob_len = end
print(f"\n채택한 길이   : {blob_len:,} bytes")

raw  = dll[off:off + blob_len]
dec  = decrypt_range(raw, 0)

(PLAY / "string_blob_windows.bin").write_bytes(raw)
(PLAY / "string_blob_windows.dec").write_bytes(dec)

# 3) 문자열 추출 (UTF-8 시도, 실패시 latin-1)
strings = []
i = 0
while i < len(dec):
    j = i
    while j < len(dec) and (is_p(dec[j]) or 0x80 <= dec[j] <= 0xBF or 0xC2 <= dec[j] <= 0xF4):
        j += 1
    if j - i >= 4:
        try:
            s = dec[i:j].decode("utf-8")
            strings.append((i, s))
        except UnicodeDecodeError:
            try:
                s = dec[i:j].decode("euc-kr")
                strings.append((i, s + "  # euc-kr"))
            except UnicodeDecodeError:
                strings.append((i, dec[i:j].decode("latin-1") + "  # latin-1"))
    i = max(j, i + 1)

with open(PLAY / "windows_strings.txt", "w", encoding="utf-8") as f:
    for offs, s in strings:
        s = s.replace("\n", "\\n").replace("\r", "\\r")
        f.write(f"{offs:6d}  {s}\n")

print(f"문자열 추출   : {len(strings)}개  → playground/windows_strings.txt")
print(f"\n--- 첫 15개 문자열 ---")
for o, s in strings[:15]:
    print(f"  {o:5d}: {s[:120]}")
print("\n--- 마지막 15개 문자열 ---")
for o, s in strings[-15:]:
    print(f"  {o:5d}: {s[:120]}")
