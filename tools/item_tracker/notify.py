"""로그 + 알림 + SSE 큐 + ANSI 색.

LOG_BUF 와 SSE_QUEUES 는 tracker_web 과 공유되는 상태.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import socket
import sys
import urllib.error
import urllib.request
from collections import deque

# ── 로그 버퍼 (웹 UI SSE 용) ─────────────────────────────────────────────────
LOG_BUF: deque[dict] = deque(maxlen=500)
SSE_QUEUES: list[asyncio.Queue] = []

# ── ANSI 색 (Windows 11 기본 터미널 지원) ────────────────────────────────────
C_RESET = "\x1b[0m"
C_BOLD = "\x1b[1m"
C_RED = "\x1b[91m"
C_GREEN = "\x1b[92m"
C_YELLOW = "\x1b[93m"
C_BLUE = "\x1b[94m"
C_MAGENTA = "\x1b[95m"
C_CYAN = "\x1b[96m"
C_GRAY = "\x1b[90m"


def ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(msg: str, level: str = "info"):
    """콘솔 출력 + 웹 SSE 큐로 push.

    level: info | success | warn | err | dim
    """
    entry = {"ts": ts(), "level": level, "msg": msg}
    LOG_BUF.append(entry)
    color = {
        "success": C_GREEN + C_BOLD,
        "warn": C_YELLOW,
        "err": C_RED,
        "dim": C_GRAY,
    }.get(level, "")
    print(f"{color}[{entry['ts']}] {msg}{C_RESET}")
    payload = json.dumps({"kind": "log", **entry}, ensure_ascii=False)
    for q in SSE_QUEUES:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def beep():
    """Windows 시스템 비프. 비차단."""
    try:
        import winsound

        winsound.Beep(880, 200)
    except Exception:
        sys.stdout.write("\a")
        sys.stdout.flush()


async def discord_notify(webhook: str, content: str):
    """Discord webhook 비동기 POST. 에러는 조용히 무시."""
    if not webhook:
        return

    def post():
        body = json.dumps({"content": content}).encode("utf-8")
        req = urllib.request.Request(
            webhook,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=3).read()
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            socket.timeout,
        ):
            pass

    await asyncio.get_event_loop().run_in_executor(None, post)
