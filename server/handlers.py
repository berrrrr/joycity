"""
JoyTalk 에뮬레이터 서버 핸들러

각 핸들러: async def handle_<type>(session, pkt: dict) → None
session.send_json(dict) 로 응답 전송
"""

import asyncio
import json
import time
import random
import string
from dataclasses import dataclass, field, asdict
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from emulator import Session, GameServer


# ── 데이터 모델 ────────────────────────────────────────────────────────────────

@dataclass
class GameObject:
    no: int           # object id (long)
    name: str = ''
    type: str = 'user'
    OX: int = 0
    OY: int = 0
    TX: int = 0
    TY: int = 0
    VX: int = 0
    VY: int = 0
    SX: int = 0
    SY: int = 0
    PX: int = 0
    PY: int = 0
    stateIdx: int = 0
    idx: int = 0
    idxs: int = 0
    chatColor: str = '#FFFFFF'
    Chat: str = ''
    TypingText: str = ''

    def to_json(self) -> dict:
        return {k: v for k, v in asdict(self).items()}


@dataclass
class GameItem:
    id: int
    state: int = 0
    num: int = 1


# ── 핸들러 레지스트리 ──────────────────────────────────────────────────────────

HANDLERS = {}

def handler(pkt_type: str):
    def decorator(fn):
        HANDLERS[pkt_type] = fn
        return fn
    return decorator


# ── 핵심 핸들러 ────────────────────────────────────────────────────────────────

@handler('ping')
async def on_ping(session, pkt: dict):
    pass  # 응답 없음, keepalive 별도 처리


@handler('login')
async def on_login(session, pkt: dict):
    userid = pkt.get('userid', 'unknown')
    version = pkt.get('version', '?')
    print(f'  [login] userid={userid!r} version={version!r}')

    # 대기열 없으면 바로 로그인 성공
    session.userid = userid
    session.my_id = session.server.next_id()

    # 게임 오브젝트 등록
    obj = GameObject(
        no=session.my_id,
        name=userid,
        type='user',
        OX=100, OY=100,
        TX=100, TY=100,
    )
    session.server.objects[session.my_id] = obj

    await session.send_json({
        'type': 'login',
        'myId': session.my_id,
        'isAdmin': '0',
    })

    # 초기 게임 오브젝트 동기화
    await session.send_json({
        'type': 'obj',
        'gameObjects': {
            str(k): v.to_json()
            for k, v in session.server.objects.items()
        },
    })

    # 인벤토리 동기화 (빈 인벤토리)
    await session.send_json({'type': 'refresh', 'items': {}})

    # 재화
    await session.send_json({'type': 'bn', 'bn': 1000})

    # 다른 유저들에게 신규 오브젝트 브로드캐스트
    await session.server.broadcast_except(session.my_id, {
        'type': 'objc',
        'objects': {str(session.my_id): obj.to_json()},
    })


@handler('loginRetry')
async def on_login_retry(session, pkt: dict):
    await on_login(session, pkt)


@handler('move')
async def on_move(session, pkt: dict):
    obj_id = int(pkt.get('no', session.my_id or 0))
    tx = pkt.get('TX', 0)
    ty = pkt.get('TY', 0)

    obj = session.server.objects.get(obj_id)
    if obj:
        obj.TX = int(tx) if tx else obj.TX
        obj.TY = int(ty) if ty else obj.TY
        # 즉시 위치 확인으로 응답 (VX/VY)
        await session.server.broadcast({
            'type': 'move',
            'no': str(obj_id),
            'VX': obj.TX,
            'VY': obj.TY,
            'TX': obj.TX,
            'TY': obj.TY,
        })


@handler('myState')
async def on_my_state(session, pkt: dict):
    if not session.my_id:
        return
    obj = session.server.objects.get(session.my_id)
    if obj:
        obj.OX = int(pkt.get('LocationX', obj.OX))
        obj.OY = int(pkt.get('LocationY', obj.OY))
        motion = pkt.get('motion', 0)
        await session.server.broadcast({
            'type': 'motion2',
            'no': str(session.my_id),
            'ox': obj.OX,
            'oy': obj.OY,
            'idxs': int(motion) if motion else 0,
        })


@handler('chat')
async def on_chat(session, pkt: dict):
    text = pkt.get('text', '')
    print(f'  [chat] {session.userid}: {text!r}')
    await session.server.broadcast({
        'type': 'chat',
        'id': str(session.my_id),
        'text': text,
    })


@handler('typing')
async def on_typing(session, pkt: dict):
    await session.server.broadcast({
        'type': 'typing',
        'no': str(session.my_id),
    })


@handler('stopTyping')
async def on_stop_typing(session, pkt: dict):
    await session.server.broadcast({
        'type': 'stopTyping',
        'no': str(session.my_id),
    })


@handler('exit')
async def on_exit(session, pkt: dict):
    await _remove_player(session)


@handler('map')
async def on_map(session, pkt: dict):
    # 맵 이동 — 현재는 같은 맵 유지
    await session.send_json({'type': 'map'})


@handler('webtoken')
async def on_webtoken(session, pkt: dict):
    # 웹 인증 토큰 요청 — 에뮬레이터에서는 더미 토큰 반환
    token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    await session.send_json({'type': 'webtoken', 'token': token})


@handler('friendsList')
async def on_friends_list(session, pkt: dict):
    await session.send_json({'type': 'friends', 'friends': []})


@handler('getOptions')
async def on_get_options(session, pkt: dict):
    await session.send_json({'type': 'options', 'options': {}})


@handler('skillList')
async def on_skill_list(session, pkt: dict):
    await session.send_json({'type': 'skillList', 'skills': []})


@handler('getWork')
async def on_get_work(session, pkt: dict):
    await session.send_json({'type': 'workList', 'works': []})


async def _remove_player(session):
    if session.my_id and session.my_id in session.server.objects:
        del session.server.objects[session.my_id]
        await session.server.broadcast({
            'type': 'remove',
            'no': str(session.my_id),
        })


async def dispatch(session, pkt_type: str, pkt: dict):
    h = HANDLERS.get(pkt_type)
    if h:
        await h(session, pkt)
    else:
        # 미구현 패킷 로그
        print(f'  [unhandled] type={pkt_type!r}  fields={list(pkt.keys())}')
