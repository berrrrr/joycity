#!/usr/bin/env python3
"""
JoyTalk 서버 에뮬레이터 (NDJSON, Phase 4 발견 반영)

와이어 포맷:
  각 패킷은 `{...JSON...}\\n` 한 줄. envelope/length-prefix 없음.
  Phase 3 의 [u32 len][type byte] framing 은 macOS 빌드 잔재 — Windows 빌드 미사용.
  자세한 내용은 docs/phase4_live_capture.md.

사용법 (Windows):
  관리자 PowerShell:
    Add-Content C:\\Windows\\System32\\drivers\\etc\\hosts "127.0.0.1 jc.joy-june.com"
  일반 셸:
    py -3.11 server\\emulator.py
    & "C:\\Users\\berrr\\AppData\\Local\\Joytalk\\Joytalk.exe"

사용법 (macOS):
    sudo bash -c "echo '127.0.0.1 jc.joy-june.com' >> /etc/hosts"
    python3 server/emulator.py
"""

import argparse
import asyncio
import io
import itertools
import json
import sys
from typing import Optional, Dict

from handlers import dispatch, _remove_player

# 진짜 jc.joy-june.com — CefSharp HTTPS/HTTP 요청을 통과시키기 위한 fallback
REAL_UPSTREAM = "119.200.71.233"


class Session:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 server: "GameServer"):
        self.reader = reader
        self.writer = writer
        self.server = server
        self.my_id: Optional[int] = None
        self.userid: str = ""
        self._lock = asyncio.Lock()

    async def send_json(self, data: dict):
        line = json.dumps(data, ensure_ascii=False).encode("utf-8") + b"\n"
        async with self._lock:
            self.writer.write(line)
            await self.writer.drain()

    async def run(self):
        peer = self.writer.get_extra_info("peername")
        print(f"[session] 연결: {peer}")
        try:
            while True:
                line = await self.reader.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    pkt = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError as e:
                    print(f"  [parse-error] {e}: {line[:80]!r}")
                    continue
                await self._handle(pkt)
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            await _remove_player(self)
            self.server.sessions.discard(self)
            self.writer.close()
            print(f"[session] 종료: {peer}  userid={self.userid!r}")

    async def _handle(self, pkt: dict):
        pkt_type = pkt.get("type", "")
        if not pkt_type:
            return
        await dispatch(self, pkt_type, pkt)


class GameServer:
    def __init__(self):
        self.sessions: set[Session] = set()
        self.objects: Dict[int, object] = {}     # object id → GameObject
        self._id_counter = itertools.count(9168) # 캡처에서 본 첫 myId

    def next_id(self) -> int:
        return next(self._id_counter)

    async def _send(self, session: "Session", line: bytes):
        try:
            async with session._lock:
                session.writer.write(line)
                await session.writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            self.sessions.discard(session)

    async def broadcast(self, data: dict):
        line = json.dumps(data, ensure_ascii=False).encode("utf-8") + b"\n"
        for s in list(self.sessions):
            await self._send(s, line)

    async def broadcast_except(self, exclude_id: int, data: dict):
        line = json.dumps(data, ensure_ascii=False).encode("utf-8") + b"\n"
        for s in list(self.sessions):
            if s.my_id != exclude_id:
                await self._send(s, line)

    async def keepalive_loop(self):
        """Phase 4 캡처상 서버는 명시적 keepalive 안 보냄. 향후 ping push 가 필요하면 여기서."""
        while True:
            await asyncio.sleep(60)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        session = Session(reader, writer, self)
        self.sessions.add(session)
        await session.run()

    async def start(self, host: str, ports: list[int],
                    passthrough_ports: list[int] | None = None,
                    upstream: str = REAL_UPSTREAM):
        servers = []
        for port in ports:
            srv = await asyncio.start_server(self.handle_client, host, port)
            servers.append(srv)
            print(f"[emulator] 리스닝: {host}:{port}")

        # 80/443 raw passthrough (CefSharp 인앱 브라우저 우회)
        for pp in (passthrough_ports or []):
            srv = await asyncio.start_server(
                lambda r, w, p=pp: _handle_passthrough(r, w, upstream, p),
                host, pp,
            )
            servers.append(srv)
            print(f"[passthrough] {host}:{pp} → {upstream}:{pp}")

        print("[emulator] 준비 완료 — 클라이언트 대기 중...\n")
        asyncio.create_task(self.keepalive_loop())

        async with asyncio.TaskGroup() as tg:
            for srv in servers:
                tg.create_task(srv.serve_forever())


async def _passthrough_relay(reader, writer):
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        writer.close()


async def _handle_passthrough(client_reader, client_writer, upstream_host, port):
    try:
        srv_reader, srv_writer = await asyncio.open_connection(upstream_host, port)
    except OSError as e:
        print(f"[passthrough:{port}] 업스트림 실패: {e}")
        client_writer.close()
        return
    await asyncio.gather(
        _passthrough_relay(client_reader, srv_writer),
        _passthrough_relay(srv_reader, client_writer),
        return_exceptions=True,
    )


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="JoyTalk 서버 에뮬레이터 (NDJSON)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, action="append",
                   help="리스닝 포트 (반복 지정 가능, 기본: 7942 7945)")
    p.add_argument("--no-passthrough", action="store_true",
                   help="80/443 HTTP/HTTPS passthrough 안 띄움")
    p.add_argument("--upstream", default=REAL_UPSTREAM,
                   help=f"passthrough 업스트림 IP (기본 {REAL_UPSTREAM} = jc.joy-june.com)")
    args = p.parse_args()

    ports = args.port or [7942, 7945]
    pass_ports = [] if args.no_passthrough else [80, 443]

    print("=" * 50)
    print("  JoyTalk 서버 에뮬레이터 (NDJSON)")
    print("=" * 50)
    print()
    print("hosts 리다이렉트 (Windows 관리자 PowerShell):")
    print('  Add-Content C:\\Windows\\System32\\drivers\\etc\\hosts "127.0.0.1 jc.joy-june.com"')
    print()

    server = GameServer()
    try:
        asyncio.run(server.start(args.host, ports,
                                 passthrough_ports=pass_ports,
                                 upstream=args.upstream))
    except KeyboardInterrupt:
        print("\n[emulator] 종료")


if __name__ == "__main__":
    main()
