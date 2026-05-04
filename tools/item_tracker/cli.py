"""CLI 진입점 — argparse + TOML 프리셋 + run().

실행:
  python -m item_tracker --preset flower_farm
  python -m item_tracker --filter "꽃,당근" --pickup --auto-walk --web

프리셋: tools/item_tracker/presets/<name>.toml
프리셋이 기본값을 덮고, CLI 인자가 프리셋을 덮음.

전제 조건 (Windows):
  관리자 PowerShell:
    Add-Content C:\\Windows\\System32\\drivers\\etc\\hosts "127.0.0.1 jc.joy-june.com"
  종료 후 hosts 원복:
    (Get-Content C:\\Windows\\System32\\drivers\\etc\\hosts) `
      | Where-Object { $_ -notmatch 'jc.joy-june.com' } `
      | Set-Content C:\\Windows\\System32\\drivers\\etc\\hosts
"""
from __future__ import annotations

import argparse
import asyncio
import io
import pathlib
import sys
import tomllib
from pathlib import Path

from . import collision
from .notify import C_BOLD, C_GRAY, C_GREEN, C_RESET, LOG_BUF, SSE_QUEUES, log
from .proxy import handle_client, passthrough
from .tracker import Tracker

PRESETS_DIR = Path(__file__).resolve().parent / "presets"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="item_tracker",
        description="JoyTalk 아이템 트래커 (실서버 MITM)",
    )
    p.add_argument(
        "--preset",
        default=None,
        help=f"프리셋 이름 — {PRESETS_DIR} 안의 <name>.toml 로드. CLI 인자가 우선.",
    )
    p.add_argument("--filter", default="", help='아이템명 부분일치 (콤마 구분)')
    p.add_argument("--types", default="hi,i", help="추적할 type (기본 hi,i)")
    p.add_argument("--upstream", default="119.200.71.233", help="진짜 jc.joy-june.com IP")
    p.add_argument("--pickup", action="store_true", help="매칭 아이템 자동 줍기")
    p.add_argument("--max-dist", type=float, default=30.0, help="자동 줍기 허용 거리 (기본 30)")
    p.add_argument("--cooldown", type=float, default=1.0, help="자동 줍기 최소 간격 초 (기본 1.0)")
    p.add_argument("--auto-walk", action="store_true", help="매칭 아이템 쪽으로 자동 이동")
    p.add_argument("--walk-interval", type=float, default=0.18, help="step 간격 초 (기본 0.18)")
    p.add_argument("--walk-timeout", type=float, default=30.0, help="한 타겟 추적 최대 시간")
    p.add_argument("--step-size", type=int, default=2, help="step 한 번 당 좌표 변화량 (기본 2)")
    p.add_argument("--stuck-timeout", type=float, default=2.5, help="(deprecated) 호환용")
    p.add_argument("--max-stuck", type=int, default=6, help="stuck → sidestep 최대 횟수")
    p.add_argument("--sidestep-steps", type=int, default=3, help="stuck 후 측면 step 수")
    p.add_argument("--stuck-check-secs", type=float, default=5.0, help="stuck 판단 윈도우 초")
    p.add_argument("--blacklist-secs", type=float, default=20.0, help="도달 못한 꽃 무시 시간")
    p.add_argument("--max-target-dist", type=float, default=120.0, help="walker target 최대 거리")
    p.add_argument("--no-bounds-filter", action="store_true", help="playable bounds 필터 끄기")
    p.add_argument("--wander", action="store_true", help="walker idle 일 때 랜덤 patrol")
    p.add_argument("--wander-idle", type=float, default=2.0, help="patrol 시작까지 idle 초")
    p.add_argument("--wander-steps-min", type=int, default=4, help="patrol 한 방향 최소 step")
    p.add_argument("--wander-steps-max", type=int, default=12, help="patrol 한 방향 최대 step")
    p.add_argument("--map-cycle", default="", help='맵 순환 — 콤마구분 mapId')
    p.add_argument("--map-cycle-secs", type=float, default=180.0, help="맵 순환 주기 초")
    p.add_argument("--beep", action="store_true", help="새 spawn 시 시스템 비프음")
    p.add_argument("--stealth", action="store_true", help="사람처럼 보이도록 랜덤 지터/skip/지연")
    p.add_argument("--skip-rate", type=float, default=0.15, help="stealth: 랜덤 skip 확률")
    p.add_argument("--reaction-min", type=float, default=0.3, help="stealth: 최소 반응 지연")
    p.add_argument("--reaction-max", type=float, default=1.2, help="stealth: 최대 반응 지연")
    p.add_argument("--proximity-interval", type=float, default=0.5, help="근접 스캔 주기 초")
    p.add_argument("--webhook", default="", help="Discord webhook URL (옵션)")
    p.add_argument("--no-passthrough", action="store_true", help="80/443 raw passthrough 끔")
    p.add_argument("--log-dir", default="captures", help="raw NDJSON 로그 저장 디렉터리")
    p.add_argument("--web", action="store_true", help="웹 UI 활성화")
    p.add_argument("--web-port", type=int, default=8765, help="웹 UI 포트 (기본 8765)")
    p.add_argument("--no-rmm", action="store_true", help="RMM 정적 collision 비활성")
    p.add_argument("--game-dir", default=None, help="게임 설치 폴더 (override)")
    return p


def _apply_preset(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """프리셋 TOML 을 args 에 머지. 단, 이미 default 와 다른 값(=명시적 CLI)은 보존."""
    if not args.preset:
        return
    preset_path = PRESETS_DIR / f"{args.preset}.toml"
    if not preset_path.exists():
        available = sorted(p.stem for p in PRESETS_DIR.glob("*.toml"))
        sys.exit(f"[preset] '{args.preset}.toml' 없음. 사용 가능: {available}")
    with open(preset_path, "rb") as f:
        preset = tomllib.load(f)
    applied = []
    for k, v in preset.items():
        # argparse 는 - 를 _ 로 바꿈
        attr = k.replace("-", "_")
        if not hasattr(args, attr):
            log(f"[preset] 알 수 없는 키 무시: {k}", "warn")
            continue
        # CLI 에서 명시적으로 바꾸지 않은 경우만 프리셋 적용
        if getattr(args, attr) == parser.get_default(attr):
            setattr(args, attr, v)
            applied.append(f"{k}={v}")
    if applied:
        print(f"  {C_GRAY}[preset:{args.preset}] {', '.join(applied)}{C_RESET}")


async def run(args):
    tracker = Tracker(args)
    log_dir = Path(args.log_dir)

    print(f"{C_BOLD}=== JoyTalk 아이템 트래커 ==={C_RESET}")
    if args.preset:
        print(f"  프리셋   : {args.preset}")
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
        # tracker_web.py 는 tools/ 에 있음 — 패키지 부모 경로 추가
        tools_dir = str(Path(__file__).resolve().parent.parent)
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import tracker_web as web_module  # noqa: E402

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
        tg.create_task(tracker.wander_loop())
        tg.create_task(tracker.map_cycle_loop())
        if web_module is not None:
            tg.create_task(web_module.state_broadcast_loop())
        for s in servers:
            tg.create_task(s.serve_forever())


def main():
    # UTF-8 stdout (Windows cmd/PowerShell 한글 출력)
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = build_parser()
    args = parser.parse_args()
    _apply_preset(args, parser)

    collision.RMM_ENABLED = not args.no_rmm
    if args.game_dir:
        collision.GAME_INSTALL_DIR = pathlib.Path(args.game_dir)

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print(f"\n{C_GRAY}종료{C_RESET}")
