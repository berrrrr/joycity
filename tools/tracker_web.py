#!/usr/bin/env python3
"""
JoyTalk Tracker — Web UI 모듈.

item_tracker.py 의 Tracker 인스턴스를 받아서 HTTP/SSE 서버 시작.
HTML/CSS/JS 는 같은 디렉터리의 tracker_web.html 에서 읽음.

Endpoints:
  GET  /              HTML 페이지
  GET  /state         현재 상태 JSON
  GET  /map.json      현재 맵의 학습된 walkable/blocked 셀
  GET  /events        SSE 스트림 (log + state + config push)
  POST /api/config    런타임 설정 변경
  POST /api/clear-blacklist
"""
from __future__ import annotations

import asyncio
import json
import pathlib
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from item_tracker.tracker import Tracker

HTML_PATH = pathlib.Path(__file__).resolve().parent / "tracker_web.html"

# start_web() 호출 시 채워짐
_TRACKER: Optional["Tracker"] = None
_LOG_BUF = None
_SSE_QUEUES: list[asyncio.Queue] = []
_LOG_FN = None  # log 콜백 (item_tracker.log)


def _config_dict(args) -> dict:
    return {
        "filter": args.filter or "",
        "types": args.types or "",
        "pickup": bool(args.pickup),
        "auto_walk": bool(args.auto_walk),
        "wander": bool(getattr(args, "wander", False)),
        "auto_smile": bool(getattr(args, "auto_smile", False)),
        "hourly_burst": bool(getattr(args, "hourly_burst", False)),
        "teleport": bool(getattr(args, "teleport", False)),
        "stealth": bool(args.stealth),
        "max_dist": args.max_dist,
        "cooldown": args.cooldown,
        "walk_interval": args.walk_interval,
        "step_size": args.step_size,
        "smile_motion": getattr(args, "smile_motion", 62),
    }


def _state_dict(t) -> dict:
    items_list = []
    for oid, (name, x, y) in t.items.items():
        if t.matches(name):
            dx, dy = x - t.my_x, y - t.my_y
            items_list.append({"oid": oid, "name": name, "x": x, "y": y,
                               "dist": (dx * dx + dy * dy) ** 0.5})
    cmap = t._cmap()
    return {
        "kind": "state",
        "connected": t.client_writer is not None,
        "my_id": t.my_id, "my_x": t.my_x, "my_y": t.my_y,
        "server_x": t.server_x, "server_y": t.server_y,
        "walk_target": list(t.walk_target) if t.walk_target else None,
        "items": items_list,
        "max_dist": t.args.max_dist,
        "map_id": t.current_map,
        "walkable_cells": len(cmap.walkable) if cmap else 0,
        "blocked_cells": len(cmap.blocked) if cmap else 0,
        "path_remaining": len(t.path),
    }


async def _write_response(writer, status: int, body: bytes,
                          content_type: str = "application/json; charset=utf-8"):
    headers = [
        f"HTTP/1.1 {status} OK",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body)}",
        "Cache-Control: no-store",
        "Connection: close",
        "\r\n",
    ]
    writer.write("\r\n".join(headers).encode("utf-8") + body)
    try:
        await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass


def _broadcast_to_sse(payload: str):
    for q in _SSE_QUEUES:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


async def _handle(reader, writer):
    try:
        req_line = await reader.readline()
        if not req_line:
            writer.close(); return
        try:
            method, path, _ = req_line.decode("latin-1").strip().split(" ", 2)
        except ValueError:
            writer.close(); return
        headers = {}
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            try:
                k, _, v = line.decode("latin-1").partition(":")
                headers[k.strip().lower()] = v.strip()
            except Exception:
                pass
        body = b""
        clen = int(headers.get("content-length", "0") or 0)
        if clen:
            body = await reader.readexactly(clen)

        if path == "/" or path.startswith("/?"):
            html = HTML_PATH.read_bytes()
            await _write_response(writer, 200, html, "text/html; charset=utf-8")
            return
        if path == "/state":
            data = json.dumps(_state_dict(_TRACKER), ensure_ascii=False).encode("utf-8")
            await _write_response(writer, 200, data); return
        if path == "/map.json":
            cmap = _TRACKER._cmap()
            data = json.dumps(cmap.to_dict() if cmap else {"walkable": [], "blocked": []},
                              ensure_ascii=False).encode("utf-8")
            await _write_response(writer, 200, data); return
        if path == "/api/config" and method == "POST":
            try:
                cfg = json.loads(body.decode("utf-8") or "{}")
            except Exception:
                cfg = {}
            t = _TRACKER
            if "filter" in cfg:
                t.args.filter = cfg["filter"] or ""
                t.filters = [f.strip() for f in t.args.filter.split(",") if f.strip()]
            if "types" in cfg:
                t.args.types = cfg["types"] or ""
                t.types = set(s for s in t.args.types.split(",") if s)
            for k in ("pickup", "auto_walk", "wander", "auto_smile",
                      "hourly_burst", "teleport", "stealth"):
                if k in cfg:
                    setattr(t.args, k, bool(cfg[k]))
            for k in ("max_dist", "cooldown", "walk_interval"):
                if k in cfg and cfg[k] is not None:
                    try: setattr(t.args, k, float(cfg[k]))
                    except (TypeError, ValueError): pass
            for k in ("step_size", "smile_motion"):
                if k in cfg and cfg[k] is not None:
                    try: setattr(t.args, k, int(cfg[k]))
                    except (TypeError, ValueError): pass
            if _LOG_FN:
                _LOG_FN(f"[config] filter={t.args.filter!r} pickup={t.args.pickup} "
                        f"walk={t.args.auto_walk} smile={getattr(t.args,'auto_smile',False)} "
                        f"hourly={getattr(t.args,'hourly_burst',False)}", "info")
            data = json.dumps(_config_dict(t.args)).encode("utf-8")
            await _write_response(writer, 200, data)
            _broadcast_to_sse(json.dumps({"kind": "config", **_config_dict(t.args)}))
            return
        if path == "/api/clear-blacklist" and method == "POST":
            n = len(_TRACKER.blacklist)
            _TRACKER.blacklist.clear()
            if _LOG_FN:
                _LOG_FN(f"[config] blacklist cleared ({n} entries)", "info")
            await _write_response(writer, 200, b'{"ok":true}')
            return
        if path == "/api/shutdown" and method == "POST":
            if _LOG_FN:
                _LOG_FN("[shutdown] 웹에서 종료 요청 — 프로세스 종료", "warn")
            await _write_response(writer, 200, b'{"ok":true,"msg":"shutting down"}')
            # 누적 학습 저장 후 즉시 종료
            try:
                for cmap in _TRACKER.cmaps.values():
                    cmap.save_persist()
            except Exception:
                pass
            import os
            os._exit(0)
        if path == "/api/save-collision" and method == "POST":
            saved = 0
            for cmap in _TRACKER.cmaps.values():
                cmap._dirty = True
                cmap.save_persist()
                saved += 1
            if _LOG_FN:
                _LOG_FN(f"[shutdown] collision 학습 강제 저장 ({saved} 맵)", "info")
            await _write_response(writer, 200, b'{"ok":true}')
            return
        if path == "/events":
            head = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/event-stream; charset=utf-8\r\n"
                "Cache-Control: no-store\r\n"
                "Connection: keep-alive\r\n\r\n"
            ).encode("utf-8")
            writer.write(head); await writer.drain()
            init_cfg = json.dumps({"kind": "config", **_config_dict(_TRACKER.args)})
            init_state = json.dumps(_state_dict(_TRACKER), ensure_ascii=False)
            writer.write(f"data: {init_cfg}\n\n".encode("utf-8"))
            writer.write(f"data: {init_state}\n\n".encode("utf-8"))
            for entry in list(_LOG_BUF or [])[-100:]:
                payload = json.dumps({"kind": "log", **entry}, ensure_ascii=False)
                writer.write(f"data: {payload}\n\n".encode("utf-8"))
            await writer.drain()
            q: asyncio.Queue = asyncio.Queue(maxsize=1000)
            _SSE_QUEUES.append(q)
            try:
                while True:
                    msg = await q.get()
                    writer.write(f"data: {msg}\n\n".encode("utf-8"))
                    await writer.drain()
            except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
                pass
            finally:
                if q in _SSE_QUEUES:
                    _SSE_QUEUES.remove(q)
            return

        await _write_response(writer, 404, b"not found", "text/plain")
    except Exception as e:
        try:
            await _write_response(writer, 500, f"err: {e}".encode("utf-8"), "text/plain")
        except Exception:
            pass
    finally:
        try: writer.close()
        except Exception: pass


async def state_broadcast_loop(interval: float = 1.0):
    """주기적으로 state 를 SSE 로 push."""
    while True:
        await asyncio.sleep(interval)
        if not _SSE_QUEUES or _TRACKER is None:
            continue
        payload = json.dumps(_state_dict(_TRACKER), ensure_ascii=False)
        _broadcast_to_sse(payload)


async def start(host: str, port: int, tracker, log_buf, sse_queues, log_fn=None):
    """웹 UI 서버 시작 + state push 루프 등록.

    호출자: item_tracker.run() 에서 args.web 일 때.
    리턴: (asyncio.Server, state_broadcast_task)
    """
    global _TRACKER, _LOG_BUF, _SSE_QUEUES, _LOG_FN
    _TRACKER = tracker
    _LOG_BUF = log_buf
    _SSE_QUEUES = sse_queues
    _LOG_FN = log_fn
    srv = await asyncio.start_server(_handle, host, port)
    return srv
