"""TCP MITM 프록시 — 클라/서버 간 라인 단위 NDJSON relay + 트래커 dispatch."""
from __future__ import annotations

import asyncio
import datetime
import json
from pathlib import Path

from .notify import log
from .tracker import Tracker


async def relay_lines(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    direction: str,
    tracker: Tracker,
    log_path: Path,
):
    """라인 단위로 파싱 + 트래커 dispatch + forward + 로그."""
    f = open(log_path, "ab")
    buf = b""
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            buf += chunk
            # 들어온 chunk 그대로 forward (지연 최소화)
            writer.write(chunk)
            await writer.drain()
            while True:
                nl = buf.find(b"\n")
                if nl < 0:
                    break
                line = buf[:nl]
                buf = buf[nl + 1 :]
                f.write(line + b"\n")
                f.flush()
                if not line.strip():
                    continue
                try:
                    pkt = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if direction == "S->C":
                    await tracker.on_packet_s2c(pkt)
                else:
                    await tracker.on_packet_c2s(pkt)
    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        f.close()
        try:
            writer.close()
        except Exception:
            pass


async def handle_client(
    client_reader,
    client_writer,
    tracker: Tracker,
    upstream: str,
    port: int,
    log_dir: Path,
):
    peer = client_writer.get_extra_info("peername")
    log(f"클라 연결 ({port}): {peer}", "dim")
    try:
        srv_reader, srv_writer = await asyncio.open_connection(upstream, port)
    except OSError as e:
        log(f"업스트림 실패 {upstream}:{port}: {e}", "err")
        client_writer.close()
        return

    tracker.client_writer = srv_writer

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir.mkdir(parents=True, exist_ok=True)
    c2s_log = log_dir / f"tracker_{port}_{stamp}.c2s.jsonl"
    s2c_log = log_dir / f"tracker_{port}_{stamp}.s2c.jsonl"
    if port == 7942 and tracker.inject_log is None:
        try:
            tracker.inject_log = open(
                log_dir / f"tracker_{port}_{stamp}.injected.jsonl", "ab"
            )
        except Exception:
            pass

    await asyncio.gather(
        relay_lines(client_reader, srv_writer, "C->S", tracker, c2s_log),
        relay_lines(srv_reader, client_writer, "S->C", tracker, s2c_log),
        return_exceptions=True,
    )
    log(f"세션 종료 ({port})", "dim")


async def passthrough(client_reader, client_writer, upstream: str, port: int):
    try:
        srv_reader, srv_writer = await asyncio.open_connection(upstream, port)
    except OSError:
        client_writer.close()
        return

    async def relay(r, w):
        try:
            while True:
                c = await r.read(65536)
                if not c:
                    break
                w.write(c)
                await w.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        finally:
            try:
                w.close()
            except Exception:
                pass

    await asyncio.gather(
        relay(client_reader, srv_writer),
        relay(srv_reader, client_writer),
        return_exceptions=True,
    )
