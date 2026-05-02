# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**joycity** is a Python 3.13 reverse-engineering toolkit for the JoyTalk Korean online game client. It contains binary file parsers for game assets and network tools for packet capture and analysis.

## Environment

- Python 3.13 (Homebrew), virtualenv at `venv/`
- No external dependencies — stdlib only (`asyncio`, `struct`, `json`, `pathlib`, etc.)
- No build system, test framework, or package configuration files

Activate virtualenv before running:
```bash
source venv/bin/activate
```

## Running the Tools

```bash
# TCP proxy — intercepts game traffic (requires /etc/hosts redirect or --upstream)
python3 tools/proxy.py [--port PORT] [--upstream HOST]

# Item spawn tracker with filtering and notifications
python3 tools/item_tracker.py [--filter NAME] [--type TYPE] [--discord WEBHOOK_URL]

# Analyze captured JSONL packet logs
python3 tools/decode_capture.py captures/proxy_*.jsonl [--filter TYPE] [--stats] [--full] [--direction]

# Run any parser standalone (uses default JoyTalk app path on macOS)
python3 parsers/jcr_parser.py [FILE]
python3 parsers/mst_parser.py [FILE]
python3 parsers/csmi_parser.py [FILE]
python3 parsers/irs_parser.py [FILE]
python3 parsers/rmm_parser.py [FILE]
```

## Architecture

### `parsers/` — Binary File Parsers

All parsers target JoyTalk game data files under `/Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/`. Each parser uses `struct.unpack` to decode proprietary binary formats:

| File | Format | Key Data |
|------|--------|----------|
| `jcr_parser.py` | Joycity RAW sprite | RLE-encoded pixel frames → PPM images |
| `mst_parser.py` | JcMsgList Table | Item/message database; EUC-KR/CP949 text |
| `csmi_parser.py` | CSMI File 2.0 | Map object placement, sprite layers, collision |
| `irs_parser.py` | Resource File | Tile sprite container with frame offset table |
| `rmm_parser.py` | RedMoon MapData 1.0 | 2D tile map; grid cells with packed bitfields |

Parsers expose Python dataclasses (`MstItem`, `CsmiObject`, `RmmMap`, `Cell`, etc.) and can be imported as modules or run standalone.

### `tools/` — Network Tools

All network tools act as transparent TCP proxies against `jc.joy-june.com` (ports 7942 chat, 7945 game). They log to `captures/` as JSONL files.

- **`proxy.py`** — Base proxy; logs all frames as JSON/binary
- **`item_tracker.py`** — Extends proxy with real-time filtering on `obj`, `objc`, `remove`, `delta` packets; supports macOS notifications and Discord webhooks
- **`decode_capture.py`** — Offline analysis of captured JSONL files

**Missing dependency**: `proxy.py` and `item_tracker.py` import a `protocol` module from `../server/` (not included in this repo). This module is required for packet parsing/framing.

## Key Conventions

- Korean text appears throughout (comments, string output, variable names) — the game is Korean; terminal must support UTF-8
- `captures/` directory is created at runtime; `.jsonl` files accumulate there
- Network tools require `/etc/hosts` redirection (`jc.joy-june.com → 127.0.0.1`) or pass `--upstream HOSTNAME` to forward traffic
- Parsers with palette data (`irs_parser.py`) return raw palette indices; caller must supply the palette
