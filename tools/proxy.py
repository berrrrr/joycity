#!/usr/bin/env python3
"""
JoyTalk 투명 TCP 프록시 + 패킷 로거

사용법 A — pfctl 리다이렉트 (게임이 IP 하드코딩인 경우):
  1. sudo bash tools/pf_redirect.sh start
  2. python3 tools/proxy.py

사용법 B — hosts 리다이렉트 (게임이 DNS 사용하는 경우):
  1. sudo bash -c "echo '127.0.0.1 jc.joy-june.com' >> /etc/hosts"
  2. python3 tools/proxy.py --mode hosts

로그 파일: captures/proxy_<port>_<timestamp>.jsonl
"""

import asyncio
import argparse
import json
import struct
import sys
import time
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'server'))
from protocol import read_frame, parse_frame

# pfctl 모드: 게임이 IP 하드코딩인 경우
UPSTREAM_IP   = '119.200.71.233'
PROXY_SRC_IP  = '127.0.0.2'   # pf_redirect.sh가 추가하는 loopback alias
LOCAL_PORT_CHAT = 17942        # pfctl이 리다이렉트해주는 로컬 포트
LOCAL_PORT_GAME = 17945

# hosts 모드: 게임이 DNS 사용하는 경우 (기존 방식)
UPSTREAM_HOST = 'jc.joy-june.com'

LOG_DIR = Path(__file__).parent.parent / 'captures'


def ts() -> str:
    return datetime.datetime.now().isoformat(timespec='milliseconds')


class PacketLogger:
    def __init__(self, port: int):
        LOG_DIR.mkdir(exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.path = LOG_DIR / f'proxy_{port}_{stamp}.jsonl'
        self._f = open(self.path, 'w', encoding='utf-8')
        print(f'[proxy:{port}] 로그 → {self.path}')

    def log(self, direction: str, parsed: dict):
        entry = {'ts': ts(), 'dir': direction, **parsed}
        line = json.dumps(entry, ensure_ascii=False, default=str)
        self._f.write(line + '\n')
        self._f.flush()

        # Pretty console output
        if parsed.get('type_byte') == 1:
            pkt = parsed.get('json', {})
            pkt_type = pkt.get('type', '?')
            arrow = '→ SRV' if direction == 'C→S' else '← SRV'
            print(f'  [{ts()}] {arrow}  type={pkt_type!r:25s}  {_summarize(pkt)}')
        elif parsed.get('type_byte') == 3:
            pass  # keepalive 무시
        elif parsed.get('type_byte') == 5:
            arrow = '→ SRV' if direction == 'C→S' else '← SRV'
            print(f'  [{ts()}] {arrow}  [BIN] seq={parsed.get("seq")}  name={parsed.get("name")!r}  len={len(parsed.get("data", b""))}')
        elif parsed.get('type_byte') == 6:
            pass  # voice ctrl

    def close(self):
        self._f.close()


def _summarize(pkt: dict) -> str:
    skip = {'type'}
    parts = [f'{k}={str(v)[:30]!r}' for k, v in pkt.items() if k not in skip]
    return '  '.join(parts[:4])


async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                direction: str, logger: PacketLogger):
    """Read frames from reader, log them, forward to writer."""
    try:
        while True:
            payload = await read_frame(reader)
            if payload is None:
                break
            parsed = parse_frame(payload)
            logger.log(direction, parsed)
            # Forward raw frame (re-wrap with length prefix)
            frame = struct.pack('<I', len(payload)) + payload
            writer.write(frame)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        writer.close()


async def handle_client(client_reader: asyncio.StreamReader,
                        client_writer: asyncio.StreamWriter,
                        upstream_host: str, upstream_port: int,
                        logger: PacketLogger,
                        local_bind: str | None = None):
    peer = client_writer.get_extra_info('peername')
    print(f'[proxy:{upstream_port}] 클라이언트 연결: {peer}')

    try:
        # local_bind: pfctl 모드에서 127.0.0.2 사용 → pf redirect 루프 방지
        kwargs = {}
        if local_bind:
            kwargs['local_addr'] = (local_bind, 0)
        srv_reader, srv_writer = await asyncio.open_connection(upstream_host, upstream_port, **kwargs)
    except OSError as e:
        print(f'[proxy:{upstream_port}] 업스트림 연결 실패: {e}')
        client_writer.close()
        return

    print(f'[proxy:{upstream_port}] 업스트림 연결됨: {upstream_host}:{upstream_port}')

    await asyncio.gather(
        relay(client_reader, srv_writer,    'C→S', logger),
        relay(srv_reader,    client_writer, 'S→C', logger),
        return_exceptions=True
    )

    print(f'[proxy:{upstream_port}] 세션 종료')


async def start_proxy(local_port: int, upstream_host: str, upstream_port: int,
                      local_bind: str | None = None):
    logger = PacketLogger(local_port)
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, upstream_host, upstream_port, logger, local_bind),
        '127.0.0.1', local_port
    )
    print(f'[proxy:{local_port}] 리스닝 → {upstream_host}:{upstream_port}')
    async with server:
        await server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description='JoyTalk TCP 프록시')
    parser.add_argument('--mode', choices=['pf', 'hosts'], default='pf',
                        help='pf=pfctl 리다이렉트 (IP 하드코딩 게임), hosts=/etc/hosts 방식')
    parser.add_argument('--upstream', default=None,
                        help='업스트림 호스트/IP (기본: 모드에 따라 자동)')
    parser.add_argument('--only', choices=['chat', 'game'], default=None,
                        help='특정 포트만 프록시')
    args = parser.parse_args()

    if args.mode == 'pf':
        upstream = args.upstream or UPSTREAM_IP
        local_bind = PROXY_SRC_IP
        chat_local = LOCAL_PORT_CHAT
        game_local = LOCAL_PORT_GAME
        print('JoyTalk 투명 프록시 — pfctl 모드')
        print(f'업스트림 IP: {upstream}')
        print(f'리스닝 포트: {chat_local} (chat), {game_local} (game)')
        print(f'프록시 outbound: {local_bind} (pfctl 루프 방지)')
        print()
        print('※ pfctl 리다이렉트가 먼저 활성화되어 있어야 함:')
        print('   sudo bash tools/pf_redirect.sh start')
        print('   sudo bash tools/pf_redirect.sh status  # 확인')
    else:
        upstream = args.upstream or UPSTREAM_HOST
        local_bind = None
        chat_local = 7942
        game_local = 7945
        print('JoyTalk 투명 프록시 — hosts 모드')
        print(f'업스트림: {upstream}')
        print()
        print('※ /etc/hosts 수정 필요:')
        print(f'   sudo bash -c "echo \'127.0.0.1 {upstream}\' >> /etc/hosts"')

    print()

    tasks = []
    if args.only != 'game':
        tasks.append(start_proxy(chat_local, upstream, 7942, local_bind))
    if args.only != 'chat':
        tasks.append(start_proxy(game_local, upstream, 7945, local_bind))

    async def run():
        await asyncio.gather(*tasks)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print('\n[proxy] 종료')


if __name__ == '__main__':
    main()
