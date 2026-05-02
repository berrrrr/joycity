# JoyTalk 앱 역공학 분석 보고서

> 분석일: 2026-04-19  
> 분석 대상: `/Applications/JoyTalk.app`  
> 목적: 게임 구조 파악, 파생 게임/모드 개발 참고

---

## 1. 앱 번들 개요

JoyTalk는 **Wineskin** 래퍼를 통해 macOS에서 실행되는 **Windows 게임**이다.

| 항목 | 내용 |
|------|------|
| 번들 ID | `com.sikarugir.JoyTalk992813094` |
| 번들 버전 | 1.0.1 |
| 게임 버전 | 1.9.9470.1211 (manifest.json 기준) |
| 최종 빌드 | 2025-12-10 |
| macOS 최소 요구 | 10.15.4 (Catalina) |
| 실행 바이너리 | `Contents/MacOS/Sikarugir` (Wineskin 런처) |
| Wine 진입점 | `/Joytalk/Update.exe` |

### Wineskin 구성
- **DXVK**: 활성화 (DirectX → Vulkan 변환)
- **MoltenVK**: 활성화 (Vulkan → Metal 변환)
- **WINEESYNC / WINEMSYNC**: 활성화 (성능 최적화)
- **Wine prefix**: `Contents/SharedSupport/prefix/`
- **가상 C 드라이브**: `prefix/drive_c/`

---

## 2. 게임 엔진 및 기술 스택

게임 본체는 `drive_c/Joytalk/` 에 위치한다.

### 런타임
| 항목 | 내용 |
|------|------|
| 언어 | C# / .NET |
| 프레임워크 | .NET 10.0 (net10.0, WindowsDesktop) |
| 메인 어셈블리 | `Joytalk.dll` (MZ/PE 포맷, .NET CIL) |
| 업데이트 모듈 | `Update.exe` + `Update.dll` |

### 주요 의존성 라이브러리

| 라이브러리 | 버전 | 역할 |
|-----------|------|------|
| **CefSharp** | 103.0.120 | Chromium 내장 브라우저 (UI/채팅) |
| **Microsoft.Web.WebView2** | 1.0.3650.58 | WebView2 (보조 웹 렌더링) |
| **NAudio** | 2.2.1 | 오디오 재생 (WAV/MP3) |
| **Concentus** | 2.2.2 | Opus 음성 코덱 (실시간 음성 채팅) |
| **Vortice.Direct2D1** | 3.8.2 | 2D 렌더링 |
| **Vortice.Direct3D11** | 3.8.2 | 3D 그래픽 |
| **Vortice.DXGI** | 3.8.2 | DirectX 그래픽 인프라 |
| **SharpGen.Runtime** | 2.4.2-beta | COM 상호작용 |

### 핵심 추론
- **CefSharp + Concentus 조합** → 인게임 음성/텍스트 채팅 기능 존재
- **Vortice (Direct2D + Direct3D)** → 2D 스프라이트 기반 게임에 DirectX 가속
- `debug.log`에 CEF 네트워크 오류 → 게임이 **온라인 서버 의존**

---

## 3. 디렉토리 구조

```
drive_c/Joytalk/
├── Joytalk.exe / Joytalk.dll     # 메인 게임 실행파일 (.NET)
├── Update.exe / Update.dll       # 자동 업데이트
├── setting.ini                   # 유저 설정 ([SECTION] user=1)
├── manifest.json                 # 파일 목록 + 해시 (4,743개 파일, 총 ~1.5GB)
├── update.cache                  # 업데이트 캐시 (JSON)
├── debug.log                     # CEF 런타임 로그
├── Res/                          # 기본 리소스
│   ├── jcr/                      # JCR 포맷 스프라이트 (98개)
│   ├── Bus/                      # PNG 버스/UI 이미지 (19개)
│   ├── Lst/                      # MST 포맷 텍스트/메시지 테이블 (6개)
│   └── Wav/                      # WAV 오디오 (Recv.wav, Send.wav)
├── Itm/                          # 아이템 데이터
│   ├── Avt/                      # 아바타 아이템
│   │   ├── HLP/ UBB/ UBG/ ...   # 아이템 카테고리별 JCR
│   │   └── _/                   # ILS 인덱스 파일
│   ├── BtI/                      # 버튼 아이템 JCR
│   ├── BtI_HC/                   # HC 버튼 아이템
│   └── ShI/                      # 숍 아이템
├── Street/                       # 게임 씬/맵/캐릭터 데이터
│   ├── A/                        # 어드민/공통 (EPC, IRS, MGO)
│   ├── C/                        # 캐릭터 스프라이트 (CSMI 포맷, 100+ 카테고리)
│   ├── E/                        # 이펙트
│   ├── ES/                       # 이펙트 + 게임 씬 (GAM IRS)
│   ├── I/                        # 인벤토리 아이템 (GPI + IRS, A~Z)
│   ├── IS/                       # 아이템 섀도우/HC 버전
│   ├── J/                        # 조인트/이펙트 애니메이션 (GPJ + EC0~EC9)
│   ├── M/                        # 맵 데이터 (148개 RMM)
│   ├── MS/                       # 맵 섀도우/미러
│   ├── P/                        # 팔레트 (11개 PAL)
│   ├── S/                        # 사운드/씬 (SPC, CEF, GEF)
│   ├── W/                        # 월드 오브젝트
│   │   ├── Chr/                  # 캐릭터 오디오 (601개 RMS WAV)
│   │   ├── Eft/                  # 이펙트 오디오 (89개 RMS WAV)
│   │   └── Jym/                  # 배경음악/지미 오디오 (273개 RMS WAV)
│   └── X/                        # 기타 IRS
└── etc/                          # 등급 이미지 (grade1~grade10.png)
```

---

## 4. 커스텀 파일 포맷 분석

### 4.1 IRS — Resource File (핵심 스프라이트 컨테이너)
**총 2,318개 (irs + IRS)**

```
헤더: "Resource File\0" (14 bytes)
[02 00] 버전?
[00 00] 
[64 00 00 00] = 100 (청크 수?)
오프셋 테이블: 4바이트 * N개
데이터: 압축/암호화된 스프라이트 프레임
```

- 스프라이트 애니메이션 프레임 집합
- 캐릭터, 아이템, 이펙트, 맵 오브젝트에 모두 사용
- `Street/A/STR/STR00000.irs` = 3.3MB (배경 타일셋으로 추정)
- 내용물은 추가 디코딩 필요 (암호화 가능성 있음)

### 4.2 RMM — RedMoon Map Data (맵)
**총 148개**

```
헤더: "RedMoon MapData 1.0\0" (20 bytes)
타일 데이터 + 오브젝트 배치 정보
한국어 문자열 포함 (EUC-KR 인코딩)
```

- RedMoon(레드문) 계열 2D 온라인 게임 엔진 기반 확인
- 맵 ID는 `Map00001` ~ `Map03003` (최대 3003번 구역)
- `Map00086.smm` 존재 → SMM은 서브맵/섀도우맵 변형 포맷

### 4.3 JCR — Joycity RAW (스프라이트 이미지)
**총 199개**

```
매직: "Joycity #$@(RAW! #!#(!# #!TS" (30 bytes)
독자적인 RLE/압축 인코딩
```

- Joycity(조이시티) 사의 독자 포맷
- `c0001.jcr` ~ `c0008.jcr`: 캐릭터 기본 스프라이트
- `h####.jcr`: 헤어/모자류 아이템 스프라이트
- `intro.jpg` 도 jcr 디렉토리에 위치 (일반 JPEG)

### 4.4 ILS — Joycity Image Pack List (아이템 인덱스)
**총 120개**

```
매직: "Joycity #$@(RAW! #!#(!# #!TS" (IRS와 동일 매직 바이트 계열)
내용: JCR/BMP 파일명 목록 + 참조 인덱스
```

- IRS 파일들의 인덱스 역할
- 예: `1-FDSN-0000.BMP`, `FDS.JCR` 등을 참조

### 4.5 CSMI File 2.0 — 멀티포맷 컨테이너
**GPI, GPC, GPJ, GPD, CPC, SPC, EPC 포맷 공통 헤더**

```
[4바이트] 오브젝트 수
[0D] 길이 prefix
"CSMI File 2.0" (13 bytes)
[버전: 01 or 02 00 00 00]
[공용 헤더 블록]
[3바이트 타입 코드] (예: "ubb", "str", "efl", "eee", "bgk")
[크기 정보]
[좌표 데이터: "0 9 9 7 7 7 8 9 9 0" 같은 변환 행렬]
```

| 확장자 | 타입코드 예 | 용도 추정 |
|--------|-----------|----------|
| `.gpi` | `0001` | 인벤토리 아이템 스프라이트 정의 |
| `.gpc` | `ubb` | 캐릭터 스프라이트 정의 |
| `.gpj` | `eee` | 조인트/파티클 이펙트 정의 |
| `.gpd` | (없음) | 오브젝트 배치/물리 정의 |
| `.cpc` | `ctt`/`ntt` | 충돌 및 이동 경로 |
| `.spc` | `efl`/`sef` | 씬/사운드 배치 |
| `.epc` | `bgk`/`str` | 환경/배경 설정 |

### 4.6 MST — JcMsgList Table (텍스트 데이터베이스)
**총 6개**

```
헤더: "\x0FJcMsgList Table"
인코딩: EUC-KR (한국어)
구조: ID 키 + 텍스트 값 쌍
```

| 파일 | 내용 |
|------|------|
| `msg.mst` | 게임 시스템 메시지 |
| `Dialog.mst` | NPC/이벤트 대화 |
| `item.mst` | 아이템 설명 텍스트 |
| `item_hc.mst` | HC 아이템 텍스트 |
| `rcp.mst` | 제작법(레시피) 텍스트 |
| `woa.mst` | WOA 관련 텍스트 |

### 4.7 RMM LST / RedMoon Lst File (목록 파일)
**총 272개**

```
헤더: "\x10RedMoon Lst File\x03""1.0"
ID 기반 파일 참조 목록
```

- `chr.lst`: 캐릭터 파일 목록 (`c-02146-xc-00` 형식 ID)
- `Eft.lst`: 이펙트 목록 (`fight_light`, `treecarol` 등 이름)
- `Jym.lst`: 배경음악 목록

### 4.8 PAL — PaletteHeader (팔레트)
**총 11개**

```
헤더: "\x0DPaletteHeader\x03""100"
256색 RGB 팔레트 데이터
```

- 팔레트 파일: B, C, G, H, M, M2, M3, N, R, S, x
- 맵별 색상 팔레트 교체 방식으로 추정

### 4.9 SIF — Joycity SIF (Sprite Info?)
**총 7개**

```
매직: "Joycity #$@(SIF! #!#(!# #!TS"
RLE 압축 스프라이트 정보
```

### 4.10 RMS — RIFF WAV (오디오)
**총 1,409개**

```
표준 RIFF WAV 포맷
PCM 모노 22,050Hz 또는 16-bit
```

- `W/Chr/`: 캐릭터 사운드 (601개)
- `W/Eft/`: 이펙트 사운드 (89개)  
- `W/Jym/`: BGM/지미 사운드 (273개)

### 4.11 JCW — RIFF WAV (대화/효과음)
**총 6개**

```
표준 RIFF WAV 포맷 (RMS와 동일)
명명: w0001.jcw ~ w0006.jcw
```

---

## 5. 게임 구조 추론

### 5.1 게임 장르 및 유형
- **2D 온라인 RPG** (RedMoon 엔진 계열)
- **소셜/채팅 RPG**: CefSharp + Concentus로 웹 UI + 음성채팅 내장
- **아바타 시스템**: 다양한 착용 아이템 (UBB, UBG, ULB, UYB 등 카테고리)
- **Joycity(조이시티)** 개발 → 국내 모바일/PC 게임사

### 5.2 맵 시스템
- 148개 맵, ID 체계: `Map00001` ~ `Map03003`
- 구역별 의미 추정:
  - `Map000xx`: 초기 마을/필드
  - `Map001xx`: 던전/인스턴스
  - `Map002xx`: 고레벨 구역 (62개로 가장 많음)
  - `Map03001~03003`: 특수 구역
- `M/A/` 서브디렉토리 → 맵 관련 추가 데이터

### 5.3 캐릭터/아이템 시스템
Street/C 디렉토리의 3자리 코드별 추정:

| 코드 패턴 | 추정 의미 |
|-----------|----------|
| `UBB`, `UBG`, `ULB`, `UYB` | 상의 (Body) 색상 변형 |
| `NJA`~`NJM`, `MJA`~`MJK` | NPC/몬스터 종류 |
| `HAO`, `HBB`, `HCR` 등 | 헤어스타일 (Hair) |
| `AAR`, `BAR`, `KAR`, `SAR` 등 | 무기 (Arm/Arrow/Sword) |
| `ADP`, `BDP`, `KDP` 등 | 방어구 (Defense/Pants) |
| `DNA`, `DOS` | 특수 캐릭터/이벤트 |

Street/I의 A~Z 서브디렉토리 → 알파벳별 아이템 분류 체계

### 5.4 이펙트/씬 시스템
- `J/EC0`~`J/EC9`, `J/EEE`, `J/EGO` 등 → 이펙트 카테고리
- `J/EP0`~`J/EP9` → 파티클 이펙트
- `J/EK0`~`J/EK9` → 킬/특수 이펙트
- `J/EOO`, `J/EOb` → 오브젝트 이펙트
- `S/Cef`, `S/GEF` → 씬 이펙트 (cef.spc, gef.spc)

### 5.5 네트워크/서버 구조
- CEF (Chromium) → 웹 기반 UI 서버 통신
- `debug.log`의 cert 오류 → HTTPS 서버와 통신
- `blocklist.txt`, `blocklist_chat.txt` → 채팅 필터링 파일
- `setting.ini`의 `user=1` → 유저 세션 상태 저장

### 5.6 업데이트 시스템
- `manifest.json`: 4,743개 파일의 MD5 해시 + 크기 목록
- `update.cache`: 업데이트 상태 JSON
- `Update.exe`: 자체 업데이트 실행파일

### 5.7 등급 시스템
- `etc/grade1.png` ~ `grade10.png` → 10단계 등급 뱃지

---

## 6. 파일 포맷 요약표

| 확장자 | 매직/헤더 | 용도 | 수량 |
|--------|----------|------|------|
| `.irs` / `.IRS` | `Resource File` | 스프라이트 애니메이션 컨테이너 | 2,318 |
| `.rms` | `RIFF...WAVE` | WAV 오디오 (표준) | 1,409 |
| `.lst` / `.LST` | `RedMoon Lst File` | 파일 참조 목록 | 275 |
| `.rmm` | `RedMoon MapData 1.0` | 맵 데이터 | 213 |
| `.jcr` | `Joycity #$@(RAW!...` | 스프라이트 이미지 | 199 |
| `.ils` | `Joycity #$@(RAW!...` | 이미지 팩 인덱스 | 120 |
| `.gpi` | `CSMI File 2.0` | 인벤토리 아이템 정의 | 41 |
| `.mst` | `JcMsgList Table` | 텍스트/메시지 DB (EUC-KR) | 6 |
| `.pal` | `PaletteHeader` | 색상 팔레트 | 11 |
| `.sif` | `Joycity #$@(SIF!...` | 스프라이트 정보 | 7 |
| `.gpc` | `CSMI File 2.0` | 캐릭터 스프라이트 정의 | 2 |
| `.gpj` | `CSMI File 2.0` | 조인트/파티클 정의 | 1 |
| `.gpd` | `CSMI File 2.0` | 오브젝트 배치 | 6 |
| `.cpc` | `CSMI File 2.0` | 충돌/경로 | 2 |
| `.spc` | `CSMI File 2.0` | 씬/사운드 배치 | 2 |
| `.epc` | `CSMI File 2.0` | 환경/배경 설정 | 5 |
| `.jcw` | `RIFF...WAVE` | WAV 오디오 (대화) | 6 |
| `.smm` | (RMM 변형 추정) | 서브/섀도우 맵 | 1 |

---

## 7. 모드/파생 게임 개발 전략

### 7.1 접근 가능한 부분 (쉬움)
1. **텍스트 수정** (`Res/Lst/*.mst`)
   - EUC-KR 인코딩 한국어 텍스트
   - 메시지, 아이템 설명, 대화 수정 가능
   
2. **이미지 교체** (`Res/Bus/*.png`, `etc/grade*.png`)
   - 표준 PNG → 직접 교체 가능
   
3. **오디오 교체** (`Street/W/Chr/*.rms`, `Eft/*.rms`, `Jym/*.rms`)
   - 표준 RIFF WAV → 동일 포맷으로 교체 가능
   
4. **설정 수정** (`setting.ini`)
   - 유저 설정 파일

### 7.2 중간 난이도
5. **JCR 스프라이트 디코딩**
   - 매직: `Joycity #$@(RAW!` → Joycity 엔진 문서 탐색 필요
   - RLE 또는 커스텀 압축 해제 도구 개발 필요
   
6. **RMM 맵 파싱**
   - `RedMoon MapData 1.0` → RedMoon 오픈소스 참고
   - 타일 인덱스 + 오브젝트 좌표 추출 가능
   
7. **MST 텍스트 DB 파싱**
   - 헤더 구조 분석 후 전체 텍스트 추출 가능

### 7.3 고난이도
8. **Joytalk.dll 디컴파일**
   - .NET 10.0 어셈블리 → **ILSpy** 또는 **dnSpy**로 C# 코드 복원 가능
   - 네트워크 프로토콜, 게임 로직 전체 파악 가능
   
9. **IRS 스프라이트 추출**
   - 오프셋 테이블 파싱 후 각 프레임 추출
   - 압축/암호화 여부 확인 필요
   
10. **서버 프로토콜 분석**
    - CEF 기반 → 웹소켓 또는 HTTP API
    - 네트워크 패킷 캡처로 분석 가능

### 7.4 권장 도구
| 도구 | 용도 |
|------|------|
| **ILSpy / dnSpy** | Joytalk.dll C# 디컴파일 |
| **010 Editor** | 바이너리 파일 구조 분석 |
| **Fiddler / Wireshark** | 네트워크 프로토콜 분석 |
| **HxD** | 헥스 편집기 |
| **Python (struct)** | 파일 포맷 파서 개발 |
| **FFmpeg** | RMS/JCW WAV 변환 |

---

## 8. 핵심 발견 사항

1. **RedMoon 엔진 기반**: 맵(`RedMoon MapData`) + 리스트(`RedMoon Lst File`) 포맷이 레드문 계열 엔진임을 확인
2. **Joycity 독자 포맷**: 스프라이트(JCR/ILS)는 조이시티 고유 포맷
3. **CSMI File 2.0**: 다양한 확장자(gpi/gpc/gpj 등)가 동일 컨테이너 포맷 사용
4. **.NET 10.0**: 최신 .NET 사용 → ILSpy로 디컴파일 시 거의 완전한 C# 소스 복원 가능
5. **온라인 게임**: 서버 의존적, 로컬 단독 실행 불가 (채팅/음성 서버 필요)
6. **총 ~1.5GB 에셋**: manifest.json 기준 4,743개 파일
