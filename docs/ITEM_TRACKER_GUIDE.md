# JoyTalk 아이템 스폰 트래커 사용 가이드

> 게임 서버 트래픽을 투명하게 중계하면서 특정 아이템이 맵에 등장하면 실시간 알림을 보내는 도구

---

## 동작 원리

```
게임 클라이언트 ──► 119.200.71.233:7942
                         ↓  pfctl (커널 레벨 리다이렉트)
                    127.0.0.1:17942 (이 프록시)
                         ↓  아이템 감지 → 알림
                    119.200.71.233:7942 (실제 서버)
```

게임이 서버 IP를 하드코딩하기 때문에 `/etc/hosts` 방식은 동작하지 않습니다.  
대신 macOS의 `pfctl` (패킷 필터)로 커널 레벨에서 트래픽을 리다이렉트합니다.  
프록시가 패킷을 중계하면서 `obj` / `objc` / `remove` 패킷에서 아이템을 감지.  
게임 플레이에는 영향 없음.

---

## 사전 준비

Python 3.11 이상 필요. 추가 패키지 불필요 (표준 라이브러리만 사용).

```bash
python3 --version   # 3.11 이상인지 확인
```

---

## 빠른 시작

### 1. pfctl 리다이렉트 활성화 (터미널 1)

```bash
cd /Applications/JoyTalk.app
sudo bash tools/pf_redirect.sh start
```

> ⚠️ 이 상태에서는 프록시가 실행 중일 때만 게임 접속 가능.  
> 프록시를 끄면 게임 접속 안 됨 — 종료 시 아래 원복 참고.

### 2. 트래커 실행 (터미널 2)

```bash
cd /Applications/JoyTalk.app
python3 tools/item_tracker.py
```

### 3. 게임 실행 후 접속

평소처럼 JoyTalk 실행 → 로그인 → 게임 진행.  
아이템이 맵에 등장하면 터미널에 실시간으로 표시됨.

### 4. 종료 후 원복

```bash
# 트래커: Ctrl+C
# pfctl 원복:
sudo bash tools/pf_redirect.sh stop
```

---

## 단계별 사용법

### Step 1 — 아이템 타입 값 확인 (최초 1회 필수)

게임마다 오브젝트의 `type` 필드 값이 다릅니다.  
`--discover` 모드로 실행하면 맵에 있는 모든 오브젝트의 타입/이름을 수집해줍니다.

```bash
python3 tools/item_tracker.py --discover
```

게임에 접속해서 5~10분 돌아다닌 뒤 `Ctrl+C`로 종료하면 결과 출력:

```
DISCOVER 결과: 감지된 오브젝트 타입/이름
──────────────────────────────────────────
  type = 'user'
    - '플레이어A'
    - '플레이어B'

  type = 'npc'
    - '강아지'
    - '고양이점원'

  type = 'item'         ← 이게 아이템
    - '장미꽃다발'
    - '생일케이크'
    - '선물상자'
    - '골드코인'

→ --types 옵션에 아이템 타입 값을 넣어서 재실행하세요.
```

---

### Step 2 — 감시 실행

discover 결과를 보고 아래 옵션 조합으로 실행.

#### 특정 이름으로 필터 (부분 일치)

```bash
python3 tools/item_tracker.py --items "장미꽃,케이크"
```

#### 아이템 타입 전체 감시

```bash
python3 tools/item_tracker.py --types "item"
```

#### 이름 + 타입 동시 필터

```bash
python3 tools/item_tracker.py --types "item" --items "장미,선물"
```

#### macOS 알림센터 팝업 추가

```bash
python3 tools/item_tracker.py --items "장미꽃" --notify
```

![알림 예시: 아이템 등장! 이름: 장미꽃  위치: X=450 Y=320]

#### Discord 웹훅 알림 추가

```bash
python3 tools/item_tracker.py --items "장미꽃" --webhook "https://discord.com/api/webhooks/XXXX/YYYY"
```

Discord 웹훅 URL 만드는 법:  
서버 설정 → 연동 → 웹후크 → 새 웹후크 → URL 복사

#### 모든 알림 동시에

```bash
python3 tools/item_tracker.py \
  --types "item" \
  --items "장미꽃,케이크,선물상자" \
  --notify \
  --webhook "https://discord.com/api/webhooks/XXXX/YYYY"
```

---

## 터미널 출력 예시

아이템이 등장하면 이렇게 표시됩니다:

```
  ┌─────────────────────────────────────────┐
  │  🎁 아이템 등장!
  │  이름: 장미꽃다발 [type=item id=20481]
  │  위치: X=450  Y=320
  │  시각: 2026-04-19 15:32:07
  └─────────────────────────────────────────┘

  [15:32:41.220] 아이템 제거: 장미꽃다발 (id=20481)

  ┌─────────────────────────────────────────┐
  │  🎁 아이템 재등장!
  │  이름: 장미꽃다발 [type=item id=20481]
  │  위치: X=500  Y=350
  │  시각: 2026-04-19 15:33:02
  └─────────────────────────────────────────┘
```

---

## 캡처 로그 파일

실행할 때마다 `captures/tracker_YYYYMMDD_HHMMSS.jsonl` 파일에 S→C 패킷이 저장됩니다.  
나중에 분석하거나 재생할 때 사용 가능.

```bash
# 저장된 캡처 목록 확인
ls -la /Applications/JoyTalk.app/captures/

# 캡처 분석 (통계)
python3 tools/decode_capture.py captures/tracker_*.jsonl --stats

# 특정 패킷 타입만 보기
python3 tools/decode_capture.py captures/tracker_*.jsonl --filter obj,objc,remove

# 전체 필드 출력
python3 tools/decode_capture.py captures/tracker_*.jsonl --filter obj --full
```

---

## 전체 옵션 목록

```
옵션              기본값               설명
──────────────────────────────────────────────────────────────
--items           (없음)              감시할 아이템 이름, 쉼표 구분, 부분 일치
                                      예: --items "장미꽃,케이크,선물"
--types           (없음)              감시할 type 값, 쉼표 구분
                                      예: --types "item,drop"
--discover        False               모든 오브젝트 타입/이름 수집 모드
--notify          False               macOS 알림센터 팝업 (소리 포함)
--webhook         (없음)              Discord 웹훅 URL
--upstream        119.200.71.233      실서버 IP
--port-chat       17942               로컬 리스닝 포트 (pfctl이 여기로 보내줌)
--port-game       17945               로컬 리스닝 포트 (pfctl이 여기로 보내줌)
```

필터 동작 규칙:
- `--items`와 `--types` 둘 다 없으면: `user` / `chr` / `character` 타입 제외하고 나머지 전부 알림
- `--types`만 있으면: 해당 타입만
- `--items`만 있으면: 이름 부분 일치
- 둘 다 있으면: 타입 AND 이름 모두 일치해야 알림

---

## 문제 해결

### 게임이 접속이 안 돼요

pfctl 리다이렉트가 활성화되어 있는지 확인:
```bash
sudo bash tools/pf_redirect.sh status
```

프록시가 실행 중인지 확인:
```bash
python3 tools/item_tracker.py   # 이게 실행 중이어야 함
```

실행 중인데도 안 되면 포트 충돌 확인:
```bash
lsof -i :17942
lsof -i :17945
```

### 아이템이 감지가 안 돼요

1. `--discover` 모드로 실행해서 실제 type 값 확인
2. 아이템이 `gameObjects` 안에 있는지 확인 (캡처 로그에서 `--filter obj --full`로 확인)
3. `--items` 없이 `--types item`만으로 먼저 테스트

### 게임 플레이가 느려졌어요

프록시가 같은 맥에서 실행 중이라 영향은 거의 없지만,  
혹시 느리다면 로그 파일 저장을 끄는 옵션 추가 예정.

### 종료 후 게임 접속이 안 돼요

pfctl 원복이 안 된 것:
```bash
sudo bash tools/pf_redirect.sh stop
sudo bash tools/pf_redirect.sh status   # 확인 (anchor 없음 이라고 나오면 정상)
```

---

## 파일 구조

```
JoyTalk.app/
├── tools/
│   ├── item_tracker.py      ← 이 도구 (메인)
│   ├── proxy.py             ← 범용 프록시 + 로거
│   └── decode_capture.py    ← 캡처 파일 분석기
├── server/
│   ├── protocol.py          ← 프레임 파싱 (item_tracker가 import)
│   ├── handlers.py          ← 에뮬레이터 핸들러
│   └── emulator.py          ← 독립 에뮬레이터 서버
└── captures/
    └── tracker_*.jsonl      ← 패킷 로그
```
