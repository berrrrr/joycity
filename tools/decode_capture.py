#!/usr/bin/env python3
"""
프록시가 저장한 .jsonl 캡처 파일 분석 도구

사용법:
  python3 decode_capture.py captures/proxy_7945_*.jsonl
  python3 decode_capture.py captures/proxy_7945_*.jsonl --filter login,obj,move
  python3 decode_capture.py captures/proxy_7945_*.jsonl --stats
"""

import argparse
import json
import sys
from pathlib import Path
from collections import Counter


def load_entries(paths: list[Path]) -> list[dict]:
    entries = []
    for p in paths:
        with open(p, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return entries


def print_entry(e: dict, show_full: bool = False):
    ts = e.get('ts', '')
    direction = e.get('dir', '?')
    tb = e.get('type_byte')

    if tb == 1:
        pkt = e.get('json', {})
        pkt_type = pkt.get('type', '?')
        arrow = '→ SRV' if direction == 'C→S' else '← SRV'
        fields = {k: v for k, v in pkt.items() if k != 'type'}
        if show_full:
            print(f'[{ts}] {arrow} {pkt_type}')
            for k, v in fields.items():
                val = str(v)
                if len(val) > 200:
                    val = val[:200] + '...'
                print(f'      {k}: {val}')
        else:
            summary = '  '.join(f'{k}={str(v)[:40]!r}' for k, v in list(fields.items())[:5])
            print(f'[{ts}] {arrow} {pkt_type:25s}  {summary}')

    elif tb == 5:
        arrow = '→ SRV' if direction == 'C→S' else '← SRV'
        print(f'[{ts}] {arrow} [BIN:{e.get("name")}] seq={e.get("seq")} len={len(e.get("data",""))}')

    elif tb == 3:
        pass  # keepalive


def print_stats(entries: list[dict]):
    cs_types = Counter()
    sc_types = Counter()

    for e in entries:
        if e.get('type_byte') != 1:
            continue
        pkt_type = e.get('json', {}).get('type', '?')
        if e.get('dir') == 'C→S':
            cs_types[pkt_type] += 1
        else:
            sc_types[pkt_type] += 1

    print('=== 클라이언트 → 서버 패킷 통계 ===')
    for t, c in cs_types.most_common():
        print(f'  {t:30s} × {c}')

    print()
    print('=== 서버 → 클라이언트 패킷 통계 ===')
    for t, c in sc_types.most_common():
        print(f'  {t:30s} × {c}')


def main():
    parser = argparse.ArgumentParser(description='JoyTalk 캡처 분석')
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--filter', '-f', help='쉼표 구분 패킷 타입 필터')
    parser.add_argument('--stats', '-s', action='store_true', help='통계만 출력')
    parser.add_argument('--full', action='store_true', help='패킷 전체 필드 출력')
    parser.add_argument('--direction', choices=['C→S', 'S→C'], help='방향 필터')
    args = parser.parse_args()

    entries = load_entries(args.files)
    print(f'총 {len(entries)}개 엔트리 로드됨\n')

    if args.stats:
        print_stats(entries)
        return

    filter_types = set(args.filter.split(',')) if args.filter else None

    for e in entries:
        tb = e.get('type_byte')
        if tb == 3:
            continue  # keepalive 스킵

        if args.direction and e.get('dir') != args.direction:
            continue

        if filter_types and tb == 1:
            pkt_type = e.get('json', {}).get('type', '')
            if pkt_type not in filter_types:
                continue

        print_entry(e, show_full=args.full)


if __name__ == '__main__':
    main()
