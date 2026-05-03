# Phase 5 결과: 자체 서버 E2E 동작 검증

> 검증일: 2026-05-03
> 환경: Windows 11, Joytalk `2.88.9618.33183` (UpdateBaseUrl 패치본)
> 자체 서버: `server/emulator.py` (NDJSON + 80/443 raw passthrough)
> 클라이언트 ↔ 서버 redirect: hosts `127.0.0.1 jc.joy-june.com`

---

## 1. 동작/미동작 매트릭스

| 기능 | 결과 | 비고 |
|---|---|---|
| Update.exe 우회 | ✅ | `playground/patch_update_url.py` 로 `UpdateBaseUrl` const 교체 (38B) |
| HTTPS 인앱 브라우저 (CefSharp) | ✅ | emulator 의 raw TCP passthrough (80/443) → 진짜 서버 |
| TCP 로그인 (NDJSON) | ✅ | 본인 `myId` 발급, ping/login/exp/bn/hp/refresh/info/userSaleDown 시퀀스 푸시 |
| 맵 진입 (검은 화면 → 렌더링) | ✅ | `map` 패킷에 `MapNum`/`MapName`/`bgstr` + 플레이어 GameObject 풀 필드 |
| 캐릭터 이동 | ✅ | 클라 `move` → 서버 broadcast echo (TX/TY/OX/OY) |
| 채팅 | ✅ | 클라 `chat` → 서버 broadcast (`{"type":"chat","no":<myId>,"text":...}`) |
| 다른 유저 등장 | ⚠️ 미검증 | 1세션만 테스트, multi-session 시 `objc` broadcast 동작은 smoke 로만 확인 |
| 인벤토리 / 상점 | ⚠️ 미구현 | refresh 는 빈 dict, userSaleDown 도 더미 5개. 클릭/구매 시 unhandled 패킷 다수 예상 |
| 음성톡 (UDP 7946) | ❌ | Phase 4 캡처에 없었음, emulator 미구현 |
| 맵 변경 (`type:"map"` 클라 요청) | ✅ ack | 같은 맵 유지 ack 만 — 다른 맵으로 실제 전환은 미구현 |

---

## 2. 재현 절차

### 2.1 사전 준비 (한 번만)

```powershell
# Joytalk.dll 백업 + UpdateBaseUrl 패치 (Update.exe 자동 다운로드 차단)
py -3.11 playground\patch_update_url.py

# 관리자 PowerShell — hosts 리다이렉트
Add-Content C:\Windows\System32\drivers\etc\hosts "127.0.0.1 jc.joy-june.com"
```

### 2.2 매 실행

```powershell
# 일반 셸
py -3.11 server\emulator.py
```

```
==================================================
  JoyTalk 서버 에뮬레이터 (NDJSON)
==================================================
[emulator] 리스닝: 0.0.0.0:7942
[emulator] 리스닝: 0.0.0.0:7945
[passthrough] 0.0.0.0:80 → 119.200.71.233:80
[passthrough] 0.0.0.0:443 → 119.200.71.233:443
[emulator] 준비 완료 — 클라이언트 대기 중...
```

```powershell
# 다른 셸에서 클라
& "C:\Users\berrr\AppData\Local\Joytalk\Joytalk.exe"
```

기대 동작:
1. 업데이트 에러 다이얼로그 잠시 (UpdateBaseUrl 가 invalid 라 실패)
2. 확인 → CefSharp 로그인 폼 (HTTPS passthrough 로 정상 로드)
3. 아이디/비번 입력 → 자체 서버로 TCP 로그인
4. "테스트맵" 진입 → 캐릭터 렌더링
5. 이동/채팅 동작

### 2.3 원복

```powershell
# Joytalk.dll 원복
py -3.11 playground\patch_update_url.py --restore

# hosts 정리 (관리자 PowerShell)
(Get-Content C:\Windows\System32\drivers\etc\hosts) `
  | Where-Object { $_ -notmatch 'jc.joy-june.com' } `
  | Set-Content C:\Windows\System32\drivers\etc\hosts
```

---

## 3. 진단 시 마주친 함정 (시간순)

1. **proxy 의 `read_frame` 무한 대기 (Step 2 초반)**
   `[u32 length][type byte]` envelope 가정으로 `readexactly(4)` 호출 →
   Windows 빌드는 NDJSON 이라 4바이트 채워질 때까지 forward 안 함 → 클라 timeout.
   **해결:** raw chunk forward.

2. **HTTPS 차단 → CefSharp 로그인 폼 안 뜸 (Step 2 중반)**
   hosts 가 `jc.joy-june.com` 을 127.0.0.1 로 보내는데 443 에 바인드 안 한 상태.
   **해결:** proxy/emulator 에 80/443 raw TCP passthrough 추가 (TLS SNI 가 평문이라 cert 위조 불필요).

3. **Update.exe spawn → 무한 로딩 (Step 5 초반)**
   Joytalk.exe 가 manifest 200 + 버전 불일치 → Update.exe 자동 다운로드 + 실행.
   Update.exe 의 자체 update 가 영원히 대기.
   **해결:** Joytalk.dll 의 `UpdateBaseUrl` const 를 invalid 호스트로 교체 (38B 동일 길이) →
   `DownloadAndRunUpdater` 가 connection 실패 → catch → false 리턴 → 게임 본체 진행.

4. **로그인 후 검은 화면 (Step 5 중반)**
   초기 emulator 의 `map` 응답이 `{"type":"map"}` 만 — 진짜는 `MapNum`/`MapName`/`bgstr`/`OX`/`OY`/`weatherType` 필요.
   플레이어 `GameObject` 도 type=`"c"`, `idx`/`idxs`/`speed`/`EOY`/`defaultAni`/`itemColor`(20슬롯) 등 풀 필드 있어야 클라가 캐릭터 스프라이트 로드.
   **해결:** 캡처 골든의 두 번째 `obj` 패킷 (단일 player GO) 구조 그대로 재현.

---

## 4. 다음 단계 후보

- 아이템 spawn / 가구 / 인벤토리 — 캡처에 `objc` 로 92개 GO 가 들어왔는데 emulator 는 빈 맵.
  골든 캡처의 `obj` 첫 번째 패킷을 그대로 재생만 해도 NPC/아이템 다수가 보일 듯.
- multi-session 검증 — 두 클라 동시 접속 시 서로 보이는지.
- 인벤토리 / 가게 / 직업 — `getOptions`, `getWork`, `skillList`, `friendsList` 핸들러는 빈 응답만. 실제 UI 시도 시 unhandled 패킷이 다수 등장할 것 — `[unhandled]` 로그 모아서 우선순위 매기는 게 다음 라운드 핵심.
- Wireshark 풀 캡처 + binary type=5/voice type=6 트리거 액션 (춤, 보이스톡) 으로 Phase 3 의 binary frame 가설 재검증.
- Squirrel/Velopack `Update.exe` 분석 → 자동 업데이트 영구 비활성화 (현재는 DLL 패치라 게임 재설치 시 풀림).

---

## 5. 산출물

```
server/emulator.py       NDJSON + 80/443 passthrough
server/handlers.py       login 시퀀스 14개 + map/move/chat echo
tests/test_emulator_smoke.py   골든 캡처 → emulator 재생 검증

playground/patch_update_url.py   Joytalk.dll UpdateBaseUrl 패치/원복
playground/inspect_obj.py        디버깅용 (캡처 obj 구조 확인)

docs/windows_diff.md             Step 1
docs/phase4_live_capture.md      Step 2
docs/windows_assets.md           Step 3
docs/phase5_e2e.md               Step 5 (this)
```
