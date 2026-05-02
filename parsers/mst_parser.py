#!/usr/bin/env python3
"""
MST Parser - JcMsgList Table binary item/message database
Used by JoyTalk for item text data (item.mst, item_hc.mst, etc.)

Binary structure:
  [1]   u8    header_len (15)
  [15]  str   "JcMsgList Table"
  [4]   u32   (count/metadata)
  [4]   u32   (metadata)
  ... header padding to offset ~919 ...

Each record (scanning for [code_len][ASCII code][0x01][0x80] pattern):
  [1]   u8    code_len
  [N]   str   ASCII code (e.g. "Y00099_0")
  [1]   u8    0x01
  [1]   u8    0x80  <- end of code section
  [4]   u32   type_id
  [4]   u32   item_num
  [4]   u32   flags
  [2]   bytes class_code (2 ASCII chars like "E0")
  ';'
  [EUC-KR name] ';'
  [EUC-KR detail] ';'
  [EUC-KR price_formula] ';' ';' ';'
  <- next record or end
"""

import struct
import sys
from dataclasses import dataclass
from typing import Optional


HEADER_MAGIC = "JcMsgList Table"


@dataclass
class MstItem:
    code: str
    type_id: int
    item_num: int
    flags: int
    class_code: str
    name: str
    detail: str
    price_formula: str


def read_euckr(data: bytes, pos: int, length: int) -> str:
    if length <= 0:
        return ""
    return data[pos:pos + length].decode('cp949', errors='replace')


def find_semicolon(data: bytes, pos: int) -> int:
    """Find next ';' (0x3b) from pos"""
    idx = data.find(0x3b, pos)
    return idx if idx != -1 else len(data)


def parse(filepath: str) -> list[MstItem]:
    with open(filepath, 'rb') as f:
        data = f.read()

    # Validate header
    hdr_len = data[0]
    header = data[1:1 + hdr_len].decode('ascii', errors='replace')
    if header != HEADER_MAGIC:
        raise ValueError(f"Not a MST file: header='{header}'")

    items = []
    pos = 16  # skip 1-byte len + 15-byte magic + 4-byte count... actually scan from after header

    # Scan entire file for record pattern: [code_len][ASCII code][0x01][0x80]
    while pos < len(data) - 12:
        code_len = data[pos]
        if 3 <= code_len <= 15:
            code_end = pos + 1 + code_len
            if (code_end + 1 < len(data)
                    and data[code_end] == 0x01
                    and data[code_end + 1] == 0x80):
                # Verify code is ASCII printable
                code_bytes = data[pos + 1:code_end]
                if all(32 <= b < 128 for b in code_bytes):
                    code = code_bytes.decode('ascii')
                    meta_start = code_end + 2  # skip 0x01 0x80

                    # Read metadata: [u32 type_id][u32 item_num][u32 flags][2 bytes class_code]
                    if meta_start + 14 > len(data):
                        pos += 1
                        continue
                    type_id, item_num, flags = struct.unpack_from('<III', data, meta_start)
                    class_code = data[meta_start + 12:meta_start + 14].decode('ascii', errors='replace')

                    field_pos = meta_start + 14  # points to first ';'
                    if field_pos >= len(data) or data[field_pos] != 0x3b:
                        pos += 1
                        continue
                    field_pos += 1  # skip ';'

                    # name
                    semi = find_semicolon(data, field_pos)
                    name = read_euckr(data, field_pos, semi - field_pos)
                    field_pos = semi + 1

                    # detail
                    semi = find_semicolon(data, field_pos)
                    detail = read_euckr(data, field_pos, semi - field_pos)
                    field_pos = semi + 1

                    # price formula
                    semi = find_semicolon(data, field_pos)
                    price = read_euckr(data, field_pos, semi - field_pos)

                    items.append(MstItem(
                        code=code, type_id=type_id, item_num=item_num,
                        flags=flags, class_code=class_code,
                        name=name, detail=detail, price_formula=price
                    ))
                    pos = code_end + 1
                    continue
        pos += 1

    return items


def main():
    if len(sys.argv) < 2:
        path = "/Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Res/Lst/item.mst"
    else:
        path = sys.argv[1]

    print(f"Parsing: {path}")
    items = parse(path)
    print(f"Total items: {len(items)}")
    for item in items[:10]:
        print(f"  [{item.code}] #{item.item_num} type={item.type_id} "
              f"name='{item.name}' detail='{item.detail[:40]}...'")


if __name__ == "__main__":
    main()
