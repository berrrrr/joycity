# JoyTalk 리버스엔지니어링 계획서

> 작성일: 2026-04-19  
> 기반: joytalk_analysis.md 분석 결과  
> 목표: 파생 게임/모드 제작을 위한 게임 구조 완전 파악

---

## 전체 로드맵 요약

```
Phase 1 (1주) ─── .NET 코드 디컴파일 ──→ 게임 로직 완전 이해
Phase 2 (2주) ─── 파일 포맷 파서 개발 ──→ 에셋 추출 가능
Phase 3 (1주) ─── 네트워크 프로토콜 분석 ──→ 서버 통신 이해
Phase 4 (2주) ─── 에셋 에디터 개발 ──→ 모드 적용 가능
Phase 5 (∞)  ─── 파생 게임 제작 ──→ 독자 게임 완성
```

---

## Phase 1: .NET 어셈블리 디컴파일 (최우선, 가장 가치 높음)

### 1.1 준비물 설치

```bash
# macOS에서 Windows 바이너리 분석 도구
brew install --cask dotpeek       # JetBrains dotPeek (무료)

# 또는 Windows VM에서
# - ILSpy (https://github.com/icsharpcode/ILSpy) - 최고 추천
# - dnSpy (https://github.com/dnSpy/dnSpy) - 디버깅 가능
# - dotPeek (JetBrains)

# Wine 환경에서 직접 실행도 가능
# 대상 파일:
# /Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Joytalk.dll
```

### 1.2 디컴파일 대상 파일

| 파일 | 크기 추정 | 기대 내용 |
|------|----------|----------|
| `Joytalk.dll` | 메인 | 전체 게임 로직, 네트워크, UI |
| `Update.dll` | 서브 | 업데이트 시스템 |

### 1.3 ILSpy로 분석할 핵심 네임스페이스

.NET 10.0이므로 ILSpy 최신 버전(9.x) 필요. 확인할 것:

```
찾아야 할 클래스/네임스페이스:
├── Network.*         → 서버 통신 프로토콜
├── Map.*             → RMM 맵 로더
├── Sprite.* / Render.* → IRS/JCR 이미지 로더
├── Audio.*           → RMS/JCW/MP3 재생
├── Item.*            → 아이템 시스템
├── Character.*       → 캐릭터 시스템
├── Chat.*            → CefSharp 채팅 통합
├── Voice.*           → Concentus 음성채팅
└── Update.*          → 업데이트 시스템
```

### 1.4 핵심 파악 목표

- [ ] **네트워크 서버 주소** (harcoded URL, config에서 읽는 방식)
- [ ] **패킷 구조** (헤더 포맷, 암호화 여부)
- [ ] **IRS 파일 로더 코드** → 직접 파서 작성 기반
- [ ] **JCR 파일 로더 코드** → 압축 알고리즘 파악
- [ ] **MST 파서 코드** → 이미 Python으로 일부 분석됨
- [ ] **맵 로더 코드** → RMM 타일 구조

---

## Phase 2: 파일 포맷 파서 개발

### 2.1 MST 텍스트 DB 파서 (즉시 가능 ✅)

**이미 구조 파악 완료.** Python으로 전체 텍스트 추출 가능.

```python
# mst_parser.py - 구현 가이드
import struct, re

def parse_mst(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    # Header: 0F + "JcMsgList Table" (16 bytes total)
    header_len = data[0]
    header = data[1:1+header_len]  # b'JcMsgList Table'
    
    pos = 1 + header_len  # = 16
    count = struct.unpack_from('<I', data, pos)[0]  # 레코드 수
    pos += 6  # count(4) + 2 padding
    
    entries = {}
    raw = data.decode('latin-1')
    id_matches = list(re.finditer(r'\d{5}_\d', raw))
    
    for m in id_matches:
        id_pos = m.start()
        key = m.group()
        after_key = id_pos + len(key)
        
        # ff ff 01 00 [type_len] [type_string] [size:4] [offset:4] [text]
        skip = after_key + 4
        type_len = data[skip]
        type_str = data[skip+1:skip+1+type_len].decode('ascii', errors='replace')
        after_type = skip + 1 + type_len
        
        size = struct.unpack_from('<I', data, after_type)[0]
        text_pos = after_type + 8
        text_bytes = data[text_pos:text_pos + min(size, 500)]
        text = text_bytes.decode('euc-kr', errors='replace')
        
        entries[key] = {
            'type': type_str.strip(),
            'text': text.split(';')  # ';' 구분자로 분리됨
        }
    
    return entries

# 결과 예시:
# {'00109_0': {'type': 'CItemTextList', 'text': ['줄리엣시티', '이 곳을 지나면...']}}
# {'00081_0': {'text': ['카페라떼', '마음과 몸이 지쳤을 때...']}}
```

**6개 MST 파일 전체 추출 시 텍스트 데이터베이스 완성:**
- `item.mst` → 아이템 이름/설명 (1,376개)
- `msg.mst` → 시스템 메시지
- `Dialog.mst` → NPC 대화
- `rcp.mst` → 제작 레시피
- `woa.mst` → WOA 관련 텍스트

### 2.2 IRS 스프라이트 컨테이너 파서

**구조 파악 완료, 내부 데이터 디코딩은 Phase 1 후 가능.**

```python
# irs_parser.py - 구조
import struct

def parse_irs_header(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    # Header
    assert data[:14] == b'Resource File\x00'
    version = struct.unpack_from('<H', data, 14)[0]   # = 2
    # data[16:18] = padding (00 00)
    count = struct.unpack_from('<I', data, 18)[0]     # 프레임 수
    # data[22:26] = 00 00 00 00 (unknown)
    
    # Offset table: count * 4 bytes, starting at offset 22
    base = 22
    offsets = [struct.unpack_from('<I', data, base + i*4)[0] for i in range(count)]
    
    data_start = base + count * 4
    
    frames = []
    for i in range(count - 1):
        frame_start = data_start + offsets[i]
        frame_end = data_start + offsets[i+1]
        frames.append(data[frame_start:frame_end])
    
    return frames
    
# 내부 프레임 포맷은 ILSpy로 파악 후 추가 구현 필요
# 현재 알 수 없는 압축 포맷으로 인코딩됨
```

### 2.3 RMM 맵 파서

```python
# rmm_parser.py - 구조
import struct

def parse_rmm(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    # Header: "RedMoon MapData 1.0\0" = 20 bytes
    assert data[:20] == b'\x13RedMoon MapData 1.0\x00' or \
           data[:19] == b'RedMoon MapData 1.0'
    
    # 이후 구조는 ILSpy 디컴파일로 확인 필요
    # 추정:
    # - 맵 크기 (width, height)
    # - 타일 인덱스 배열
    # - 오브젝트 배치 정보
    # - NPC/몬스터 스폰 정보
    pass
```

### 2.4 JCR 스프라이트 파서

```python
# jcr_parser.py - 구조
# 매직: b'Joycity #$@(RAW! #!#(!# #!TS'
# 조이시티 고유 압축 포맷
# ILSpy로 JCR 로더 클래스 찾아 알고리즘 복제 필요

# 참고: Joycity 계열 게임(버블파이터, 조이시티 RPG 등)
# 커뮤니티에서 역공학 시도 기록 탐색 추천
```

### 2.5 CSMI File 2.0 파서

여러 확장자가 공통 포맷 사용 (gpi, gpc, gpj, gpd, cpc, spc, epc):

```python
# csmi_parser.py
import struct

def parse_csmi(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    # Header
    obj_count = struct.unpack_from('<I', data, 0)[0]
    magic_len = data[4]
    magic = data[5:5+magic_len]  # b'CSMI File 2.0'
    
    version_major = struct.unpack_from('<I', data, 5+magic_len)[0]
    
    # 3바이트 타입 코드 (e.g. 'ubb', 'str', 'efl')
    type_code_pos = 5 + magic_len + 16  # 추정
    type_code = data[type_code_pos:type_code_pos+3].decode('ascii', errors='?')
    
    # 오브젝트 데이터: 위치(x,y,z), 크기, 변환행렬 포함
    # 변환행렬: "0 9 9 7 7 7 8 9 9 0" 형태의 텍스트 필드 존재
    
    return {'type': type_code, 'count': obj_count}
```

### 2.6 PAL 팔레트 파서 (즉시 가능 ✅)

```python
# pal_parser.py
import struct

def parse_pal(filepath):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    # Header: 0D + "PaletteHeader" + 03 + "100"
    header_len = data[0]  # 0D = 13
    header = data[1:1+header_len]  # b'PaletteHeader'
    ver_len = data[1+header_len]
    ver = data[2+header_len:2+header_len+ver_len]  # b'100'
    
    # 팔레트 데이터: RGB triplets
    palette_start = 2 + header_len + ver_len
    palette = []
    pos = palette_start
    while pos + 3 <= len(data):
        r, g, b = data[pos], data[pos+1], data[pos+2]
        palette.append((r, g, b))
        pos += 3
    
    return palette  # 최대 256색
```

---

## Phase 3: 네트워크 프로토콜 분석

### 3.1 CEF 기반 웹 통신 분석

게임 UI와 일부 통신이 CefSharp(Chromium) 기반이므로:

```bash
# 방법 1: Wireshark로 실시간 캡처
# - JoyTalk 실행 중 HTTPS 트래픽 캡처
# - 필터: host joytalk.joycity.com (또는 실제 서버 도메인)

# 방법 2: mitmproxy로 HTTPS 중간자 분석
pip install mitmproxy
mitmproxy --mode transparent -p 8080
# → 모든 HTTP/WebSocket 요청 내용 확인 가능

# 방법 3: ILSpy로 Network 클래스 찾기 (Phase 1과 연계)
# Joytalk.dll → 네트워크 클래스 → 엔드포인트 URL 추출
```

### 3.2 음성 채팅 프로토콜 (Concentus/Opus)

```
Concentus 2.2.2 = Opus 코덱 C# 구현
→ WebRTC 또는 UDP 기반 음성 스트리밍 추정
→ Wireshark로 UDP 트래픽 분석 필요
```

### 3.3 게임 서버 프로토콜

```
분석 목표:
├── 서버 주소/포트
├── 패킷 헤더 구조 (길이, 타입, 시퀀스)
├── 암호화 여부 (AES, XOR, 또는 평문)
├── 로그인 패킷 구조
├── 캐릭터 이동 패킷
└── 채팅 패킷
```

---

## Phase 4: 에셋 에디터 & 모드 도구 개발

### 4.1 텍스트 에디터 (Phase 2.1 완료 후 바로 가능)

```python
# mst_editor.py
# 기능:
# 1. MST 파싱 → JSON/CSV 출력
# 2. JSON/CSV 편집
# 3. 수정된 내용 MST로 재패킹
# 4. 한국어 외 언어 번역 지원

# 활용: 아이템 설명 변경, 시스템 메시지 수정, 언어 현지화
```

### 4.2 오디오 교체 도구 (즉시 가능 ✅)

```bash
# RMS/JCW는 표준 RIFF WAV → FFmpeg으로 변환 후 교체
ffmpeg -i original.mp3 -ar 22050 -ac 1 -f wav replacement.rms

# BGM은 이미 MP3 → 직접 교체 가능
# Street/W/Bks/b-000.mp3 ~ b-NNN.mp3 (72개)
```

### 4.3 이미지 교체 도구

```bash
# PNG 직접 교체 (즉시 가능):
# - Res/Bus/*.png (버스/UI 이미지)
# - etc/grade*.png (등급 뱃지)

# JCR 교체 (Phase 1+2 후):
# 1. JCR → BMP/PNG 추출
# 2. 이미지 수정
# 3. BMP/PNG → JCR 재패킹
```

### 4.4 맵 에디터 (Phase 1+2 후)

```
기능 목표:
├── RMM 파싱 → 타일 맵 시각화
├── 타일 배치 편집
├── NPC/오브젝트 배치
└── 수정된 맵 RMM 저장
```

### 4.5 스프라이트 뷰어 (Phase 1+2 후)

```
기능 목표:
├── IRS 파싱 → 프레임 시퀀스 추출
├── 애니메이션 프리뷰
├── 개별 프레임 PNG 추출
└── 새 스프라이트 IRS 패킹
```

---

## Phase 5: 파생 게임/모드 제작

### 5.1 모드 제작 접근법

**Option A: 에셋 교체 모드 (가장 쉬움)**
- 텍스트, 이미지, 오디오만 교체
- 게임 로직은 그대로
- Phase 2.1 + 4.2 완료 후 즉시 가능

**Option B: 서버 에뮬레이터 (중간)**
- Phase 3 완료 후 가능
- 오프라인 플레이 가능하게 만들기
- 네트워크 프로토콜 → 로컬 서버 구현 (Node.js/Python)

**Option C: 독자 엔진 재구현 (최고 난이도)**
- Phase 1~3 완료 후 가능
- .NET 10 / Unity / Godot으로 동일 게임플레이 재구현
- 모든 에셋 추출 후 새 엔진에 임포트

### 5.2 파생 게임 아이디어 (에셋 활용)

```
아이디어 1: 오프라인 싱글플레이어 버전
  - 서버 에뮬레이터 + 기존 맵/캐릭터/이야기 재활용
  
아이디어 2: 팬 서버 (프라이빗 서버)
  - 서버 프로토콜 파악 → 오픈소스 서버 구현
  
아이디어 3: 크로스플랫폼 리메이크
  - Godot 4 + 추출한 에셋으로 macOS/Linux/모바일 지원
  
아이디어 4: 맵 에디터로 새 콘텐츠
  - 기존 엔진 유지 + 새 맵/이벤트 추가
```

---

## 즉시 실행 가능한 작업 목록

### 지금 당장 가능 (도구 추가 설치 없이)

| 우선순위 | 작업 | 예상 시간 |
|---------|------|---------|
| ★★★ | `mst_parser.py` 작성 → 전체 텍스트 DB 추출 | 1시간 |
| ★★★ | `pal_parser.py` 작성 → 팔레트 추출/시각화 | 30분 |
| ★★ | BGM MP3 카탈로그 작성 (72개) | 30분 |
| ★★ | RMS WAV 파일 카탈로그 (1,409개) | 30분 |
| ★ | IRS 헤더 파서 작성 (프레임 수/오프셋) | 1시간 |

### ILSpy 설치 후 가능 (Windows VM 필요)

| 우선순위 | 작업 | 예상 시간 |
|---------|------|---------|
| ★★★ | `Joytalk.dll` 전체 클래스 구조 파악 | 2~4시간 |
| ★★★ | IRS/JCR 로더 코드 추출 | 4~8시간 |
| ★★★ | 네트워크 서버 주소/프로토콜 파악 | 2~4시간 |
| ★★ | RMM 맵 로더 코드 추출 | 2~4시간 |
| ★★ | MST 파서 코드 확인 (Python 파서 검증) | 1시간 |

### 중기 목표 (1~2주)

| 우선순위 | 작업 |
|---------|------|
| ★★★ | 완전한 파일 포맷 파서 라이브러리 완성 |
| ★★★ | IRS 스프라이트 → PNG 시퀀스 추출 도구 |
| ★★ | 네트워크 패킷 캡처 및 분석 |
| ★★ | 맵 뷰어 (RMM → 이미지 렌더링) |
| ★ | 서버 에뮬레이터 프로토타입 |

---

## 도구 설치 가이드

### 필수 도구

```bash
# macOS 기본 설치
brew install python3
pip3 install Pillow numpy  # 이미지 처리

# Windows VM 또는 Wine에서 ILSpy
# https://github.com/icsharpcode/ILSpy/releases
# → ILSpy.exe (최신 9.x 버전, .NET 10 지원 확인)

# Wireshark (네트워크 분석)
brew install --cask wireshark

# mitmproxy (HTTPS 분석)
pip3 install mitmproxy

# 010 Editor (바이너리 분석, 유료지만 강력)
# https://www.sweetscape.com/010editor/
```

### 권장 파일 작업 환경

```
프로젝트 폴더 구조 제안:
joytalk-re/
├── parsers/           # 파일 포맷 파서
│   ├── mst_parser.py
│   ├── irs_parser.py
│   ├── jcr_parser.py
│   ├── rmm_parser.py
│   └── csmi_parser.py
├── extracted/         # 추출된 에셋
│   ├── texts/         # MST → JSON
│   ├── sprites/       # IRS → PNG
│   ├── maps/          # RMM → 이미지
│   └── audio/         # RMS → WAV
├── tools/             # 에디터/모드 도구
│   ├── mst_editor.py
│   ├── sprite_viewer.py
│   └── map_viewer.py
└── docs/              # 분석 문서
    ├── file_formats/  # 포맷별 상세 문서
    └── network/       # 프로토콜 분석
```

---

## 법적/윤리적 고려사항

- **개인 용도**: 리버스엔지니어링은 개인 연구/학습 목적에서 대부분 국가에서 허용
- **파생 게임 배포**: 에셋(스프라이트/텍스트/오디오)을 그대로 사용해 배포하면 저작권 침해
- **재구현**: 게임플레이 메커니즘/아이디어를 참고해 **직접 제작한 새 에셋으로** 게임 만들기는 허용
- **프라이빗 서버**: 개인/소규모 커뮤니티 용도는 그레이존, 상업적 운영은 불가
- **모드 배포**: 조이시티 측 정책 확인 필요

---

## 참고 자료

- [ILSpy GitHub](https://github.com/icsharpcode/ILSpy) - .NET 디컴파일러
- [RedMoon 엔진 관련 커뮤니티](https://ragezone.com) - 유사 게임 역공학 사례
- [010 Editor Binary Templates](https://www.sweetscape.com/010editor/templates/) - 바이너리 템플릿
- Joycity 계열 게임 포럼 검색: "Joycity file format", "JCR sprite format"
- `.NET 10 IL` 코드 참고: Microsoft dotnet/runtime GitHub
