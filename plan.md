# JoyTalk Windows 리버스 엔지니어링 계획

## Context

이 레포(`joycity`)는 한국 온라인 게임 **JoyTalk**의 macOS 클라이언트(Wineskin 래핑)를 기반으로 진행한 RE 결과물 모음. Phase 1–3까지 완료된 상태로:

- `decompiled/` — `Joytalk.dll`을 ilspycmd로 풀어낸 C# 65,597줄 (난독화된 이름 + XOR 복호화한 문자열 2,698개)
- `parsers/` — 5종 바이너리 포맷 파서 (`.jcr/.mst/.csmi/.irs/.rmm`)
- `server/{protocol,handlers,emulator}.py` — TCP 프레이밍/JSON 디스패치 스텁
- `tools/proxy.py` — 투명 TCP 프록시 (macOS는 `/etc/hosts`+pfctl 사용)
- `docs/phase{1,2,3}_results.md` — 패킷 타입 319개, 인증 흐름, 파일 포맷 분석

**왜 Windows에서 다시 하는가:**
1. **라이브 패킷 캡처** — Phase 3는 디컴파일 코드에서 *추론*만 했고, 실제 트래픽으로 검증한 적이 없음. Windows에선 Wireshark + 호스트 파일 리다이렉트만으로 가능 (Wine 우회 불필요).
2. **실시간 디버깅** — dnSpy로 `Joytalk.exe`에 attach해서 변수/스택을 실측 가능 (macOS에선 불가능).
3. **서버 에뮬레이터 완성** — 클라이언트 ↔ 자체 서버 E2E 흐름을 Windows 네이티브에서 끝까지 돌려보기.
4. **에셋 경로/포맷 재검증** — Windows 설치본의 폴더 구조가 macOS와 다름. 같은 포맷인지 확인 필요.

**최종 산출물:** Windows에서 실제 트래픽으로 검증된 패킷 스펙 + 자체 서버에 클라이언트가 로그인/이동/채팅까지 가능한 최소 에뮬레이터.

---

## Windows 환경 사실관계 (조사 결과)

| 항목 | 값 |
|---|---|
| 설치 경로 | `C:\Users\berrr\AppData\Local\Joytalk\` (`Program Files`가 아님 — `HOW_TO_RUN_Windows.md` 주의사항) |
| 프레임워크 | .NET 10.0, win-x64 |
| 메인 어셈블리 | `Joytalk.dll` (2.0 MB, PE32+ CLR) |
| UI 스택 | CefSharp 103 + WebView2 + WinForms + Vortice D3D11 |
| 음성 | Concentus (Opus) + NAudio |
| 업데이터 | `Update.exe` (Squirrel 추정) + `unins000.exe` (Inno Setup) |
| 빌드 메타 | `2.88.9618.33183`, hash `58130b21...` |

**에셋 폴더 (macOS와 구조 다름):**
- `Itm\{Avt, BtI, BtI_HC, ShI}` — 7.9 MB. `Avt/HLP, UBB, ULB, ...` 처럼 3글자 코드 하위폴더
- `Res\{Bus, Icons, jcr, Lst, Wav}` — 28 MB. `Res\jcr\` 안에 `c0001.jcr`, `h0005.jcr`, `intro.jpg` 등 (기존 파서 호환 가능성 높음)
- `Street\{A, C, E, ES, I, IS, J, M, MS, P, S, W, X}` — **1.5 GB**. 알파벳 인덱스. 맵 데이터 + 거리 단위 리소스로 추정

**서버 엔드포인트 (디컴파일 결과 + debug.log):**
- TCP `jc.joy-june.com:7942` (chat) / `:7945` (game)
- UDP `:7946` (Opus voice, 48kHz mono)
- HTTPS `https://jc.joy-june.com/...` (CefSharp가 인앱 브라우저로 로드)

---

## 단계별 작업

### Step 1 — Windows 빌드 검증 & macOS와 diff (1–2시간)

**목표:** Windows `Joytalk.dll`이 macOS에서 디컴파일한 것과 같은 버전인지 확인. 다르면 어디가 바뀌었는지 파악.

1. Windows DLL을 ILSpy/dnSpy로 다시 디컴파일 → `windows_decompiled/` 폴더에 저장.
2. 기존 `decompiled\-\-.cs` 와 `diff` (PowerShell `Compare-Object` 또는 VS Code diff).
3. 차이점이 있으면 `docs\windows_diff.md`에 기록 (난독화 이름 매핑이 어긋났는지, 신규 패킷 타입이 생겼는지 우선 체크).
4. **문자열 블롭 재추출** — `playground\extract_blob.py`를 Windows DLL 대상으로 실행 → 새 `string_blob.bin` 생성. XOR 키(`pos ^ 0xAA`)가 같은지 1개라도 복호해서 검증.
5. dnSpy로 DLL 열고 `_4` (블롭 배열) 사이즈와 `_5` (캐시 배열) 길이 확인 → Phase 3 문서의 `42,797 bytes / 2,698 strings`와 비교.

**결과물:** `docs\windows_diff.md` (버전 동일 확인 또는 신규/변경된 핸들러 목록).

### Step 2 — 라이브 패킷 캡처로 프로토콜 검증 (2–3시간)

**목표:** Phase 3가 *추론*했던 프레임 구조/JSON 스키마를 실제 트래픽으로 검증.

1. **호스트 리다이렉트** (관리자 PowerShell):
   ```powershell
   Add-Content C:\Windows\System32\drivers\etc\hosts "127.0.0.1 jc.joy-june.com"
   ```
2. **프록시 macOS 의존성 제거** — `tools\proxy.py:28-32`의 macOS 전용 pfctl 모드 분기를 정리하거나 hosts 모드만 쓰도록. 신규 파일은 만들지 말고 기존 `proxy.py`의 hosts 모드를 그대로 사용. `--upstream` 인자로 진짜 서버 IP 직접 지정 가능.
3. 진짜 서버 IP 확인:
   ```powershell
   Resolve-DnsName jc.joy-june.com -Server 8.8.8.8
   ```
   결과를 `--upstream` 으로 넘김.
4. **Wireshark 병행 캡처** — 루프백 인터페이스에서 포트 7942/7945 필터로 캡처. 프록시가 정상 프레이밍하는지 교차 검증.
5. 클라이언트 실행: `Joytalk.exe` → 로그인 → 짧게 이동/채팅/아이템 줍기 시연.
6. `captures\proxy_*.jsonl` 결과를 `tools\decode_capture.py`로 디코드 → 통계:
   - 실제로 등장한 `"type"` 값 vs Phase 3 문서의 319개 매핑 비교
   - 추론이 빗나간 필드(예: `move`의 `VX/VY/TX/TY`) 실제 값으로 보정
   - 알 수 없는 신규 타입 → `docs\phase4_live_capture.md`에 기록

**결과물:** `docs\phase4_live_capture.md` + 검증된 `captures\*.jsonl` 샘플 1세트 (login → 이동 → 채팅 → 종료).

### Step 3 — 에셋 폴더 매핑 & 파서 재검증 (1–2시간)

**목표:** Windows 폴더 구조에 맞게 파서가 동작하는지 확인. 코드 수정은 최소화.

1. **파서 진입점 경로 갱신** — 각 파서(`parsers\*.py`)는 standalone 실행 시 macOS 기본 경로를 사용함. 인자로 Windows 경로를 넘겨 동작 확인:
   ```powershell
   python parsers\jcr_parser.py "C:\Users\berrr\AppData\Local\Joytalk\Res\jcr\c0001.jcr"
   python parsers\mst_parser.py "C:\Users\berrr\AppData\Local\Joytalk\Res\Lst\<mst파일>"
   python parsers\rmm_parser.py "C:\Users\berrr\AppData\Local\Joytalk\Street\<rmm파일>"
   ```
2. 매직 바이트가 안 맞으면 → dnSpy로 클라이언트의 파일 로드 함수에 BP 걸어서 실제 호출 경로/포맷 확인.
3. **`Street\` 알파벳 폴더 매핑** — 1.5GB라 디컴파일에서 디렉터리명이 어떻게 분기되는지 검색:
   ```powershell
   Select-String -Path decompiled\-\-.cs -Pattern '"Street\\\\[A-Z]"' | Select -First 50
   ```
   알파벳 → 맵 카테고리 매핑을 `docs\windows_assets.md`에 정리.
4. **palette 미해결 분** (macOS 작업의 loose end) — `Street\P\` 또는 `Res\Lst\` 안의 `.pal` 파일을 `irs_parser.py`와 결합해서 실제 PNG 출력까지 검증.

**결과물:** `docs\windows_assets.md` (폴더→포맷→파서 매핑 테이블) + 샘플 PPM/PNG 출력.

### Step 4 — 서버 에뮬레이터 핵심 핸들러 채우기 (4–6시간)

**목표:** 클라이언트가 자체 서버에 연결해서 로그인 → 맵 입장 → 이동/채팅까지 가능한 최소 에뮬레이터.

`server\emulator.py`/`handlers.py`/`protocol.py`를 확장. 새 모듈 만들지 말고 기존 파일에 핸들러 추가.

1. **프레이밍은 검증 완료** — `server\protocol.py`의 `read_frame/make_json_frame/make_binary_frame`는 그대로 사용.
2. Step 2 캡처 데이터를 골든 픽스처로 `tests\fixtures\` (또는 `captures\golden\`)에 저장 — 핸들러가 같은 바이트를 재생산하는지 비교.
3. **최소 핸들러 세트** (Phase 3 문서의 핸들러 ID 그대로):
   - `login` (`_2007`): myId 부여, 캐릭터 데이터 더미 응답
   - `loginQueue` (`_2008`): 즉시 통과
   - `webtoken` (`_1680_2055`): 더미 토큰 발급 → `/bbs/login_check.php?pcode=` 경로 모킹 (간단한 HTTP 서버 추가)
   - `obj` (`_2025`) / `objc` (`_202A`) / `remove` (`_2064`): 빈 맵 + NPC 1명
   - `move` (`_2062`) / `motion2` (`_2004`): 에코백
   - `chat` (`_00A0`): 본인+다른 더미 NPC 에코
4. **HTTPS 모킹** — CefSharp가 `https://jc.joy-june.com/`를 호출하므로, 인증 흐름이 막히면 로컬 HTTPS 서버 (자체 서명 인증서) + Windows 인증서 신뢰 추가 필요. 처음엔 `webtoken` 흐름을 우회하도록 클라이언트 분기를 dnSpy로 임시 패치하는 게 더 빠를 수 있음.
5. 로그 출력은 한국어 유지 (CLAUDE.md 컨벤션).

**결과물:** `python server\emulator.py` 실행 후 `Joytalk.exe`가 캐릭터 화면까지 진입.

### Step 5 — E2E 검증 (2–3시간)

1. hosts 파일을 `127.0.0.1`로 유지 + `server\emulator.py` 실행.
2. `Joytalk.exe` 시작 → 로그인 → 맵 진입 → 이동/채팅.
3. dnSpy를 attach해서 메인 스레드에서 예외/끊김 없는지 확인.
4. 안 되는 동작은 Step 2 골든 캡처와 비교해서 누락 핸들러 추가.
5. `docs\phase5_e2e.md` 작성 — 동작/미동작 매트릭스, 다음 단계 후보.

---

## 핵심 파일

**수정/생성:**
- `docs\windows_diff.md` (신규) — Step 1
- `docs\phase4_live_capture.md` (신규) — Step 2
- `docs\windows_assets.md` (신규) — Step 3
- `docs\phase5_e2e.md` (신규) — Step 5
- `server\handlers.py` — Step 4 핸들러 추가
- `server\emulator.py` — Step 4 디스패치 확장
- `tools\proxy.py:28-32` — macOS 전용 pfctl 분기 정리(선택), Windows 모드 우선
- `parsers\*.py` 의 standalone 기본 경로 — Windows 경로로 갱신 (선택)

**재사용 (수정 없음):**
- `decompiled\-\-.cs` — Phase 3 매핑 그대로 활용
- `parsers\{jcr,mst,csmi,irs,rmm}_parser.py` — 인자로 경로만 넘기면 작동 가능성 높음
- `server\protocol.py:20-49` — `read_frame`/`make_json_frame`/`make_binary_frame`
- `tools\decode_capture.py` — Step 2 캡처 분석
- `playground\extract_blob.py` — Step 1 블롭 재추출
- `playground\HOW_TO_RUN_Windows.md` — 도구 설치/사용법 (단, 게임 경로는 `C:\Program Files\JoyTalk\`로 잘못 적혀 있음 → 본 작업 중 `AppData\Local\Joytalk`로 정정 필요)

---

## 검증 방법

| 단계 | 검증 |
|---|---|
| Step 1 | `string_blob.bin` 첫 10개 문자열을 macOS Phase 1 결과와 일치 확인 |
| Step 2 | 캡처 JSONL의 `"type"` 빈도 상위 20개가 Phase 3 문서 표 대비 99% 매핑 |
| Step 3 | `c0001.jcr` → PPM 출력이 macOS 결과와 동일 픽셀 |
| Step 4 | `server\emulator.py` + `Joytalk.exe` → 캐릭터 화면 도달 (오류 다이얼로그 없음) |
| Step 5 | 자체 서버에서 이동/채팅이 비주얼적으로 동작 |

---

## 진행 시 주의

- **Wineskin 경로 하드코딩 주의** — `parsers/`와 `tools/`에 macOS 경로(`/Applications/JoyTalk.app/...`)가 default로 박힌 곳이 많음. 인자로 우회.
- **서버 에뮬레이터의 인증 흐름**이 가장 큰 미지수 — `webtoken` HTTPS 콜백을 클라이언트 패치 vs 로컬 HTTPS 서버 중 빠른 길 선택.
- **Joytalk.dll 백업 먼저** — dnSpy로 패치할 일 생기면 `Joytalk.dll.bak` 복사부터.
- **CLAUDE.md 컨벤션 유지** — 한국어 주석/로그, 의존성 stdlib only, `captures/` 자동 생성.
- **Step별 git 커밋** — 단계마다 docs 새 파일 생기므로 별도 커밋해두면 롤백 용이.

---

## 다음 단계 (이 계획 밖, 참고)

- 음성(UDP 7946 Opus) 분석은 별도 Phase 6 권장
- 인앱 CefSharp 브라우저가 부르는 `/bbs/*.php` API 시퀀스 풀어내기 → 본 계획에선 webtoken 한 개만 다룸
- `Update.exe`(Squirrel) 흐름 분석으로 자동 업데이트 차단 방법 확보 (게임 버전 고정용)
