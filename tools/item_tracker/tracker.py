"""Tracker — 패킷 처리 + walker/proximity/wander/persist/map_cycle 루프."""
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Optional

from .collision import CollisionMap, astar
from .notify import beep, discord_notify, log


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
        # obj_id -> obj type code ('c', 'hi', 'i', 'o', 'em', ...)
        # 'o' = NPC 가 누군가에게 변신/탑승 됐음 → walker 타겟 제외
        self.item_types: dict[int, str] = {}
        # 이미 표정 짓기 시도한 NPC oid (재시도 방지). 맵 전환 시 reset.
        self.smiled_ids: set[int] = set()
        # 표정 직후 drop window — 이 timestamp 이전엔 어떤 type=i 든 자동 픽업
        self.smile_drop_until: float = 0.0
        self.client_writer: Optional[asyncio.StreamWriter] = None
        # 이미 itemGet 발사한 oid 들 — 서버가 remove 패킷 안 보낼 수도 있어서
        # 우리 쪽에서 명시적으로 추적해야 stale 아이템 다시 타겟하는 거 방지.
        # 맵 전환 시 clear (oid 가 다음 맵에서 재사용될 수 있음).
        self.picked_ids: set[int] = set()
        self.last_pickup_time: float = 0.0  # 쓰로틀
        # walker 상태: (oid, name, target_x, target_y) — None 이면 walking 중지
        self.walk_target: Optional[tuple[int, str, int, int]] = None
        self.walk_started_at: float = 0.0
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
        """필터 미지정 시 알림 안 함 (스팸 방지), 아니면 부분일치."""
        if not self.filters:
            return False
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

    # 표정 짓기 가능한 NPC 판별 — 캡처 검증됨
    # ○○돼지: 살색/황금/산타 (idx 3000~3002)
    # ○○팝: 쵸코팝/차차팝/골드팝 (강아지 변신 NPC, idx 2118~2121)
    # ○○차차: 둥둥차차/빨간멍든차차/차차둥둥 (차차 시리즈)
    # 제외: 오팝 (사용자 요청), 팝콘 (em 상점), 팝마트 (상점 NPC), 팝피아초청장 (item)
    _ANIMAL_FALSE_POSITIVES = {"오팝", "팝콘", "팝마트", "팝피아초청장"}

    def is_animal(self, name: str) -> bool:
        """표정 짓기 발사 대상인지 판별."""
        if any(kw in name for kw in ("돼지", "응가")):
            return True
        if name in self._ANIMAL_FALSE_POSITIVES:
            return False
        if name.endswith("팝") or "차차" in name:
            return True
        return False

    def should_target(self, oid: int, name: str) -> bool:
        """walker/pickup 대상인지 판별.

        - filter 매칭 → 무조건 OK (기존 동작)
        - 표정 직후 drop window 안 + type=i → 이름 무관하게 OK
          (드랍 아이템 이름이 다양하고 매번 변할 수 있어서 — 차차팝이 골드응가도
          뱉을 수 있다는 사용자 보고 기반)
        """
        if self.matches(name):
            return True
        if time.time() < self.smile_drop_until and self.item_types.get(oid) == "i":
            return True
        return False

    def is_taken(self, oid: int) -> bool:
        """돼지/응가가 이미 누군가에게 변신/탑승 됨 (type=o). 타겟 제외해야 함."""
        return self.item_types.get(oid) == "o"

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
                obj_type = v.get("type")
                try:
                    oid = int(v.get("no", k))
                except (ValueError, TypeError):
                    continue
                # 이미 추적중인 oid 의 type 변환은 항상 받음 (c→o 가 핵심 신호)
                if oid in self.item_types:
                    self.item_types[oid] = obj_type
                if obj_type not in self.types:
                    continue
                try:
                    name = v.get("name", "?")
                    x = int(v.get("OX", 0))
                    y = int(v.get("OY", 0))
                    prev = self.items.get(oid)
                    self.items[oid] = (name, x, y)
                    self.item_types[oid] = obj_type
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
                self.item_types.pop(oid, None)
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
            self.item_types.clear()
            self.smiled_ids.clear()
            self.walk_target = None
            self.path.clear()
            self.blacklist.clear()
            self.picked_ids.clear()  # oid 가 다음 맵에서 재사용될 수 있음

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
        if not self.should_target(oid, name):
            return
        tag = "초기맵" if batch else "스폰"
        msg = f"★ {tag}: {name} #{oid} {self.fmt_pos(x, y)}"
        log(msg, "warn")

        if not batch and self.args.beep:
            beep()
        if self.args.webhook:
            await discord_notify(self.args.webhook, msg)

        # 자동 이동: 현재 타겟 없고 playable area 안인 꽃만
        if (
            self.args.auto_walk
            and oid not in self.picked_ids
            and self.my_id
            and oid not in self.blacklist
            and self.walk_target is None
            and not self.is_taken(oid)
        ):
            cmap = self._cmap()
            if cmap and not self.args.no_bounds_filter and not cmap.in_playable(x, y):
                log(f"  [skip-target] {name} #{oid} {self.fmt_pos(x, y)} 활동 영역 밖", "dim")
            else:
                d = ((x - self.cur_x) ** 2 + (y - self.cur_y) ** 2) ** 0.5
                if d > self.args.max_target_dist:
                    log(f"  [skip-target] {name} #{oid} dist={d:.0f} > 한도 {self.args.max_target_dist}", "dim")
                else:
                    self.walk_target = (oid, name, x, y)
                    self.walk_started_at = time.time()
                    self.last_server_progress = time.time()
                    self.path.clear()
                    log(f"→ walk target: {name} #{oid} {self.fmt_pos(x, y)}", "info")

        if self.args.pickup and oid not in self.picked_ids:
            await self.maybe_pickup(oid, name, x, y, batch)

    async def maybe_pickup(self, oid: int, name: str, x: int, y: int, batch: bool):
        """안전장치 통과 시 자동 줍기. stealth 모드에선 랜덤 skip + 반응 지연.
        batch=True 도 허용 (proximity_loop 가 batch 로 호출하는 케이스)."""
        if not self.my_id:
            return
        if oid in self.picked_ids:
            return
        dx, dy = x - self.cur_x, y - self.cur_y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > self.args.max_dist:
            return
        now = time.time()
        if now - self.last_pickup_time < self.args.cooldown:
            return
        # 스텔스: 랜덤 skip + 반응 지연
        if self.args.stealth and not batch:
            if random.random() < self.args.skip_rate:
                log(f"[stealth-skip] {name} #{oid}", "dim")
                self.picked_ids.add(oid)
                return
            delay = random.uniform(self.args.reaction_min, self.args.reaction_max)
            log(f"[stealth] {delay:.2f}s 반응 지연…", "dim")
            await asyncio.sleep(delay)
            if oid not in self.items:
                return
        self.last_pickup_time = time.time()
        await self.try_pickup(oid, name)
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
            if not self.should_target(oid, name):
                continue
            if oid in self.blacklist:
                continue
            if oid in self.picked_ids:
                continue
            if self.is_taken(oid):
                continue
            if cmap and not self.args.no_bounds_filter and not cmap.in_playable(x, y):
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

    async def map_cycle_loop(self):
        """일정 시간마다 맵 순환. --map-cycle "01006,01007" 같이 지정.
        walker target 추적 중이어도 시간 되면 강제 전환 (현재 타겟 잠시 보류)."""
        if not self.args.map_cycle:
            return
        maps = [m.strip() for m in self.args.map_cycle.split(",") if m.strip()]
        if len(maps) < 2:
            log(f"[map-cycle] 2개 이상 맵 필요 (지금: {maps})", "warn")
            return
        idx = 0
        log(f"[map-cycle] 순환 활성: {maps}, 주기 {self.args.map_cycle_secs}초", "info")
        while True:
            await asyncio.sleep(self.args.map_cycle_secs)
            if not self.client_writer or not self.my_id:
                continue
            if self.walk_target is not None:
                tgt_oid = self.walk_target[0]
                self.blacklist[tgt_oid] = time.time() + self.args.blacklist_secs
                self.walk_target = None
                self.path.clear()
                log(f"[map-cycle] 현재 타겟 #{tgt_oid} 보류, 맵 전환", "info")
            target_map = maps[idx % len(maps)]
            if target_map == self.current_map:
                idx += 1
                target_map = maps[idx % len(maps)]
            self.move_ts += 1
            pkt = {"type": "map", "mapId": target_map, "timestamp": str(self.move_ts)}
            await self._inject(pkt)
            log(f"[map-cycle] → {target_map}", "info")
            idx += 1

    async def wander_loop(self):
        """walker idle 일 때 랜덤 patrol — 학습된 영역 안에서 어슬렁."""
        wander_dir = (1, 0)
        steps_in_dir = 0
        idle_since = 0.0
        while True:
            await asyncio.sleep(self.args.walk_interval)
            if not self.args.wander or not self.args.auto_walk:
                idle_since = 0.0
                continue
            if self.walk_target is not None or not self.client_writer or not self.my_id:
                idle_since = 0.0
                continue
            now = time.time()
            if idle_since == 0.0:
                idle_since = now
                continue
            if now - idle_since < self.args.wander_idle:
                continue

            if steps_in_dir <= 0:
                cmap = self._cmap()
                bounds = cmap.playable_bounds() if cmap else None
                if bounds:
                    minx, miny, maxx, maxy = bounds
                    if not (minx <= self.server_x <= maxx and miny <= self.server_y <= maxy):
                        cx = (minx + maxx) // 2
                        cy = (miny + maxy) // 2
                        dx = cx - self.server_x
                        dy = cy - self.server_y
                        wander_dir = (1 if dx > 0 else -1 if dx < 0 else 0,
                                      1 if dy > 0 else -1 if dy < 0 else 0)
                    else:
                        wander_dir = random.choice([(1,0),(-1,0),(0,1),(0,-1),
                                                    (1,1),(-1,-1),(1,-1),(-1,1)])
                else:
                    wander_dir = random.choice([(1,0),(-1,0),(0,1),(0,-1)])
                steps_in_dir = random.randint(self.args.wander_steps_min, self.args.wander_steps_max)

            step = self.args.step_size
            sx_new = self.server_x + wander_dir[0] * step
            sy_new = self.server_y + wander_dir[1] * step
            self.move_ts += 1
            move_pkt = {
                "type": "move",
                "TY": str(sy_new), "TX": str(sx_new),
                "OX": str(sx_new), "OY": str(sy_new),
                "timestamp": str(self.move_ts),
            }
            await self._inject(move_pkt)
            steps_in_dir -= 1

    async def proximity_loop(self):
        """주기적으로 거리 재평가:
          1. max-dist 이내 → 즉시 pickup
          2. 그 외, walker idle + max-target-dist 이내 → walker target 으로 promote
        """
        while True:
            await asyncio.sleep(self.args.proximity_interval)
            if not self.my_id:
                continue

            if self.args.pickup:
                best = None; best_dist = float("inf")
                for oid, (name, x, y) in self.items.items():
                    if not self.should_target(oid, name): continue
                    if oid in self.picked_ids: continue
                    if self.is_taken(oid): continue
                    dx, dy = x - self.cur_x, y - self.cur_y
                    d = (dx * dx + dy * dy) ** 0.5
                    if d <= self.args.max_dist and d < best_dist:
                        best, best_dist = (oid, name, x, y), d
                if best:
                    oid, name, x, y = best
                    log(f"★ 근접 ({best_dist:.0f}): {name} #{oid}", "success")
                    await self.maybe_pickup(oid, name, x, y, batch=False)
                    continue

            if self.args.auto_walk and self.walk_target is None:
                self._select_next_target()

    async def try_pickup(self, oid: int, name: str):
        """itemGet 패킷 발사. 캡처 검증된 포맷:
        {"type":"itemGet","no":"<id>","timestamp":"<n>"}"""
        if not self.client_writer:
            return
        self.picked_ids.add(oid)
        # self.items 에서도 즉시 제거 — 서버가 remove 패킷 안 보낼 수도 있음.
        # 만약 itemGet 실패해도 server 의 다음 obj broadcast 에서 다시 잡힘.
        self.items.pop(oid, None)
        self.move_ts += 1
        pkt = {"type": "itemGet", "no": str(oid), "timestamp": str(self.move_ts)}
        await self._inject(pkt)
        log(f">> itemGet({oid}, {name}) ts={self.move_ts}", "success")

    async def try_smile(self, target_oid: int, target_name: str):
        """돼지/응가 NPC 위에서 웃는 표정 패킷 발사 (motion=62).

        캡처 검증: motion 62 → 책임의 열쇠/돼지코 등 아이템 드랍 + exp 50.
        본인 my_id 로 발사하면 server 가 broadcast 해서 모두에게 전달됨.

        발사 후 smile_drop_until 윈도우 활성 — 그 동안은 매칭 안 되는 type=i 도
        다 줍기 (드랍 종류 다양해서 filter 로 일일이 못 맞춤).
        """
        if not self.client_writer or not self.my_id:
            return
        if self.args.stealth:
            await asyncio.sleep(random.uniform(0.4, 1.1))
        self.smiled_ids.add(target_oid)
        self.move_ts += 1
        pkt = {
            "type": "motion",
            "no": str(self.my_id),
            "motion": str(self.args.smile_motion),
            "sound": "",
        }
        await self._inject(pkt)
        # drop window 활성 — 12초간 모든 type=i 자동 픽업
        self.smile_drop_until = time.time() + self.args.smile_drop_window
        log(f">> 표정 motion={self.args.smile_motion} on {target_name} #{target_oid} "
            f"(drop window {self.args.smile_drop_window}s)", "success")

    async def _inject(self, pkt: dict):
        if self.client_writer is None:
            return
        line = json.dumps(pkt, ensure_ascii=False).encode("utf-8") + b"\n"
        try:
            self.client_writer.write(line)
            await self.client_writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError, RuntimeError):
            self.client_writer = None
            return
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
        self.path = path[:30]
        return True

    async def walker_loop(self):
        """자동 이동 루프 — Hybrid:
        - 학습된 walkable 셀이 충분 (>50개) 하면 A* 사용 (학습 경로 따라 우회)
        - 부족하면 직선 + sidestep dance (collision 데이터 학습 단계)
        - 학습된 walkable/blocked 는 디스크에 누적 → 같은 맵 재방문 시 재사용
        """
        stuck_attempts = 0
        sidestep_remaining = 0
        sidestep_dir = (0, 0)
        last_pos = (0, 0)
        last_pos_at = 0.0
        last_oid = None
        last_arrived_oid = None  # 따라잡음 로그 dedupe — 같은 타겟 멈춰있는 동안 한 번만
        SIDESTEP_PATTERNS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]

        while True:
            base = self.args.walk_interval
            if self.args.stealth:
                base *= random.uniform(0.7, 1.4)
            await asyncio.sleep(base)

            if not self.args.auto_walk or not self.walk_target or not self.client_writer:
                stuck_attempts = 0; sidestep_remaining = 0; last_oid = None
                last_arrived_oid = None
                continue
            oid, name, _tx_static, _ty_static = self.walk_target

            # 살아있는 좌표 우선 — NPC/동물 같이 움직이는 타겟 따라가기
            live = self.items.get(oid)
            if live is not None:
                _, tx, ty = live
            else:
                self.walk_target = None
                last_arrived_oid = None
                continue

            if oid != last_oid:
                stuck_attempts = 0
                sidestep_remaining = 0
                last_pos = (self.server_x, self.server_y)
                last_pos_at = time.time()
                last_oid = oid
                last_arrived_oid = None

            if time.time() - self.walk_started_at > self.args.walk_timeout:
                log(f"[walker] 타임아웃 — {name} 잠시 보류", "dim")
                self.blacklist[oid] = time.time() + self.args.blacklist_secs
                self.walk_target = None
                self._select_next_target()
                continue

            dx = tx - self.server_x
            dy = ty - self.server_y
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= self.args.max_dist:
                # 동물 NPC 위에 도착 → 자동 표정 짓기 (auto_smile 옵션)
                is_animal_target = self.is_animal(name)
                if (
                    self.args.auto_smile
                    and is_animal_target
                    and oid not in self.smiled_ids
                    and not self.is_taken(oid)
                ):
                    await self.try_smile(oid, name)
                    # 표정 후 잠시 대기 — 서버가 응답 + 아이템 드랍할 시간
                    # 아이템이 obj 패킷으로 등록되면 walker 가 자동 재타겟 → pickup
                    self.walk_target = None
                    last_arrived_oid = None
                    self.blacklist[oid] = time.time() + 8.0  # 8초간 같은 NPC 재시도 방지
                    continue
                if self.args.pickup and not is_animal_target:
                    log(f"[walker] 도달 (dist={dist:.0f}) — pickup", "info")
                    self.walk_target = None
                    await self.maybe_pickup(oid, name, tx, ty, batch=False)
                    last_arrived_oid = None
                else:
                    # follow-mode 또는 동물 (이미 smile 함): 타겟 유지하고 멈춤
                    if last_arrived_oid != oid:
                        log(f"[walker] 따라잡음 — {name} #{oid} (follow)", "info")
                        last_arrived_oid = oid
                continue
            else:
                last_arrived_oid = None

            now = time.time()
            if sidestep_remaining == 0 and now - last_pos_at > self.args.stuck_check_secs:
                moved = ((self.server_x - last_pos[0]) ** 2 +
                         (self.server_y - last_pos[1]) ** 2) ** 0.5
                last_pos = (self.server_x, self.server_y)
                last_pos_at = now
                if moved < 1.0:
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

            step = self.args.step_size
            cmap = self._cmap()
            if sidestep_remaining > 0:
                step_x = sidestep_dir[0] * step
                step_y = sidestep_dir[1] * step
                sidestep_remaining -= 1
            elif cmap and len(cmap.walkable) >= 50:
                if not self.path:
                    self._replan(tx, ty)
                if self.path:
                    nx, ny = self.path.pop(0)
                    step_x = step if nx > self.server_x else -step if nx < self.server_x else 0
                    step_y = step if ny > self.server_y else -step if ny < self.server_y else 0
                else:
                    step_x = step if dx > 0 else -step if dx < 0 else 0
                    step_y = step if dy > 0 else -step if dy < 0 else 0
            else:
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
