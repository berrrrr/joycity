"""Collision grid (RMM 정적 + 런타임 학습) + A* 경로탐색.

RMM_ENABLED, GAME_INSTALL_DIR 는 cli 에서 args 따라 변경.
PERSIST_DIR 는 captures/collision/ 에 맵별 학습본 누적.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Optional

from .notify import log

# 게임 설치 경로 (Windows). 다른 OS면 ENV 또는 CLI 인자로 override.
GAME_INSTALL_DIR = pathlib.Path(r"C:/Users/berrr/AppData/Local/Joytalk")

# RMM static collision 활성화 — cli 에서 args 따라 변경
RMM_ENABLED = True

# 프로젝트 루트 (joycity/) — tools/item_tracker/collision.py → ../../
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


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
    parsers_dir = str(_PROJECT_ROOT / "parsers")
    if parsers_dir not in sys.path:
        sys.path.insert(0, parsers_dir)
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

    PERSIST_DIR = _PROJECT_ROOT / "captures" / "collision"

    def __init__(self, map_id: str):
        self.map_id = map_id
        self.walkable: set[tuple[int, int]] = set()
        self.blocked_runtime: set[tuple[int, int]] = set()
        self.blocked_static: set[tuple[int, int]] = set()
        self.width: int = 0
        self.height: int = 0
        self.rmm_loaded: bool = False
        self._dirty = False
        self.try_load_persist()
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
        if not RMM_ENABLED:
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
        if cell in self.walkable:
            return 1.0
        if cell in self.blocked_runtime:
            return None
        if cell in self.blocked_static:
            return None
        # 미탐색은 매우 비싼 비용 — A* 가 학습된 walkable 경로를 강하게 선호
        return 5.0

    def playable_bounds(self, margin: int = 60) -> Optional[tuple[int, int, int, int]]:
        """학습된 walkable 셀의 bounding box. 데이터 부족하면 None."""
        if len(self.walkable) < 100:
            return None
        xs = [c[0] for c in self.walkable]
        ys = [c[1] for c in self.walkable]
        return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)

    def in_playable(self, x: int, y: int) -> bool:
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
                move_cost = c * (1.4142135 if dx and dy else 1.0)
                tentative = gs + move_cost
                if tentative < g_score.get(nb, float("inf")):
                    g_score[nb] = tentative
                    heapq.heappush(
                        open_heap, (tentative + h(nb, g), tentative, nb, cur)
                    )
    return None
