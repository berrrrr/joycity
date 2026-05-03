# Step 1 결과: Windows DLL ↔ macOS 디컴파일본 diff

> 검증일: 2026-05-02
> 대상 DLL: `C:\Users\berrr\AppData\Local\Joytalk\Joytalk.dll`
> 비교 대상: `decompiled/` (macOS Phase 1~3에서 추출), `playground/string_blob.bin`

---

## 1. 결론

| 항목 | 결과 |
|---|---|
| XOR 복호화 알고리즘 (`byte ^ pos ^ 0xAA`) | ✅ Windows에서도 그대로 사용 |
| 빌드 버전 | `2.88.9618.33183` (`58130b21…`) — plan.md와 일치 |
| 기존 `string_blob.bin`(42,797 B)과 byte-level 일치 | ❌ 첫 2,542 B만 동일, 그 이후 분기 |
| 기존 디컴파일 C# (`decompiled/-/-.cs`)이 동일 빌드인지 | ❌ 아닐 가능성 매우 높음 (블롭 차이로 추정) |
| Phase 3의 핸들러 ID(`_2007`, `_2025`…) Windows에서 그대로 유효 | ⚠️ 검증 불가 — 신규 디컴파일 필요 |

**작업 방침:** Step 2(라이브 캡처)는 핸들러 ID 무관하게 진행 가능 — JSON `"type"` 문자열만 필요. Step 4(에뮬레이터)에서 핸들러 ID 정확 매칭이 필요해지면 그때 ilspycmd 재디컴파일 진행.

---

## 2. 검증 절차

### 2.1 PE/CLR 메타데이터

```
ProductVersion    : 1.0.0+58130b216168bf8b5bbe0c33679193f36d2220e0
FileVersion       : 2.88.9618.33183
OriginalFilename  : Joytalk.dll
InternalName      : Joytalk.dll
CompanyName       : Joytalk
CLR runtime ver   : v4.0.30319
SHA-256           : 5627844ab994ad61cb26d6b18dcfdc50e1c802a0e8693c8ce2cf8344a9a2b401
파일 크기         : 2,004,992 bytes
```

### 2.2 문자열 블롭 위치

```
playground/string_blob.bin (macOS) : 42,797 bytes
DLL 안 blob 시작 offset            : 0x19620C  (1,663,500)
공통 prefix                        : 2,542 / 42,797 bytes (5.9%)
```

블롭의 시작 부분(첫 ~2.5 KB)은 일치 — `https://jc.joy-june.com/...` URL 블록은 동일. 그 이후 어셈블리 메서드 순서/string interning이 달라 분기.

### 2.3 같은 XOR 스킴 검증

DLL의 블롭 시작 offset에서 첫 256 byte를 `b ^ pos ^ 0xAA` 로 풀면 그대로 URL이 나옴:

```
https://jc.joy-june.com/joytalk/update/manifest.json
http://jc.joy-june.com/joytalk/server_status.php
http://jc.joy-june.com/joycityw/joytalk_notice.php
http://jc.joy-june.com/joytalk2.php?version=
https://jc.joy-june.com/joytalk/map/?Id=
…
```

→ 키와 알고리즘은 macOS와 완전히 동일. Phase 3 문서의 복호화 코드는 Windows DLL에도 그대로 적용 가능.

### 2.4 새로 등장한 문자열 (샘플)

분기점(byte 2542) 직후 풀어보면 macOS Phase 3에 없던 신규 문자열이 보임:

```
nearchat
bgmVolume / eftVolume / motionVolume / fontform / Opacity / setting.ini
"⭐ 사용자별 개별 설정 사용"     ← 사운드 패널 옵션
"🔊 소리 설정"
checkBoxEft / checkBoxMotion / checkBoxOld / checkBoxMotionOld
panelTop / panelSound / panelEftTrack / panelMotionTrack / panelBgTrack
========== PERFORMANCE REPORT ==========
CPU: % | FPS:  | MEM: MB
```

→ Windows 빌드에서 (1) 사운드 설정 UI 패널, (2) 성능 모니터링이 추가됨. 패킷 핸들러 자체는 아닐 가능성이 높지만, 신규 UI 클래스 → 신규 메서드 → `_5` 캐시 인덱스가 전체적으로 shift 됐을 것.

---

## 3. Step 4(에뮬레이터)에 미치는 영향

Phase 3 문서가 매핑한 패킷 ↔ 핸들러 표:

| JSON `"type"` | 핸들러 |
|---|---|
| `login` | `_2007` |
| `obj` | `_2025` |
| `move` | `_2062` |
| `chat` | `_00A0` |
| ... | ... (총 319개) |

이 매핑의 좌측(JSON `"type"` 문자열)은 **서버↔클라 와이어 프로토콜의 일부**이므로 빌드가 바뀌어도 그대로 — 에뮬레이터 입장에서는 이쪽만 알면 충분. 우측 핸들러 ID는 **dnSpy로 클라이언트 패치**할 때만 필요.

따라서:

1. Step 2/3/5 — 영향 없음 (와이어 포맷만 다룸)
2. Step 4 — 영향 없음, 단 webtoken 우회를 위해 dnSpy 패치를 선택할 경우에만 신규 디컴파일 필요

---

## 4. 추가 산출물

```
playground/extract_blob_windows.py  — Windows DLL 블롭 추출 스크립트
playground/string_blob_windows.bin  — 추출된 raw 블롭 (~341 KB, 끝쪽 노이즈 포함)
playground/string_blob_windows.dec  — XOR 복호화 결과
playground/windows_strings.txt      — 길이 4+ 인쇄 문자열 17,020개
playground/diff_blob.py             — 두 블롭 prefix 비교 + 끝 추정
```

> **주의:** `string_blob_windows.bin`의 정확한 끝점은 CLR FieldRVA 메타데이터를 파싱해야 알 수 있음. 현재는 보수적으로 DLL의 blob start ~ EOF까지 잘라놓아 뒤쪽엔 다른 .data 영역이 섞여 있음. 4글자 이상 ASCII run 기준 마지막 위치는 byte 341,492 (= EOF), printable 비율 30% 기준은 byte 14,470. 정확한 길이가 필요하면 ilspycmd로 재디컴파일.

---

## 5. 다음 단계 결정

- [x] Step 2 진행 (핸들러 ID 영향 없음)
- [ ] (선택) dotnet SDK + ilspycmd 설치 → 신규 `decompiled_windows/-/-.cs` 생성
  - Step 4에서 webtoken 우회를 위해 클라이언트 분기를 dnSpy로 패치할 경우 필요
  - 명령:
    ```powershell
    winget install Microsoft.DotNet.SDK.9
    dotnet tool install -g ilspycmd
    ilspycmd "C:\Users\berrr\AppData\Local\Joytalk\Joytalk.dll" -p -o decompiled_windows
    ```
