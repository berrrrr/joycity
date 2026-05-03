#!/usr/bin/env python3
"""
JoyTalk 아이템 트래커 (Phase 4 NDJSON 기반)

진짜 게임 서버 (jc.joy-june.com:7942) 와 클라 사이에 끼어서
맵에 떨어진 아이템을 실시간 모니터링.

기능:
  - obj/objc 패킷에서 아이템(type="hi") 스폰 감지
  - --filter 로 원하는 아이템명 매칭 (부분일치, 콤마 구분)
  - 매칭 시 콘솔 하이라이트 + 시스템 비프 + (옵션) Discord webhook
  - --pickup 으로 자동 줍기 시도 (실험적 — 패킷 포맷 미확정)
  - 위치/거리 표시 — 내 좌표 기준

전제 조건 (Windows):
  관리자 PowerShell:
    Add-Content C:\\Windows\\System32\\drivers\\etc\\hosts "127.0.0.1 jc.joy-june.com"
  일반 셸:
    py -3.11 tools\\item_tracker.py --filter "사과,당근" --upstream 119.200.71.233
    & "C:\\Users\\berrr\\AppData\\Local\\Joytalk\\Joytalk.exe"

종료 후 hosts 원복:
    (Get-Content C:\\Windows\\System32\\drivers\\etc\\hosts) `
      | Where-Object { $_ -notmatch 'jc.joy-june.com' } `
      | Set-Content C:\\Windows\\System32\\drivers\\etc\\hosts
"""

import argparse
import asyncio
import datetime
import io
import json
import pathlib
import random
import socket
import sys
import time
import urllib.request
import urllib.error
from collections import deque
from pathlib import Path
from typing import Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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
    # SSE queues 에 push (비동기)
    payload = json.dumps({"kind": "log", **entry}, ensure_ascii=False)
    for q in SSE_QUEUES:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


# ── 알림 ─────────────────────────────────────────────────────────────────────


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


# ── Collision grid + A* ────────────────────────────────────────────────────

# 게임 설치 경로 (Windows). 다른 OS면 ENV 또는 CLI 인자로 override.
GAME_INSTALL_DIR = pathlib.Path(r"C:/Users/berrr/AppData/Local/Joytalk")

# RMM static collision 활성화 — main() 에서 args 따라 변경
_RMM_ENABLED = True


def _find_rmm_file(map_id: str) -> Optional[pathlib.Path]:
    """MapNum (예 '01006') → 로컬 .rmm 파일 경로. M, MS 폴더에서 검색."""
    fname = f"Map{map_id}.rmm"
    for sub in ("M", "MS"):
        p = GAME_INSTALL_DIR / "Street" / sub / fname
        if p.exists():
            return p
    return None


def _load_rmm_blocked(rmm_path: pathlib.Path) -> tuple[set[tuple[int, int]], int, int]:
    """RMM 파싱 후 unk1 != 0 인 셀들을 blocked 로 반환. (blocked, w, h)
    실측 결과 unk1 가 collision flag 패턴 (95% =0 sparse). 다른 게임이면 다른 필드일 수도.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "parsers"))
    import rmm_parser  # type: ignore

    m = rmm_parser.parse(str(rmm_path))
    blocked: set[tuple[int, int]] = set()
    for y, row in enumerate(m.grid):
        for x, c in enumerate(row):
            if c.unk1 != 0:
                blocked.add((x, y))
    return blocked, m.width, m.height


class CollisionMap:
    """맵 1개의 collision 정보. 세 source 결합:
    1. RMM 파일 (옵션, --no-rmm 으로 끔)
    2. 디스크 영구 저장 — 이전 세션에서 학습한 walkable/blocked 누적
    3. 런타임 학습 (서버 echo / walker stuck)
    """

    PERSIST_DIR = pathlib.Path(__file__).resolve().parent.parent / "captures" / "collision"

    def __init__(self, map_id: str):
        self.map_id = map_id
        self.walkable: set[tuple[int, int]] = set()
        self.blocked_runtime: set[tuple[int, int]] = set()
        self.blocked_static: set[tuple[int, int]] = set()
        self.width: int = 0
        self.height: int = 0
        self.rmm_loaded: bool = False
        self._dirty = False  # 변경 누적 — periodic save
        # 디스크 누적 학습본 먼저 로드
        self.try_load_persist()
        # RMM 정적 collision 시도
        self.try_load_rmm()

    def try_load_persist(self):
        path = self.PERSIST_DIR / f"map_{self.map_id}.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.walkable = {tuple(c) for c in data.get("walkable", [])}
            self.blocked_runtime = {tuple(c) for c in data.get("blocked_runtime", [])}
            log(f"[map] {self.map_id} 영구 학습 로드: walk={len(self.walkable)} block={len(self.blocked_runtime)}", "info")
        except Exception as e:
            log(f"[map] persist 로드 실패: {e}", "err")

    def save_persist(self):
        if not self._dirty:
            return
        self.PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        path = self.PERSIST_DIR / f"map_{self.map_id}.json"
        try:
            path.write_text(json.dumps({
                "map_id": self.map_id,
                "walkable": [list(c) for c in self.walkable],
                "blocked_runtime": [list(c) for c in self.blocked_runtime],
            }), encoding="utf-8")
            self._dirty = False
        except Exception as e:
            log(f"[map] persist 저장 실패: {e}", "err")

    def try_load_rmm(self):
        # 글로벌 토글
        if not _RMM_ENABLED:
            return
        rmm = _find_rmm_file(self.map_id)
        if rmm is None:
            return
        try:
            self.blocked_static, self.width, self.height = _load_rmm_blocked(rmm)
            self.rmm_loaded = True
            log(
                f"[map] {self.map_id} 정적 collision 로드: {len(self.blocked_static)} blocked / {self.width}x{self.height} ({rmm.name})",
                "info",
            )
        except Exception as e:
            log(f"[map] RMM 로드 실패 ({rmm}): {e}", "err")

    @property
    def blocked(self) -> set[tuple[int, int]]:
        # 호환성 — 외부에서 read-only 처럼 사용
        return self.blocked_runtime | self.blocked_static

    def mark_walkable(self, x: int, y: int):
        cell = (int(x), int(y))
        was_blocked_static = cell in self.blocked_static
        if cell not in self.walkable:
            self._dirty = True
        self.walkable.add(cell)
        self.blocked_runtime.discard(cell)
        if was_blocked_static:
            # RMM 가설 (unk1!=0 = blocked) 검증 카운터 — 너무 많이 어긋나면 RMM 끔
            self._rmm_mismatches = getattr(self, "_rmm_mismatches", 0) + 1
            if self._rmm_mismatches == 5:
                log(
                    f"[map] {self.map_id} RMM unk1 가설 5번 어긋남 — 정적 collision 비활성",
                    "warn",
                )
                self.blocked_static.clear()
                self.rmm_loaded = False

    def mark_blocked(self, x: int, y: int):
        cell = (int(x), int(y))
        if cell in self.walkable:
            return
        if cell not in self.blocked_runtime:
            self._dirty = True
        self.blocked_runtime.add(cell)

    def cost(self, x: int, y: int) -> float | None:
        cell = (int(x), int(y))
        # 학습 walkable 가 최우선 (RMM 잘못 알아도 override)
        if cell in self.walkable:
            return 1.0
        if cell in self.blocked_runtime:
            return None
        if cell in self.blocked_static:
            return None
        # 미탐색은 매우 비싼 비용 — A* 가 학습된 walkable 경로를 강하게 선호
        # (이전 1.5 는 거의 같은 비용이라 직선 우선됨)
        return 5.0

    def playable_bounds(self, margin: int = 10) -> Optional[tuple[int, int, int, int]]:
        """학습된 walkable 셀의 bounding box. 데이터 부족하면 None.
        margin: 가장자리 여유 (활동 영역 밖에 살짝 들어가도 봐주기)."""
        if len(self.walkable) < 30:
            return None
        xs = [c[0] for c in self.walkable]
        ys = [c[1] for c in self.walkable]
        return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)

    def in_playable(self, x: int, y: int) -> bool:
        """좌표가 추정 활동 영역 안인지. 학습 부족 시 항상 True (필터 안 함)."""
        b = self.playable_bounds()
        if b is None:
            return True
        return b[0] <= x <= b[2] and b[1] <= y <= b[3]

    def to_dict(self) -> dict:
        b = self.playable_bounds()
        return {
            "map_id": self.map_id,
            "walkable": [list(c) for c in self.walkable],
            "blocked": [list(c) for c in self.blocked],
            "blocked_static": len(self.blocked_static),
            "blocked_runtime": len(self.blocked_runtime),
            "width": self.width,
            "height": self.height,
            "playable_bounds": list(b) if b else None,
        }


def astar(
    start: tuple[int, int],
    goal: tuple[int, int],
    cmap: CollisionMap,
    step: int = 2,
    max_nodes: int = 5000,
) -> list[tuple[int, int]] | None:
    """8방향 A* 경로탐색. 좌표는 step 단위로 grid snap.

    리턴: start 다음 셀부터 goal 까지의 셀 리스트 (start 제외), 실패 시 None.
    """
    import heapq

    def snap(p):
        return (int(round(p[0] / step)) * step, int(round(p[1] / step)) * step)

    s = snap(start)
    g = snap(goal)
    if s == g:
        return []

    def h(a, b):
        # 8방향 옥타일 휴리스틱
        dx = abs(a[0] - b[0]) / step
        dy = abs(a[1] - b[1]) / step
        return (max(dx, dy) + (1.4142135 - 1) * min(dx, dy)) * step

    open_heap = [(h(s, g), 0, s, None)]
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {}
    g_score: dict[tuple[int, int], float] = {s: 0}
    visited: set[tuple[int, int]] = set()

    nodes_expanded = 0
    while open_heap and nodes_expanded < max_nodes:
        _, gs, cur, parent = heapq.heappop(open_heap)
        if cur in visited:
            continue
        visited.add(cur)
        came_from[cur] = parent
        nodes_expanded += 1
        if cur == g:
            # 경로 복원
            path: list[tuple[int, int]] = []
            node = cur
            while came_from.get(node) is not None:
                path.append(node)
                node = came_from[node]
            path.reverse()
            return path
        for dx in (-step, 0, step):
            for dy in (-step, 0, step):
                if dx == 0 and dy == 0:
                    continue
                nb = (cur[0] + dx, cur[1] + dy)
                if nb in visited:
                    continue
                c = cmap.cost(nb[0], nb[1])
                if c is None:
                    continue
                # 대각선 비용
                move_cost = c * (1.4142135 if dx and dy else 1.0)
                tentative = gs + move_cost
                if tentative < g_score.get(nb, float("inf")):
                    g_score[nb] = tentative
                    heapq.heappush(
                        open_heap, (tentative + h(nb, g), tentative, nb, cur)
                    )
    return None


# ── 트래커 상태 ──────────────────────────────────────────────────────────────


class Tracker:
    """프록시 세션 1개의 상태.

    GameObject type 코드 (실측):
      c  = 캐릭터
      hi = 채집형 아이템 (씨앗/버섯/열매/땅의요정석)
      i  = 장식형 아이템 (꽃 — 빨강/노랑/파랑꽃 등)
      o  = 다른 캐릭이 들고있는 오브젝트 (스킵)
      e/s/j = 이벤트 NPC, 직업 표지 등
    """

    PICKABLE_TYPES = {"hi", "i"}

    def __init__(self, args):
        self.args = args
        self.filters = [f.strip() for f in (args.filter or "").split(",") if f.strip()]
        self.types = set((args.types or "hi,i").split(","))
        self.my_id: Optional[int] = None
        self.my_x: int = 0
        self.my_y: int = 0
        self.move_ts: int = 0  # itemGet timestamp 동기화용
        # obj_id -> (name, x, y)
        self.items: dict[int, tuple[str, int, int]] = {}
        self.client_writer: Optional[asyncio.StreamWriter] = None
        self.last_pickup_id: Optional[int] = None
        self.last_pickup_time: float = 0.0  # 쓰로틀
        # walker 상태: (oid, name, target_x, target_y) — None 이면 walking 중지
        self.walk_target: Optional[tuple[int, str, int, int]] = None
        self.walk_started_at: float = 0.0
        # 주입한 packet 로그 file (relay_lines 가 안 잡으니 별도)
        self.inject_log = None
        # 서버 echo 로 받은 본인 실제 위치 (collision 후 진짜 좌표)
        self.server_x: int = 0
        self.server_y: int = 0
        self.last_server_progress: float = 0.0
        self.last_server_pos: tuple[int, int] = (0, 0)
        # 못 가는 아이템 oid (잠시 무시)
        self.blacklist: dict[int, float] = {}
        # collision 학습 — 맵별
        self.cmaps: dict[str, CollisionMap] = {}
        self.current_map: str = ""
        # 현재 경로 (A* 결과). 다음 step 으로 갈 셀들의 큐
        self.path: list[tuple[int, int]] = []
        # 마지막 step 의 목적 셀 (서버 echo 가 따라오는지 확인)
        self.last_step_dst: Optional[tuple[int, int]] = None
        self.last_step_at: float = 0.0

    def matches(self, item_name: str) -> bool:
        """필터 미지정 시 모든 아이템, 아니면 부분일치."""
        if not self.filters:
            return False  # 필터 없으면 알림 안 함 (스팸 방지)
        return any(f in item_name for f in self.filters)

    def _cmap(self) -> Optional[CollisionMap]:
        if not self.current_map:
            return None
        cmap = self.cmaps.get(self.current_map)
        if cmap is None:
            cmap = CollisionMap(self.current_map)
            self.cmaps[self.current_map] = cmap
        return cmap

    @property
    def cur_x(self) -> int:
        """현재 본인 위치 X — server 가 인정한 값 우선, 없으면 클라가 보낸 값."""
        return self.server_x if self.server_x else self.my_x

    @property
    def cur_y(self) -> int:
        return self.server_y if self.server_y else self.my_y

    def fmt_pos(self, x: int, y: int) -> str:
        if not self.my_id:
            return f"({x},{y})"
        dx, dy = x - self.cur_x, y - self.cur_y
        dist = (dx * dx + dy * dy) ** 0.5
        return f"({x},{y}) dist={dist:.0f}"

    async def on_packet_s2c(self, pkt: dict):
        """서버 → 클라 패킷 처리."""
        t = pkt.get("type")

        if t == "login":
            mid = pkt.get("myId")
            if mid is not None:
                try:
                    self.my_id = int(mid)
                    log(f"내 myId = {self.my_id}", "dim")
                except ValueError:
                    pass

        elif t in ("obj", "objc"):
            for k, v in (pkt.get("gameObjects") or {}).items():
                if v.get("type") not in self.types:
                    continue
                try:
                    oid = int(v.get("no", k))
                    name = v.get("name", "?")
                    x = int(v.get("OX", 0))
                    y = int(v.get("OY", 0))
                    prev = self.items.get(oid)
                    self.items[oid] = (name, x, y)
                    is_new = prev is None
                    if t == "objc" or is_new:
                        await self.notify_spawn(oid, name, x, y, batch=(t == "obj"))
                except (ValueError, TypeError):
                    pass

        elif t == "move":
            # 본인 캐릭터 이동 echo — 서버가 실제로 받아준 위치
            if self.my_id and str(pkt.get("no")) == str(self.my_id):
                try:
                    new_sx = int(pkt.get("VX", self.server_x))
                    new_sy = int(pkt.get("VY", self.server_y))
                    if (new_sx, new_sy) != self.last_server_pos:
                        self.last_server_progress = time.time()
                        self.last_server_pos = (new_sx, new_sy)
                        # walkable 학습
                        cmap = self._cmap()
                        if cmap:
                            cmap.mark_walkable(new_sx, new_sy)
                    self.server_x, self.server_y = new_sx, new_sy
                except (ValueError, TypeError):
                    pass

        elif t == "remove":
            try:
                oid = int(pkt.get("no", 0))
                if oid in self.items:
                    name, x, y = self.items.pop(oid)
                    if self.matches(name):
                        log(f"- removed {name} #{oid} {self.fmt_pos(x,y)}", "dim")
            except (ValueError, TypeError):
                pass

        elif t == "map":
            mn = pkt.get("MapNum", "?")
            self.current_map = str(mn)
            cmap = self._cmap()
            log(
                f"맵 진입: {mn} {pkt.get('MapName','')} (학습: walk={len(cmap.walkable)} block={len(cmap.blocked)})",
                "info",
            )
            self.items.clear()
            self.walk_target = None
            self.path.clear()
            self.blacklist.clear()

    async def on_packet_c2s(self, pkt: dict):
        """클라 → 서버 패킷에서 내 위치 + timestamp 추적."""
        t = pkt.get("type")
        try:
            ts_val = int(pkt.get("timestamp", 0))
            if ts_val > self.move_ts:
                self.move_ts = ts_val
        except (ValueError, TypeError):
            pass
        if t == "move":
            try:
                self.my_x = int(pkt.get("OX", self.my_x))
                self.my_y = int(pkt.get("OY", self.my_y))
            except (ValueError, TypeError):
                pass
        elif t == "myState":
            try:
                self.my_x = int(pkt.get("LocationX", self.my_x))
                self.my_y = int(pkt.get("LocationY", self.my_y))
            except (ValueError, TypeError):
                pass

    async def notify_spawn(
        self, oid: int, name: str, x: int, y: int, batch: bool = False
    ):
        if not self.matches(name):
            return
        tag = "초기맵" if batch else "스폰"
        msg = f"★ {tag}: {name} #{oid} {self.fmt_pos(x, y)}"
        log(msg, "warn")

        if not batch:
            beep()
        if self.args.webhook:
            await discord_notify(self.args.webhook, msg)

        # 자동 이동: 현재 타겟 없고 playable area 안인 꽃만
        if (
            self.args.auto_walk
            and oid != self.last_pickup_id
            and self.my_id
            and oid not in self.blacklist
            and self.walk_target is None
        ):
            cmap = self._cmap()
            if cmap and not cmap.in_playable(x, y):
                log(f"  [skip-target] {name} #{oid} {self.fmt_pos(x, y)} 활동 영역 밖", "dim")
            else:
                # max-target-dist 도 체크 (학습 부족 단계에서 너무 먼 거 제외)
                d = ((x - self.cur_x) ** 2 + (y - self.cur_y) ** 2) ** 0.5
                if d > self.args.max_target_dist:
                    log(f"  [skip-target] {name} #{oid} dist={d:.0f} > 한도 {self.args.max_target_dist}", "dim")
                else:
                    self.walk_target = (oid, name, x, y)
                    self.walk_started_at = time.time()
                    self.last_server_progress = time.time()
                    self.path.clear()
                    log(f"→ walk target: {name} #{oid} {self.fmt_pos(x, y)}", "info")

        if self.args.pickup and oid != self.last_pickup_id:
            await self.maybe_pickup(oid, name, x, y, batch)

    async def maybe_pickup(self, oid: int, name: str, x: int, y: int, batch: bool):
        """안전장치 통과 시 자동 줍기. stealth 모드에선 랜덤 skip + 반응 지연.
        batch=True 도 허용 (proximity_loop 가 batch 로 호출하는 케이스)."""
        if not self.my_id:
            return
        if oid == self.last_pickup_id:
            return
        dx, dy = x - self.cur_x, y - self.cur_y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > self.args.max_dist:
            return  # 조용히 (proximity loop 가 자주 부를 거라 노이즈 줄임)
        now = time.time()
        if now - self.last_pickup_time < self.args.cooldown:
            return
        # 스텔스: 랜덤 skip + 반응 지연
        if self.args.stealth and not batch:
            if random.random() < self.args.skip_rate:
                log(f"[stealth-skip] {name} #{oid}", "dim")
                self.last_pickup_id = oid
                return
            delay = random.uniform(self.args.reaction_min, self.args.reaction_max)
            log(f"[stealth] {delay:.2f}s 반응 지연…", "dim")
            await asyncio.sleep(delay)
            if oid not in self.items:
                return
        self.last_pickup_time = time.time()
        await self.try_pickup(oid, name)
        # 픽업 발사 후 같은 맵에 매칭 아이템 더 있으면 즉시 다음 타겟
        if self.args.auto_walk:
            self._select_next_target()

    def _select_next_target(self):
        """블랙리스트/활동 영역 밖/너무 먼 거 제외, 가장 가까운 매칭 아이템 선정."""
        if not self.args.auto_walk or not self.my_id:
            return
        now = time.time()
        self.blacklist = {k: v for k, v in self.blacklist.items() if v > now}
        cmap = self._cmap()
        best, best_dist = None, float("inf")
        for oid, (name, x, y) in self.items.items():
            if not self.matches(name):
                continue
            if oid in self.blacklist:
                continue
            if oid == self.last_pickup_id:
                continue
            if cmap and not cmap.in_playable(x, y):
                continue
            d = ((x - self.cur_x) ** 2 + (y - self.cur_y) ** 2) ** 0.5
            if d > self.args.max_target_dist:
                continue
            if d < best_dist:
                best, best_dist = (oid, name, x, y), d
        if best:
            oid, name, x, y = best
            self.walk_target = (oid, name, x, y)
            self.walk_started_at = now
            self.last_server_progress = now
            log(
                f"→ walk target (re-select): {name} #{oid} dist={best_dist:.0f}", "info"
            )

    async def persist_loop(self):
        """30초마다 학습한 collision 누적본 디스크 저장."""
        while True:
            await asyncio.sleep(30)
            for cmap in self.cmaps.values():
                cmap.save_persist()

    async def proximity_loop(self):
        """주기적으로 알려진 아이템 거리 재평가 → 근접하면 픽업 시도.

        spawn 시점 한 번 체크로는 부족 — 사용자가 나중에 걸어가는 케이스 커버."""
        while True:
            await asyncio.sleep(self.args.proximity_interval)
            if not self.args.pickup or not self.my_id:
                continue
            # 가장 가까운 매칭 아이템 1개만 시도
            best = None
            best_dist = float("inf")
            for oid, (name, x, y) in self.items.items():
                if not self.matches(name):
                    continue
                if oid == self.last_pickup_id:
                    continue
                dx, dy = x - self.cur_x, y - self.cur_y
                d = (dx * dx + dy * dy) ** 0.5
                if d <= self.args.max_dist and d < best_dist:
                    best, best_dist = (oid, name, x, y), d
            if best:
                oid, name, x, y = best
                log(f"★ 근접 ({best_dist:.0f}): {name} #{oid}", "success")
                await self.maybe_pickup(oid, name, x, y, batch=False)

    async def try_pickup(self, oid: int, name: str):
        """itemGet 패킷 발사. 캡처 검증된 포맷:
        {"type":"itemGet","no":"<id>","timestamp":"<n>"}"""
        if not self.client_writer:
            return
        self.last_pickup_id = oid
        self.move_ts += 1
        pkt = {"type": "itemGet", "no": str(oid), "timestamp": str(self.move_ts)}
        await self._inject(pkt)
        log(f">> itemGet({oid}, {name}) ts={self.move_ts}", "success")

    async def _inject(self, pkt: dict):
        line = json.dumps(pkt, ensure_ascii=False).encode("utf-8") + b"\n"
        try:
            self.client_writer.write(line)
            await self.client_writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        # 주입 로그 (진단용 — 실제 c2s 로그와 합쳐서 보면 walker 동작 검증)
        if self.inject_log:
            try:
                self.inject_log.write(line)
                self.inject_log.flush()
            except Exception:
                pass

    def _replan(self, tx: int, ty: int) -> bool:
        """현재 위치에서 (tx,ty) 까지 A* 경로 재탐색. self.path 채움."""
        cmap = self._cmap()
        if cmap is None:
            return False
        start = (self.cur_x, self.cur_y)
        path = astar(start, (tx, ty), cmap, step=self.args.step_size)
        if path is None:
            return False
        # 너무 길면 앞쪽만 사용 (중간에 또 replan)
        self.path = path[:30]
        return True

    async def walker_loop(self):
        """자동 이동 루프 — Hybrid:
        - 학습된 walkable 셀이 충분 (>50개) 하면 A* 사용 (학습 경로 따라 우회)
        - 부족하면 직선 + sidestep dance (collision 데이터 학습 단계)
        - 학습된 walkable/blocked 는 디스크에 누적 → 같은 맵 재방문 시 재사용
        """
        # 현재 타겟에 대한 walker 상태
        stuck_attempts = 0      # 누적 stuck 횟수 (sidestep 시도 카운터)
        sidestep_remaining = 0  # 남은 sidestep step
        sidestep_dir = (0, 0)   # 현재 sidestep 이동 방향
        last_pos = (0, 0)       # 1.5s 전 server pos
        last_pos_at = 0.0
        last_oid = None
        # sidestep 시도 패턴 (각 stuck 마다 다른 방향으로)
        SIDESTEP_PATTERNS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]

        while True:
            base = self.args.walk_interval
            if self.args.stealth:
                base *= random.uniform(0.7, 1.4)
            await asyncio.sleep(base)

            if not self.args.auto_walk or not self.walk_target or not self.client_writer:
                stuck_attempts = 0; sidestep_remaining = 0; last_oid = None
                continue
            oid, name, tx, ty = self.walk_target

            # 타겟 변경 → 카운터 reset
            if oid != last_oid:
                stuck_attempts = 0
                sidestep_remaining = 0
                last_pos = (self.server_x, self.server_y)
                last_pos_at = time.time()
                last_oid = oid

            if time.time() - self.walk_started_at > self.args.walk_timeout:
                log(f"[walker] 타임아웃 — {name} 잠시 보류", "dim")
                self.blacklist[oid] = time.time() + self.args.blacklist_secs
                self.walk_target = None
                self._select_next_target()
                continue
            if oid not in self.items:
                self.walk_target = None
                continue

            # 도달 체크
            dx = tx - self.server_x
            dy = ty - self.server_y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= self.args.max_dist:
                log(f"[walker] 도달 (dist={dist:.0f}) — pickup", "info")
                self.walk_target = None
                if self.args.pickup:
                    await self.maybe_pickup(oid, name, tx, ty, batch=False)
                continue

            # stuck 검사 — N초 동안 server pos 가 거의 안 움직였나
            # 너무 민감하면 echo 지연으로 false positive → "왔다갔다" 됨
            now = time.time()
            if sidestep_remaining == 0 and now - last_pos_at > self.args.stuck_check_secs:
                moved = ((self.server_x - last_pos[0]) ** 2 +
                         (self.server_y - last_pos[1]) ** 2) ** 0.5
                last_pos = (self.server_x, self.server_y)
                last_pos_at = now
                # 매우 보수적: 1 step (2 unit) 미만 진행만 stuck 으로 간주
                if moved < self.args.step_size:
                    stuck_attempts += 1
                    if stuck_attempts > self.args.max_stuck:
                        log(f"[walker] {name} {stuck_attempts}회 stuck — 잠시 보류 ({self.args.blacklist_secs}s)", "warn")
                        self.blacklist[oid] = time.time() + self.args.blacklist_secs
                        self.walk_target = None
                        self._select_next_target()
                        continue
                    pat = SIDESTEP_PATTERNS[(stuck_attempts - 1) % len(SIDESTEP_PATTERNS)]
                    sidestep_dir = pat
                    sidestep_remaining = self.args.sidestep_steps
                    cmap = self._cmap()
                    if cmap:
                        bx = self.server_x + (self.args.step_size if dx > 0 else -self.args.step_size if dx < 0 else 0)
                        by = self.server_y + (self.args.step_size if dy > 0 else -self.args.step_size if dy < 0 else 0)
                        cmap.mark_blocked(bx, by)
                    log(f"[walker] stuck #{stuck_attempts} — sidestep {pat} x{sidestep_remaining}", "dim")

            if self.args.stealth and random.random() < 0.05:
                continue

            # step 방향 결정
            step = self.args.step_size
            cmap = self._cmap()
            if sidestep_remaining > 0:
                step_x = sidestep_dir[0] * step
                step_y = sidestep_dir[1] * step
                sidestep_remaining -= 1
            elif cmap and len(cmap.walkable) >= 50:
                # A* 사용 — 학습된 walkable 셀이 충분
                if not self.path:
                    self._replan(tx, ty)
                if self.path:
                    nx, ny = self.path.pop(0)
                    step_x = step if nx > self.server_x else -step if nx < self.server_x else 0
                    step_y = step if ny > self.server_y else -step if ny < self.server_y else 0
                else:
                    # A* 실패 → 직선
                    step_x = step if dx > 0 else -step if dx < 0 else 0
                    step_y = step if dy > 0 else -step if dy < 0 else 0
            else:
                # 직선 (학습 부족 단계)
                step_x = step if dx > 0 else -step if dx < 0 else 0
                step_y = step if dy > 0 else -step if dy < 0 else 0
                if abs(step_x) > abs(dx): step_x = dx
                if abs(step_y) > abs(dy): step_y = dy

            sx_new = self.server_x + step_x
            sy_new = self.server_y + step_y
            self.move_ts += 1
            move_pkt = {
                "type": "move",
                "TY": str(ty), "TX": str(tx),
                "OX": str(sx_new), "OY": str(sy_new),
                "timestamp": str(self.move_ts),
            }
            await self._inject(move_pkt)


# ── 프록시 ──────────────────────────────────────────────────────────────────


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
            # 라인 단위로 파싱
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
    # 주입 로그 (walker 가 보낸 move/itemGet)
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


# ── 메인 ────────────────────────────────────────────────────────────────────


async def run(args):
    tracker = Tracker(args)
    log_dir = Path(args.log_dir)

    print(f"{C_BOLD}=== JoyTalk 아이템 트래커 ==={C_RESET}")
    print(f"  upstream : {args.upstream}")
    print(
        f"  필터     : {tracker.filters or '(없음 — 알림 안 뜸. 웹 UI 또는 --filter)'}"
    )
    print(
        f"  자동줍기 : {'ON (max_dist=' + str(args.max_dist) + ')' if args.pickup else 'OFF'}"
    )
    print(
        f"  자동이동 : {'ON (interval=' + str(args.walk_interval) + 's)' if args.auto_walk else 'OFF'}"
    )
    print(f"  스텔스   : {'ON' if args.stealth else 'OFF'}")
    print(f"  로그     : {log_dir}/tracker_*.jsonl")
    if args.web:
        print(f"  {C_GREEN}웹 UI    : http://127.0.0.1:{args.web_port}/{C_RESET}")
    print()

    servers = []
    for port in (7942, 7945):
        srv = await asyncio.start_server(
            lambda r, w, p=port: handle_client(
                r, w, tracker, args.upstream, p, log_dir
            ),
            "127.0.0.1",
            port,
        )
        servers.append(srv)
        print(f"  리스닝 127.0.0.1:{port} → {args.upstream}:{port}")

    if not args.no_passthrough:
        for port in (80, 443):
            srv = await asyncio.start_server(
                lambda r, w, p=port: passthrough(r, w, args.upstream, p),
                "127.0.0.1",
                port,
            )
            servers.append(srv)
            print(f"  passthrough 127.0.0.1:{port} → {args.upstream}:{port}")

    web_module = None
    if args.web:
        import tracker_web as web_module

        srv = await web_module.start(
            "127.0.0.1", args.web_port, tracker, LOG_BUF, SSE_QUEUES, log_fn=log
        )
        servers.append(srv)
        print(f"  웹 UI 127.0.0.1:{args.web_port}")

    print(f"\n{C_GREEN}준비 완료. 게임 실행 후 맵 진입하면 알림 시작{C_RESET}\n")
    log("tracker started", "info")

    async with asyncio.TaskGroup() as tg:
        tg.create_task(tracker.walker_loop())
        tg.create_task(tracker.proximity_loop())
        tg.create_task(tracker.persist_loop())
        if web_module is not None:
            tg.create_task(web_module.state_broadcast_loop())
        for s in servers:
            tg.create_task(s.serve_forever())


def main():
    p = argparse.ArgumentParser(description="JoyTalk 아이템 트래커 (실서버 MITM)")
    p.add_argument(
        "--filter",
        default="",
        help='아이템명 부분일치 (콤마 구분). 예: --filter "꽃,당근"',
    )
    p.add_argument(
        "--types",
        default="hi,i",
        help="추적할 GameObject type (콤마 구분, 기본 hi,i). hi=채집, i=꽃",
    )
    p.add_argument(
        "--upstream", default="119.200.71.233", help="진짜 jc.joy-june.com IP"
    )
    p.add_argument(
        "--pickup",
        action="store_true",
        help="매칭 아이템 자동 줍기 (게임 strings 에 [MacroDetector] 가 있음 — 주의)",
    )
    p.add_argument(
        "--max-dist",
        type=float,
        default=30.0,
        help="자동 줍기 허용 거리 (서브-타일 단위, 기본 30). "
        "캡처상 사용자 직접 픽업이 38 거리에서도 됨 — 너무 작으면 절대 안 잡힘",
    )
    p.add_argument(
        "--cooldown", type=float, default=1.0, help="자동 줍기 최소 간격 초 (기본 1.0)"
    )
    p.add_argument(
        "--auto-walk",
        action="store_true",
        help="매칭 아이템 쪽으로 한 타일씩 자동 이동 (가장 가까운 매칭으로 우선)",
    )
    p.add_argument(
        "--walk-interval",
        type=float,
        default=0.18,
        help="step move 간격 초 (기본 0.18 — 대략 사람 이동 속도)",
    )
    p.add_argument(
        "--walk-timeout",
        type=float,
        default=30.0,
        help="한 타겟 추적 최대 시간 (기본 30초). 초과 시 포기.",
    )
    p.add_argument(
        "--step-size",
        type=int,
        default=2,
        help="step move 한 번 당 좌표 변화량 (기본 2 — 게임 자연 속도)",
    )
    p.add_argument(
        "--stuck-timeout",
        type=float,
        default=2.5,
        help="(deprecated) 호환용. 새 walker 는 3초 윈도우로 server pos 변화 검사",
    )
    p.add_argument(
        "--max-stuck",
        type=int,
        default=6,
        help="한 타겟 당 stuck → sidestep 시도 최대 횟수 (기본 6). 초과 시 잠시 보류",
    )
    p.add_argument(
        "--sidestep-steps",
        type=int,
        default=3,
        help="stuck 후 측면으로 시도할 step 수 (기본 3, 너무 크면 옆으로 멀리 감)",
    )
    p.add_argument(
        "--stuck-check-secs",
        type=float,
        default=3.0,
        help="stuck 으로 판단하기 전 server pos 변화 검사 윈도우 초 (기본 3.0). 너무 짧으면 echo 지연으로 false positive",
    )
    p.add_argument(
        "--blacklist-secs",
        type=float,
        default=20.0,
        help="도달 못 한 꽃을 무시할 시간 (기본 20초). 너무 길면 다른 꽃도 줄줄이 잠김",
    )
    p.add_argument(
        "--max-target-dist",
        type=float,
        default=120.0,
        help="walker target 으로 잡을 최대 거리 (기본 120). 바다 너머 꽃 같은 너무 먼 거 자동 제외",
    )
    p.add_argument(
        "--stealth",
        action="store_true",
        help="사람처럼 보이도록 랜덤 지터/skip/지연 추가 (강력 추천)",
    )
    p.add_argument(
        "--skip-rate",
        type=float,
        default=0.15,
        help="stealth: 매칭 아이템을 랜덤으로 건너뛸 확률 (기본 0.15 = 15%%)",
    )
    p.add_argument(
        "--reaction-min",
        type=float,
        default=0.3,
        help="stealth: spawn 후 픽업까지 최소 반응 지연 초 (기본 0.3)",
    )
    p.add_argument(
        "--reaction-max",
        type=float,
        default=1.2,
        help="stealth: spawn 후 픽업까지 최대 반응 지연 초 (기본 1.2)",
    )
    p.add_argument(
        "--proximity-interval",
        type=float,
        default=0.5,
        help="근접 스캔 주기 초 (기본 0.5). 사용자가 걸어가서 가까이 갔을 때 자동 픽업.",
    )
    p.add_argument("--webhook", default="", help="Discord webhook URL (옵션)")
    p.add_argument(
        "--no-passthrough", action="store_true", help="80/443 raw passthrough 끔"
    )
    p.add_argument(
        "--log-dir",
        default="captures",
        help="raw NDJSON 로그 저장 디렉터리 (기본 captures/)",
    )
    p.add_argument(
        "--web", action="store_true", help="웹 UI 활성화 (http://127.0.0.1:<web-port>)"
    )
    p.add_argument("--web-port", type=int, default=8765, help="웹 UI 포트 (기본 8765)")
    p.add_argument(
        "--no-rmm",
        action="store_true",
        help="RMM 정적 collision 비활성 (런타임 학습만 사용)",
    )
    p.add_argument(
        "--game-dir",
        default=None,
        help="게임 설치 폴더 (기본 C:/Users/berrr/AppData/Local/Joytalk)",
    )
    args = p.parse_args()

    global _RMM_ENABLED, GAME_INSTALL_DIR
    _RMM_ENABLED = not args.no_rmm
    if args.game_dir:
        GAME_INSTALL_DIR = pathlib.Path(args.game_dir)

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print(f"\n{C_GRAY}종료{C_RESET}")


if __name__ == "__main__":
    main()
