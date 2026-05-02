"""
JoyTalk TCP protocol framing and serialization.

TCP envelope:    [u32 length LE][payload]
Payload types:
  1 → JSON text:  [u8=1][i16 json_len LE][UTF-8 JSON]
  3 → keepalive:  [u8=3]
  5 → binary game:[u8=5][u16 seq LE][u8 type_len][type_name bytes][payload]
  6 → voice ctrl: [u8=6][flag][message]
"""

import asyncio
import json
import struct
from typing import Optional


# ── Frame reading ──────────────────────────────────────────────────────────────

async def read_frame(reader: asyncio.StreamReader) -> Optional[bytes]:
    """Read one [u32 len][payload] frame. Returns payload bytes or None on EOF."""
    hdr = await reader.readexactly(4)
    length = struct.unpack_from('<I', hdr)[0]
    if length == 0:
        return b''
    return await reader.readexactly(length)


def make_json_frame(data: dict) -> bytes:
    """Serialize dict → JSON → type-1 TCP frame."""
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    inner = struct.pack('<Bh', 1, len(payload)) + payload
    return struct.pack('<I', len(inner)) + inner


def make_keepalive_frame() -> bytes:
    return struct.pack('<IB', 1, 3)


def make_binary_frame(seq: int, type_name: str, payload: bytes) -> bytes:
    """Build type-5 binary game frame."""
    name_bytes = type_name.encode('utf-8')
    inner_payload = (
        struct.pack('<HB', seq, len(name_bytes))
        + name_bytes
        + payload
    )
    outer = struct.pack('<B', 5) + inner_payload
    return struct.pack('<I', len(outer)) + outer


# ── Frame parsing ──────────────────────────────────────────────────────────────

def parse_frame(payload: bytes) -> dict:
    """Parse a raw payload into a structured dict for logging/handling."""
    if not payload:
        return {'type_byte': 0, 'raw': b''}

    type_byte = payload[0]

    if type_byte == 1:  # JSON
        json_len = struct.unpack_from('<h', payload, 1)[0]
        json_bytes = payload[3:3 + json_len]
        try:
            return {'type_byte': 1, 'json': json.loads(json_bytes)}
        except json.JSONDecodeError:
            return {'type_byte': 1, 'raw_json': json_bytes}

    if type_byte == 3:  # keepalive
        return {'type_byte': 3}

    if type_byte == 5:  # binary game packet
        seq = struct.unpack_from('<H', payload, 1)[0]
        name_len = payload[3]
        name = payload[4:4 + name_len].decode('utf-8', errors='replace')
        data = payload[4 + name_len:]
        return {'type_byte': 5, 'seq': seq, 'name': name, 'data': data}

    if type_byte == 6:  # voice control
        return {'type_byte': 6, 'raw': payload[1:]}

    return {'type_byte': type_byte, 'raw': payload}
