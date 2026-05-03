# Phase 4 결과: Windows 라이브 패킷 캡처

> 검증일: 2026-05-03
> 환경: Windows 11, Joytalk.dll `2.88.9618.33183`
> 도구: `tools/proxy.py` (raw chunk relay) + `tools/decode_raw_stream.py`
> 골든 샘플: `captures/golden/proxy_7942_20260503_002756.raw.bin.{c2s,s2c}.jsonl`

---

## 1. 가장 중요한 발견 — 와이어 포맷이 Phase 3와 다르다

### Phase 3 (macOS 빌드 디컴파일에서 *추론*한 것)

```
[u32 length LE][payload]
payload[0] = type byte:
  1 → JSON 텍스트  : [u8=1][i16 json_len LE][UTF-8 JSON \n]
  3 → keepalive   : [u8=3]
  5 → 바이너리    : [u8=5][u16 seq][u8 name_len][name][...]
  6 → voice ctrl
```

### Phase 4 (Windows 빌드 라이브 캡처)

```
{...JSON...}\n
{...JSON...}\n
{...JSON...}\n
```

**그게 전부다.** 외부 envelope (length prefix, type byte) **사용 안 함**. 단순 NDJSON. 바이너리 패킷 / keepalive / voice ctrl 도 이번 세션에선 한 번도 안 등장.

이게 우리가 처음 `read_frame` 기반 프록시로 무한 대기에 빠진 이유 — `readexactly(4)` 가 절대 안 채워지니 4바이트 받기 전엔 한 바이트도 forward 안 됨 → 게임이 hello timeout.

→ **`server/protocol.py` 의 read_frame/make_*_frame 은 Phase 3 잔재. Step 4(에뮬레이터) 에서 NDJSON 으로 다시 짜야 함.**

---

## 2. 캡처 통계

| 방향 | 바이트 | 패킷 | 고유 type 수 |
|---|---|---|---|
| C → S (port 7942) | 1,625 | 23 | 6 |
| S → C (port 7942) | 255,558 | 1,747 | 17 |
| C ↔ S (port 7945) | 0 | 0 | 0 |

**놀라운 점:** **port 7945 (game) 트래픽 0**. 이번 세션의 모든 패킷이 7942 한 포트로만 흘렀다 (chat/game 분리 없음).

> Phase 3의 "7942 chat / 7945 game" 매핑은 macOS 빌드의 분리 모델이거나 우리가 잘못 추론한 것. Windows 빌드는 한 채널로 통합된 듯. (5번 섹션의 후속 검증 필요.)

---

## 3. 등장한 패킷 타입

### 클라이언트 → 서버 (6종)

| type | 횟수 | 예시 페이로드 |
|---|---|---|
| `move` | 13 | `{"type":"move","TY":"92","TX":"90","OX":"89","OY":"92","timestamp":"2"}` |
| `myState` | 5 | `{"type":"myState","Location":..., ...}` (사용자 상태 보고) |
| `chat` | 2 | `{"type":"chat","text":"ee","timestamp":"13"}` |
| `login` | 1 | `{"type":"login","version":"2.88","userid":"…","userpw":"…","timestamp":"1"}` |
| `map` | 1 | 맵 입장/이탈 |
| `exit` | 1 | 종료 |

### 서버 → 클라이언트 (17종)

| type | 횟수 | 비고 |
|---|---|---|
| `state` | 1,005 | 다른 플레이어 상태 변화 (idle/active 등) |
| `move` | 599 | 다른 플레이어 이동 |
| `objc` | 44 | 오브젝트 추가 (씨앗 등 아이템 spawn) |
| `chat` | 36 | 채팅 |
| `expGain` | 34 | EXP 획득 알림 |
| `obj` | 6 | 게임 오브젝트 일괄 동기화 (맵 진입 시) |
| `eftsound` | 6 | 이펙트 사운드 (Phase 3 미문서) |
| `userSaleDown` | 5 | 가게 슬롯 만료 (Phase 3 미문서) |
| `hp` | 3 | HP 변화 |
| `map` | 2 | 맵 정보 |
| `ping` | 1 | 로그인 직후 keepalive 시작 신호 (`{"text":"Login"}`) |
| `login` | 1 | `{"myId":"9168","isAdmin":"0"}` |
| `exp` | 1 | 초기 EXP |
| `bn` | 1 | bn (재화?) 초기값 |
| `refresh` | 1 | **인벤토리 일괄** (3.3 KB JSON) |
| `info` | 1 | `{"home":"","awards":"[]"}` |
| `remove` | 1 | 오브젝트 제거 |

**Phase 3 매핑과의 차이:**
- 신규: `eftsound`, `userSaleDown`, `expGain`, `info`, `bn`, `refresh`, `myState`
- Phase 3에 있었지만 이 세션엔 안 나옴: `webtoken`, `loginQueue`, `delta`, `motion`, `motion2`, `streamChat`, `typing`, `alert`, `newMessage`, `messageHistory` 등 — 시연 시나리오에 안 걸림
- 이름 그대로 일치: `login`, `obj`, `objc`, `remove`, `move`, `chat`, `state`, `map`, `hp`, `exp`

---

## 4. 로그인 흐름 (실측)

```
C → S  {"type":"login","version":"2.88","userid":"…","userpw":"…","timestamp":"1"}

S → C  {"type":"ping","text":"Login"}                     ← 인증 OK 신호 + ping 시작
S → C  {"type":"login","myId":"9168","isAdmin":"0"}       ← 본인 ID
S → C  {"type":"exp","value":"0","max":"100","exp_level":"1"}
S → C  {"type":"bn","bn":"0"}                             ← 재화
S → C  {"type":"hp","value":"72","max":"90"}
S → C  {"type":"refresh","Inventory":{...3.3KB...}}       ← 인벤 전체
S → C  {"type":"info","home":"","awards":"[]"}
S → C  {"type":"userSaleDown","num1":"0..N"}              ← 가게 슬롯
... 이후 obj, state, move 가 푸시됨
```

**결론:** Phase 3가 추정한 "login 이후 webtoken → 브라우저 인증" 흐름은 *이 세션에선* 발생 안 함. 단순 userid/userpw 로 바로 인증.

→ Step 4 에뮬레이터 최소 핸들러는: `login` (myId 발급), `ping` (서버 푸시), `refresh`/`info`/`bn`/`hp`/`exp` (스테이터스 더미 응답), `obj` (빈 맵), `move`/`chat` 에코백 정도면 캐릭터 화면 진입 가능할 것.

---

## 5. 바이너리/voice 트래픽 부재의 의미

이번 세션에선 type=5 binary, type=6 voice 가 한 번도 안 등장. 가능성:
- (a) Windows 빌드는 binary/voice 채널을 별도 포트(예: UDP 7946)로 분리
- (b) 이번 시연이 너무 짧아서 binary 트리거 액션이 없었음 (예: 음성/특정 아이템 사용)
- (c) Phase 3의 `type=5 binary game packet` 자체가 Windows 빌드에서 폐기

**검증 방법:** 다음 캡처에서 보이스톡 / 무거운 액션(춤, 특수 동작) 추가 → binary/voice 등장 여부 확인.

---

## 6. 산출물

```
captures/golden/proxy_7942_20260503_002756.raw.bin.c2s.jsonl   (23 패킷)
captures/golden/proxy_7942_20260503_002756.raw.bin.s2c.jsonl   (1,747 패킷)
                ↑ userpw/userid 마스킹 완료 (tools/sanitize_capture.py)

tools/decode_raw_stream.py  — NDJSON 디코더 + type 빈도 통계
tools/sanitize_capture.py   — PII 마스킹
tools/proxy.py              — raw chunk forward 모드로 리팩토 (read_frame 의존 제거)
playground/patch_update_url.py — UpdateBaseUrl 무력화 (테스트 게임 실행 필수)
playground/diff_blob.py     — Step 1 산출
```

`captures/golden/` 는 `.gitignore` 에서 예외 처리됨 (`!captures/golden/`).

---

## 7. 진행 중 마주친 함정 노트

1. **HTTPS 패스스루 필수**
   클라가 `https://jc.joy-june.com/` (CefSharp 인앱 브라우저) 로딩이 막히면 로그인 UI 자체가 안 뜸.
   → `tools/proxy.py` 가 hosts 모드일 때 `127.0.0.1:443` 도 raw TCP 패스스루. SNI 가 평문이라 인증서 위조 불필요.

2. **Update.exe 자동 업데이트 차단 필요**
   `download.joy-june.com` manifest 가 200 OK + 신버전 → Joytalk 가 Update.exe 를 spawn → Squirrel UI 무한로딩.
   → `playground/patch_update_url.py` 로 `UpdateBaseUrl` const 만 16바이트 짜리 dummy 호스트로 교체하면 우회.
   → 원복: `py -3.11 playground/patch_update_url.py --restore`

3. **frame 단위 read 금지**
   NDJSON 이라 chunk 단위 read & 즉시 forward 가 정답. 4바이트 length 기다리면 데드락.
