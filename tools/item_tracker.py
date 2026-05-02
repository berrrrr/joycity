#!/usr/bin/env python3
"""
JoyTalk 아이템 스폰 트래커

실서버 트래픽을 투명하게 중계하면서 특정 아이템이 맵에 등장하면 알림.

사용법:
  # 1. /etc/hosts에 리다이렉트 추가
  sudo bash -c "echo '127.0.0.1 jc.joy-june.com' >> /etc/hosts"

  # 2. 트래커 실행
  python3 item_tracker.py

  # 3. 아이템 이름 필터 지정 (쉼표 구분)
  python3 item_tracker.py --items "장미꽃,케이크,선물상자"

  # 4. 타입 필터 (실캡처 후 --discover로 확인한 타입 값)
  python3 item_tracker.py --types "item,drop"

  # 5. 원복
  sudo sed -i '' '/jc.joy-june.com/d' /etc/hosts

옵션:
  --items    감시할 아이템 이름 (부분 일치, 쉼표 구분). 미지정시 모든 오브젝트
  --types    감시할 GameObject.type 값 (쉼표 구분)
  --discover 처음 5분간 등장하는 모든 오브젝트 타입/이름 수집해서 출력
  --notify   macOS 알림센터 팝업 사용 (기본: 터미널 출력만)
  --webhook  Discord 웹훅 URL (알림 전송)
  --port-chat 7942
  --port-game 7945
  --upstream jc.joy-june.com
"""

import asyncio
import argparse
import json
import struct
import sys
import subprocess
import datetime
import urllib.request
import urllib.error
from pathlib import Path
from collections import defaultdict
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / 'server'))
from protocol import read_frame, parse_frame

UPSTREAM_HOST = 'jc.joy-june.com'
LOG_DIR = Path(__file__).parent.parent / 'captures'


def ts() -> str:
    return datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]


def now_str() -> str:
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ── 알림 ─────────────────────────────────────────────────────────────────────

def notify_terminal(item_name: str, x: int, y: int, action: str = '등장'):
    line = (
        f'\n'
        f'  ┌─────────────────────────────────────────┐\n'
        f'  │  🎁 아이템 {action}!                        \n'
        f'  │  이름: {item_name:<32}\n'
        f'  │  위치: X={x}  Y={y:<28}\n'
        f'  │  시각: {now_str():<29}\n'
        f'  └─────────────────────────────────────────┘\n'
    )
    print(line)
    # 터미널 벨
    print('\a', end='', flush=True)


def notify_macos(title: str, message: str):
    try:
        script = f'display notification "{message}" with title "{title}" sound name "Glass"'
        subprocess.run(['osascript', '-e', script], capture_output=True)
    except Exception:
        pass


def notify_discord(webhook_url: str, item_name: str, x: int, y: int):
    payload = {
        'embeds': [{
            'title': f'🎁 아이템 스폰: {item_name}',
            'color': 0x00ff88,
            'fields': [
                {'name': 'X', 'value': str(x), 'inline': True},
                {'name': 'Y', 'value': str(y), 'inline': True},
                {'name': '시각', 'value': now_str(), 'inline': False},
            ],
        }]
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.URLError as e:
        print(f'  [webhook 오류] {e}')


# ── 오브젝트 트래커 ───────────────────────────────────────────────────────────

class ItemTracker:
    def __init__(self, args):
        self.args = args
        self.item_filters: list[str] = [s.strip() for s in args.items.split(',')] if args.items else []
        self.type_filters: list[str] = [s.strip() for s in args.types.split(',')] if args.types else []
        self.objects: dict[str, dict] = {}   # id → GameObject dict
        self.seen_ids: set[str] = set()      # 알림 중복 방지 (리스폰 제외)
        self.discover_log: dict[str, set] = defaultdict(set)  # type → set of names

    def _matches(self, obj: dict) -> bool:
        """이 오브젝트가 감시 대상인지 판단."""
        # discover 모드: 모두 기록
        if self.args.discover:
            return True

        name = str(obj.get('name', '') or obj.get('Name', '')).lower()
        type_val = str(obj.get('type', '') or obj.get('Type', '')).lower()

        # 타입 필터가 있으면 타입 먼저 체크
        if self.type_filters:
            if not any(tf.lower() in type_val for tf in self.type_filters):
                return False

        # 이름 필터가 있으면 이름 체크
        if self.item_filters:
            return any(f.lower() in name for f in self.item_filters)

        # 둘 다 없으면 사용자/npc 제외하고 나머지 (아이템 추정)
        if type_val in ('user', 'chr', 'character', ''):
            return False

        return True

    def _alert(self, obj: dict, action: str = '등장'):
        name = obj.get('name') or obj.get('Name') or '(이름없음)'
        x = obj.get('OX') or obj.get('ox') or obj.get('TX') or 0
        y = obj.get('OY') or obj.get('oy') or obj.get('TY') or 0
        type_val = obj.get('type', '?')
        obj_id = str(obj.get('no', obj.get('id', '?')))

        notify_terminal(f'{name} [type={type_val} id={obj_id}]', int(x), int(y), action)

        if self.args.notify:
            notify_macos(f'JoyTalk 아이템 {action}', f'{name}  X={x} Y={y}')

        if self.args.webhook:
            notify_discord(self.args.webhook, name, int(x), int(y))

    def process_objects(self, objects_dict: dict, action: str = '등장'):
        """obj/objc 패킷의 gameObjects/objects 딕셔너리 처리."""
        for obj_id, obj in objects_dict.items():
            if not isinstance(obj, dict):
                continue

            # discover 모드: 타입/이름 기록
            if self.args.discover:
                type_val = str(obj.get('type', obj.get('Type', 'unknown')))
                name = str(obj.get('name', obj.get('Name', '')))
                self.discover_log[type_val].add(name[:40])

            self.objects[str(obj_id)] = obj

            if self._matches(obj):
                # 리스폰 감지: 이미 seen이었다가 remove 후 다시 등장하면 '재등장'
                is_new = str(obj_id) not in self.seen_ids
                self.seen_ids.add(str(obj_id))
                a = action if is_new else '재등장'
                self._alert(obj, a)

    def process_remove(self, pkt: dict):
        obj_id = str(pkt.get('no', ''))
        if obj_id and obj_id in self.objects:
            obj = self.objects.pop(obj_id)
            self.seen_ids.discard(obj_id)  # 제거 후 재등장 감지 허용
            if self._matches(obj):
                name = obj.get('name') or '(이름없음)'
                print(f'  [{ts()}] 아이템 제거: {name} (id={obj_id})')

    def process_delta(self, pkt: dict):
        """delta 패킷: reflection 업데이트. 오브젝트 위치 변경 반영."""
        obj_id = str(pkt.get('no', ''))
        if obj_id in self.objects:
            obj = self.objects[obj_id]
            # 이동 등 임의 필드 업데이트
            for k, v in pkt.items():
                if k != 'type':
                    obj[k] = v

    def process_packet(self, pkt: dict):
        pkt_type = pkt.get('type', '')

        if pkt_type == 'obj':
            raw = pkt.get('gameObjects', {})
            if isinstance(raw, dict):
                self.process_objects(raw, '등장')

        elif pkt_type == 'objc':
            raw = pkt.get('objects', {})
            if isinstance(raw, dict):
                self.process_objects(raw, '등장')

        elif pkt_type == 'remove':
            self.process_remove(pkt)

        elif pkt_type == 'delta':
            self.process_delta(pkt)

        elif pkt_type == 'login':
            # 방 입장 시 기존 오브젝트 초기화
            self.objects.clear()
            self.seen_ids.clear()
            print(f'  [{ts()}] 로그인 감지 — 오브젝트 초기화')

        elif pkt_type == 'map':
            # 맵 이동 시 초기화
            self.objects.clear()
            self.seen_ids.clear()
            print(f'  [{ts()}] 맵 이동 감지 — 오브젝트 초기화')

    def print_discover_report(self):
        print('\n' + '=' * 60)
        print('  DISCOVER 결과: 감지된 오브젝트 타입/이름')
        print('=' * 60)
        for type_val, names in sorted(self.discover_log.items()):
            print(f'\n  type = {type_val!r}')
            for name in sorted(names)[:20]:
                print(f'    - {name!r}')
            if len(names) > 20:
                print(f'    ... +{len(names)-20}개 더')
        print()
        print('→ --types 옵션에 아이템 타입 값을 넣어서 재실행하세요.')
        print()


# ── 프록시 코어 ───────────────────────────────────────────────────────────────

async def relay_with_tracking(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    direction: str,
    tracker: ItemTracker,
    log_file,
):
    """한 방향 릴레이. S→C 패킷만 트래커에 전달."""
    try:
        while True:
            payload = await read_frame(reader)
            if payload is None:
                break

            parsed = parse_frame(payload)

            # S→C JSON 패킷만 트래킹
            if direction == 'S→C' and parsed.get('type_byte') == 1:
                pkt = parsed.get('json', {})
                tracker.process_packet(pkt)

                # 로그 파일에 기록
                if log_file:
                    entry = {'ts': ts(), 'dir': direction, **parsed}
                    log_file.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')
                    log_file.flush()

            # 원본 프레임 그대로 포워드
            frame = struct.pack('<I', len(payload)) + payload
            writer.write(frame)
            await writer.drain()

    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        writer.close()


async def handle_client(
    client_reader, client_writer,
    upstream_host: str, upstream_port: int,
    tracker: ItemTracker, log_file,
):
    peer = client_writer.get_extra_info('peername')
    print(f'  [{ts()}] 클라이언트 연결: {peer[0]}:{peer[1]}')

    try:
        srv_reader, srv_writer = await asyncio.open_connection(upstream_host, upstream_port)
    except OSError as e:
        print(f'  [{ts()}] 업스트림 연결 실패: {e}')
        client_writer.close()
        return

    print(f'  [{ts()}] 업스트림 연결됨: {upstream_host}:{upstream_port}')

    await asyncio.gather(
        relay_with_tracking(client_reader, srv_writer,    'C→S', tracker, None),
        relay_with_tracking(srv_reader,    client_writer, 'S→C', tracker, log_file),
        return_exceptions=True,
    )

    print(f'  [{ts()}] 세션 종료')

    if tracker.args.discover:
        tracker.print_discover_report()


async def run(args):
    tracker = ItemTracker(args)

    # 로그 파일
    LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path = LOG_DIR / f'tracker_{stamp}.jsonl'
    log_file = open(log_path, 'w', encoding='utf-8')

    print('=' * 60)
    print('  JoyTalk 아이템 스폰 트래커')
    print('=' * 60)
    if tracker.item_filters:
        print(f'  감시 이름: {tracker.item_filters}')
    if tracker.type_filters:
        print(f'  감시 타입: {tracker.type_filters}')
    if args.discover:
        print(f'  모드: DISCOVER (모든 오브젝트 타입 수집)')
    print(f'  로그: {log_path}')
    print(f'  알림: macOS={args.notify}  Discord={bool(args.webhook)}')
    print()
    print('  아이템이 등장하면 아래에 실시간으로 표시됩니다.')
    print('-' * 60)

    servers = []
    for port in [args.port_chat, args.port_game]:
        srv = await asyncio.start_server(
            lambda r, w, p=port: handle_client(
                r, w, args.upstream, p, tracker, log_file
            ),
            '127.0.0.1', port
        )
        servers.append(srv)
        print(f'  [{ts()}] 포트 {port} 리스닝')

    print()

    try:
        async with asyncio.TaskGroup() as tg:
            for srv in servers:
                tg.create_task(srv.serve_forever())
    finally:
        log_file.close()


def main():
    parser = argparse.ArgumentParser(description='JoyTalk 아이템 스폰 트래커')
    parser.add_argument('--upstream', default=UPSTREAM_HOST)
    parser.add_argument('--port-chat', type=int, default=7942)
    parser.add_argument('--port-game', type=int, default=7945)
    parser.add_argument('--items', default='',
                        help='감시할 아이템 이름 (쉼표 구분, 부분 일치)')
    parser.add_argument('--types', default='',
                        help='감시할 type 값 (쉼표 구분)')
    parser.add_argument('--discover', action='store_true',
                        help='모든 오브젝트 타입/이름 수집 (필터 설정용)')
    parser.add_argument('--notify', action='store_true',
                        help='macOS 알림센터 팝업')
    parser.add_argument('--webhook', default='',
                        help='Discord 웹훅 URL')
    args = parser.parse_args()

    print()
    print('※ 게임 클라이언트를 이 프록시로 연결하려면:')
    print(f'   sudo bash -c "echo \'127.0.0.1 {args.upstream}\' >> /etc/hosts"')
    print()
    print('※ 종료 후 원복:')
    print("   sudo sed -i '' '/jc.joy-june.com/d' /etc/hosts")
    print()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print('\n[트래커] 종료')


if __name__ == '__main__':
    main()
