#!/usr/bin/env python3
"""
JoyTalk 서버 에뮬레이터

사용법:
  python3 emulator.py [--host 0.0.0.0] [--port-game 7945] [--port-chat 7942]

게임 클라이언트가 이 서버로 연결하려면:
  sudo bash -c "echo '127.0.0.1 jc.joy-june.com' >> /etc/hosts"
"""

import asyncio
import argparse
import json
import struct
import time
import itertools
from typing import Optional, Dict

from protocol import read_frame, parse_frame, make_json_frame, make_keepalive_frame
from handlers import dispatch, _remove_player


class Session:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 server: 'GameServer'):
        self.reader = reader
        self.writer = writer
        self.server = server
        self.my_id: Optional[int] = None
        self.userid: str = ''
        self._lock = asyncio.Lock()

    async def send_json(self, data: dict):
        frame = make_json_frame(data)
        async with self._lock:
            self.writer.write(frame)
            await self.writer.drain()

    async def run(self):
        peer = self.writer.get_extra_info('peername')
        print(f'[session] 연결: {peer}')
        try:
            while True:
                payload = await read_frame(self.reader)
                if payload is None:
                    break
                parsed = parse_frame(payload)
                await self._handle(parsed)
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            await _remove_player(self)
            self.server.sessions.discard(self)
            self.writer.close()
            print(f'[session] 종료: {peer}  userid={self.userid!r}')

    async def _handle(self, parsed: dict):
        tb = parsed.get('type_byte')

        if tb == 3:  # keepalive
            frame = make_keepalive_frame()
            async with self._lock:
                self.writer.write(frame)
                await self.writer.drain()
            return

        if tb == 1:  # JSON
            pkt = parsed.get('json', {})
            pkt_type = pkt.get('type', '')
            if pkt_type:
                await dispatch(self, pkt_type, pkt)
            return

        if tb == 5:  # 바이너리 게임 패킷
            name = parsed.get('name', '')
            print(f'  [bin] seq={parsed.get("seq")}  name={name!r}  len={len(parsed.get("data", b""))}')
            return


class GameServer:
    def __init__(self):
        self.sessions: set[Session] = set()
        self.objects: Dict[int, object] = {}  # id → GameObject
        self._id_counter = itertools.count(1000001)

    def next_id(self) -> int:
        return next(self._id_counter)

    async def broadcast(self, data: dict):
        frame = make_json_frame(data)
        dead = set()
        for s in list(self.sessions):
            try:
                async with s._lock:
                    s.writer.write(frame)
                    await s.writer.drain()
            except (ConnectionResetError, BrokenPipeError):
                dead.add(s)
        self.sessions -= dead

    async def broadcast_except(self, exclude_id: int, data: dict):
        frame = make_json_frame(data)
        for s in list(self.sessions):
            if s.my_id != exclude_id:
                try:
                    async with s._lock:
                        s.writer.write(frame)
                        await s.writer.drain()
                except (ConnectionResetError, BrokenPipeError):
                    pass

    async def keepalive_loop(self):
        frame = make_keepalive_frame()
        while True:
            await asyncio.sleep(30)
            for s in list(self.sessions):
                try:
                    async with s._lock:
                        s.writer.write(frame)
                        await s.writer.drain()
                except Exception:
                    pass

    async def handle_client(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):
        session = Session(reader, writer, self)
        self.sessions.add(session)
        await session.run()

    async def start(self, host: str, ports: list[int]):
        servers = []
        for port in ports:
            srv = await asyncio.start_server(self.handle_client, host, port)
            servers.append(srv)
            print(f'[emulator] 리스닝: {host}:{port}')

        print(f'[emulator] 준비 완료 — 클라이언트 대기 중...')
        print()

        asyncio.create_task(self.keepalive_loop())

        async with asyncio.TaskGroup() as tg:
            for srv in servers:
                tg.create_task(srv.serve_forever())


def main():
    parser = argparse.ArgumentParser(description='JoyTalk 서버 에뮬레이터')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port-game', type=int, default=7945)
    parser.add_argument('--port-chat', type=int, default=7942)
    parser.add_argument('--game-only', action='store_true')
    parser.add_argument('--chat-only', action='store_true')
    args = parser.parse_args()

    ports = []
    if not args.game_only:
        ports.append(args.port_chat)
    if not args.chat_only:
        ports.append(args.port_game)

    print('=' * 50)
    print('  JoyTalk 서버 에뮬레이터')
    print('=' * 50)
    print()
    print('※ 클라이언트 리다이렉트:')
    print('  sudo bash -c "echo \'127.0.0.1 jc.joy-june.com\' >> /etc/hosts"')
    print()
    print('※ 원복:')
    print('  sudo sed -i \'\' \'/jc.joy-june.com/d\' /etc/hosts')
    print()

    server = GameServer()
    try:
        asyncio.run(server.start(args.host, ports))
    except KeyboardInterrupt:
        print('\n[emulator] 종료')


if __name__ == '__main__':
    main()
