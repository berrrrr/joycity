"""
JoyTalk 에뮬레이터 핸들러 (Phase 4 NDJSON 와이어 포맷)

각 핸들러: async def handle_<type>(session, pkt: dict) → None
session.send_json(dict) 로 응답 전송 (자동으로 \\n 종결).

필드명/값 모두 string 인 경우가 많음 (캡처 기준):
  myId, no, TX/TY/OX/OY, value, max 등 — 전부 "0" 같은 문자열.
"""

import asyncio
from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from emulator import Session  # noqa


# ── 데이터 모델 ────────────────────────────────────────────────────────────────

@dataclass
class GameObject:
    """Player GameObject (type='c'). 캡처에서 본 필드 그대로 — 일부라도 빠지면
    클라이언트가 맵 렌더링을 안 함 (검은 화면)."""
    no: int
    name: str = ""
    handle: int = 0
    level: int = 1
    type: str = "c"
    mapId: str = "01006"   # 캡처 첫 맵 = "모래속의사막"
    idx: int = 1000
    idxs: int = 2
    beforeRideIdx: int = -1
    OX: int = 89
    OY: int = 92
    VX: int = 89
    VY: int = 92
    TX: int = 89
    TY: int = 92
    speed: int = 8
    EOY: int = 100
    Chat: str = ""
    chatColor: list = field(default_factory=lambda: [255, 255, 255])
    defaultAni: int = 2
    preorder: list = field(default_factory=lambda: [0] * 20)
    itemColor: dict = field(default_factory=lambda: {
        str(i): {"r": 255, "g": 255, "b": 255} for i in range(20)
    })

    def to_json(self) -> dict:
        return asdict(self)


# ── 핸들러 레지스트리 ──────────────────────────────────────────────────────────

HANDLERS = {}

def handler(pkt_type: str):
    def deco(fn):
        HANDLERS[pkt_type] = fn
        return fn
    return deco


# ── 로그인 시퀀스 (Phase 4 캡처 그대로 재현) ───────────────────────────────────

@handler("login")
async def on_login(session, pkt: dict):
    """캡처된 로그인 응답 시퀀스 (S→C 첫 14개) 그대로 푸시.

    순서가 중요 — map 이 obj 보다 먼저 와야 클라가 맵 스프라이트를 로드.
    """
    userid = pkt.get("userid", "tester")
    version = pkt.get("version", "?")
    print(f"  [login] userid={userid!r} version={version!r}")

    session.userid = userid
    session.my_id = session.server.next_id()

    obj = GameObject(
        no=session.my_id,
        handle=session.my_id,
        name=userid or "tester",
    )
    session.server.objects[session.my_id] = obj

    # 1) ping
    await session.send_json({"type": "ping", "text": "Login"})

    # 2) login — myId
    await session.send_json({
        "type": "login",
        "myId": str(session.my_id),
        "isAdmin": "0",
    })

    # 3) exp
    await session.send_json({
        "type": "exp", "value": "0", "max": "100", "exp_level": "1",
    })

    # 4) bn
    await session.send_json({"type": "bn", "bn": "0"})

    # 5) hp
    await session.send_json({"type": "hp", "value": "100", "max": "100"})

    # 6) refresh
    await session.send_json({"type": "refresh", "Inventory": {}})

    # 7) info
    await session.send_json({"type": "info", "home": "", "awards": "[]"})

    # 8) userSaleDown (5 슬롯)
    for i in range(5):
        await session.send_json({"type": "userSaleDown", "num1": str(i)})

    # 9) map — 클라가 어떤 맵을 로드해야 하는지. 이게 빠지면 검은 화면.
    await session.send_json({
        "type": "map",
        "no": str(session.my_id),
        "MapNum": obj.mapId,
        "MapName": "테스트맵",
        "bgstr": "011",
        "OX": str(obj.OX),
        "OY": str(obj.OY),
        "weatherType": "0",
    })

    # 10) obj — 현재 맵의 모든 게임 오브젝트 (플레이어 본인 포함)
    await session.send_json({
        "type": "obj",
        "gameObjects": {
            str(k): v.to_json() for k, v in session.server.objects.items()
        },
    })

    # 11) 다른 세션에 입장 알림
    await session.server.broadcast_except(session.my_id, {
        "type": "objc",
        "gameObjects": {str(session.my_id): obj.to_json()},
    })


# ── 이동 / 상태 ────────────────────────────────────────────────────────────────

@handler("move")
async def on_move(session, pkt: dict):
    """클라가 보낸 move 를 그대로 브로드캐스트 (자기 포함). no 는 myId 로 채워줌."""
    if not session.my_id:
        return
    obj = session.server.objects.get(session.my_id)
    if not obj:
        return
    # 캡처상 클라이언트 move: TX/TY/OX/OY 모두 string
    obj.TX = int(pkt.get("TX", obj.TX))
    obj.TY = int(pkt.get("TY", obj.TY))
    obj.OX = int(pkt.get("OX", obj.OX))
    obj.OY = int(pkt.get("OY", obj.OY))

    await session.server.broadcast({
        "type": "move",
        "no": str(session.my_id),
        "TX": str(obj.TX),
        "TY": str(obj.TY),
        "OX": str(obj.OX),
        "OY": str(obj.OY),
        "timestamp": pkt.get("timestamp", "0"),
    })


@handler("myState")
async def on_my_state(session, pkt: dict):
    """myState — 캡처에서 5번 등장. 정확한 응답 형식 미상이라 무시."""
    pass


@handler("map")
async def on_map(session, pkt: dict):
    """클라 → 맵 변경 요청. 같은 맵 유지하며 ack."""
    if not session.my_id:
        return
    obj = session.server.objects.get(session.my_id)
    if not obj:
        return
    await session.send_json({
        "type": "map",
        "no": str(session.my_id),
        "MapNum": obj.mapId,
        "MapName": "테스트맵",
        "bgstr": "011",
        "OX": str(obj.OX),
        "OY": str(obj.OY),
        "weatherType": "0",
    })


# ── 채팅 ───────────────────────────────────────────────────────────────────────

@handler("chat")
async def on_chat(session, pkt: dict):
    text = pkt.get("text", "")
    print(f"  [chat] {session.userid}: {text!r}")
    if not session.my_id:
        return
    # 캡처: S→C 의 chat 은 {"type":"chat","no":"7920","text":"..."}
    await session.server.broadcast({
        "type": "chat",
        "no": str(session.my_id),
        "text": text,
    })


# ── 종료 ───────────────────────────────────────────────────────────────────────

@handler("exit")
async def on_exit(session, pkt: dict):
    await _remove_player(session)


# ── 캡처 미등장 패킷 — 안전한 무응답 (또는 최소 응답) ────────────────────────

@handler("ping")
async def on_ping(session, pkt: dict):
    pass

@handler("typing")
async def on_typing(session, pkt: dict):
    if session.my_id:
        await session.server.broadcast({"type": "typing", "no": str(session.my_id)})

@handler("stopTyping")
async def on_stop_typing(session, pkt: dict):
    if session.my_id:
        await session.server.broadcast({"type": "stopTyping", "no": str(session.my_id)})


async def _remove_player(session):
    if session.my_id and session.my_id in session.server.objects:
        del session.server.objects[session.my_id]
        await session.server.broadcast({"type": "remove", "no": str(session.my_id)})


async def dispatch(session, pkt_type: str, pkt: dict):
    h = HANDLERS.get(pkt_type)
    if h:
        await h(session, pkt)
    else:
        print(f"  [unhandled] type={pkt_type!r}  fields={list(pkt.keys())}")
