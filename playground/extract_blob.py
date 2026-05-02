#!/usr/bin/env python3
"""
decompiled C# 코드에서 _4 바이트 블롭을 추출해서 string_blob.bin으로 저장.
C# 코드에서 StringDecryptor.Decrypt()로 테스트할 수 있게 해줌.

실행: python3 extract_blob.py
"""
import re
from pathlib import Path

cs_path = Path(__file__).parent.parent / "decompiled" / "-PrivateImplementationDetails--AC6C2DFE-D87B-4B2C-94F2-0C219A0FF1EF-" / "3CDA3D22-BFAD-4812-B058-4341C38661CE.cs"
out_path = Path(__file__).parent / "string_blob.bin"

with open(cs_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

blob_bytes = []
in_blob = False
for line in lines:
    if 'internal static byte[] _4 = new byte[' in line:
        in_blob = True
        for n in re.findall(r'\b(\d+)\b', line)[1:]:
            v = int(n)
            if v <= 255: blob_bytes.append(v)
        continue
    if in_blob:
        if '};' in line: break
        for n in re.findall(r'\b(\d+)\b', line):
            v = int(n)
            if v <= 255: blob_bytes.append(v)

blob = bytes(blob_bytes)
out_path.write_bytes(blob)
print(f"추출 완료: {out_path}  ({len(blob)} bytes)")
