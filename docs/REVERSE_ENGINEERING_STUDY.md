# JoyTalk 리버스 엔지니어링 공부 노트

> 이 문서는 JoyTalk (한국 MMO 게임, .NET 10.0 C#, Wine/Wineskin macOS 래핑)를  
> 처음부터 완전히 분석한 과정을 기술로 정리한 학습 자료입니다.

---

## 목차

1. [리버스 엔지니어링이란](#1-리버스-엔지니어링이란)
2. [분석 대상 파악](#2-분석-대상-파악)
3. [Phase 1 — 코드 복원 (DLL 디컴파일)](#3-phase-1--코드-복원-dll-디컴파일)
4. [Phase 2 — 바이너리 파일 포맷 분석](#4-phase-2--바이너리-파일-포맷-분석)
5. [Phase 3 — 네트워크 프로토콜 분석](#5-phase-3--네트워크-프로토콜-분석)
6. [핵심 기술 정리](#6-핵심-기술-정리)
7. [도구 사용법 요약](#7-도구-사용법-요약)
8. [공통 패턴과 교훈](#8-공통-패턴과-교훈)
9. [더 공부할 것들](#9-더-공부할-것들)

---

## 1. 리버스 엔지니어링이란

소프트웨어를 **소스코드 없이** 분석해서 동작 방식을 이해하는 기술.  
크게 세 영역으로 나뉨:

```
┌─────────────────────────────────────────────────────┐
│  리버스 엔지니어링 영역                              │
│                                                     │
│  1. 코드 복원     실행 파일 → 소스코드에 가까운 형태  │
│  2. 데이터 분석   바이너리 파일 → 구조 파악           │
│  3. 프로토콜 분석 네트워크 패킷 → 통신 규격 파악      │
└─────────────────────────────────────────────────────┘
```

이번 JoyTalk 분석은 세 가지를 순서대로 전부 했음.

### 왜 하는가?

| 목적 | 예시 |
|------|------|
| 보안 연구 | 취약점 발견, 악성코드 분석 |
| 상호운용성 | 비공개 프로토콜로 클라이언트 구현 |
| 게임 분석 | 봇, 에뮬레이터 서버 제작 |
| 포렌식 | 사고 원인 분석 |
| 학습 | 잘 만들어진 코드 구조 이해 |

---

## 2. 분석 대상 파악

### 2-1. 앱 구조 파악부터

리버스 엔지니어링의 첫 단계는 **무엇을 분석할지** 파악하는 것.

```bash
# macOS .app 번들 내부 탐색
ls /Applications/JoyTalk.app/Contents/
#  MacOS/          ← 실행 파일 (Wineskin 래퍼)
#  SharedSupport/  ← Wine prefix (Windows 환경)
#  Resources/      ← 아이콘 등

# Wine prefix 안의 실제 Windows 실행 파일
ls /Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/
#  JoyTalk.exe
#  JoyTalk.dll
#  Res/            ← 게임 리소스
```

**발견한 것:**
- macOS 앱이지만 내부는 **Wine**으로 실행되는 Windows 프로그램
- 실제 게임은 **C# .NET 10.0** (관리형 코드 = 역컴파일 가능)
- DXVK + MoltenVK로 DirectX → Metal 변환

### 2-2. 기술 스택 파악

```bash
# .NET 어셈블리 여부 확인
file JoyTalk.exe
# PE32 executable... Mono/.Net assembly

# 어셈블리 메타데이터 확인
strings JoyTalk.dll | grep -i "framework\|runtime\|dotnet"
```

**핵심 인사이트:** 네이티브 C/C++ 바이너리는 어셈블리 수준으로 분석해야 하지만,  
**.NET/Java/Python 같은 관리형 언어는 원본 코드에 가깝게 역컴파일 가능**.

---

## 3. Phase 1 — 코드 복원 (DLL 디컴파일)

### 3-1. 역컴파일 (Decompilation)

**컴파일 과정:**
```
C# 소스코드 → 컴파일 → IL(중간언어) → 런타임에 JIT 컴파일 → 네이티브 코드
```

.NET 실행 파일은 **IL(Intermediate Language)** 바이트코드를 포함하고 있어서  
`ilspycmd` 같은 도구로 C#에 가깝게 복원 가능.

```bash
# ilspycmd 설치
dotnet tool install ilspycmd -g

# DLL 역컴파일
ilspycmd JoyTalk.dll -o ./decompiled/

# 결과: 65,597줄의 C# 코드 (decompiled/-/-.cs)
```

### 3-2. 난독화 (Obfuscation)

역컴파일했더니 모든 클래스/메서드명이 `_2047`, `_2051`, `_00A0` 같은 이름.  
이게 **난독화(Obfuscation)** — 코드를 읽기 어렵게 만드는 기법.

```csharp
// 난독화 전 (원본 추정)
public class NetworkManager {
    public async Task SendChatMessage(string text) { ... }
}

// 난독화 후 (실제 코드)
public class _2047 {
    public async Task _1680(string _00A0) { ... }
}
```

**이 프로젝트의 난독화 방식: 유니코드 보이지 않는 문자**

```
클래스명 _2047 → 실제로는 Unicode 보이지 않는 문자들로 구성
```

### 3-3. 문자열 암호화 분석

게임 내 문자열(URL, 패킷 타입명 등)이 그대로 노출되면 분석이 쉬워지므로  
개발자가 **문자열을 암호화해서 바이트 배열**로 저장.

**암호화된 저장 구조:**

```csharp
// 암호화된 바이트 블롭 (42,797 bytes)
internal static byte[] _4 = new byte[42797] {
    194, 223, 220, 217, 221, ...  // 암호화된 데이터
};

// 캐시 배열
internal static string[] _5 = new string[2698];

// 복호화 함수
private static string _6(int idx, int offset, int length) {
    string text = Encoding.UTF8.GetString(_4, offset, length);
    _5[idx] = text;  // 캐시에 저장
    return text;
}

// 각 문자열 접근자
public static string _2003_2057() {
    return _5[N] ?? _6(N, 234, 4);  // "chat"
}
```

**분석 방법 — XOR 패턴 발견:**

암호화된 바이트를 봤을 때 패턴을 찾아야 함.

```python
# 복호화 전
blob[0] = 0xDF  # 223
blob[1] = 0xDC  # 220
blob[2] = 0xD9  # 217

# XOR with position ^ 0xAA 시도
blob[0] ^ 0 ^ 0xAA = 0xDF ^ 0xAA = 0x75 = 'u'  ← URL의 'u'!
blob[1] ^ 1 ^ 0xAA = 0xDC ^ 0xAB = 0x77 = 'v'
blob[2] ^ 2 ^ 0xAA = 0xD9 ^ 0xA8 = 0x71 = 'q'  ← 아니네...

# 다시 시도: position ^ 0xAA 만
blob[0] ^ 0xAA = 0x75 = 'u'
blob[1] ^ 0xAA = 0x76 = 'v'  ← 'uv'? ...
```

실제로는 Python으로 여러 XOR 키 조합을 시도해서 읽을 수 있는 문자열이 나오는 것을 찾음.

```python
# 최종 발견된 XOR 알고리즘
def decrypt(blob: bytes) -> bytes:
    return bytes(b ^ p ^ 0xAA for p, b in enumerate(blob))

# 검증: offset=0, length=52의 결과
decrypted = decrypt(blob_raw)
print(decrypted[0:52].decode('utf-8'))
# → 'https://jc.joy-june.com/joytalk/update/manifest.json' ✓
```

**XOR 암호화의 특성:**
```
암호화: plaintext[i] XOR key[i]  → ciphertext[i]
복호화: ciphertext[i] XOR key[i] → plaintext[i]
같은 연산! 대칭 암호화.

key = position ^ 0xAA
→ key[0] = 0^0xAA = 0xAA
→ key[1] = 1^0xAA = 0xAB
→ key[2] = 2^0xAA = 0xA8
→ ...
```

### 3-4. 전체 문자열 일괄 복호화

구조를 이해했으니 2698개 문자열 전체를 한 번에 복호화:

```python
# 모든 접근자 메서드 파싱
pattern = re.compile(
    r'public static string (_[\w]+)\(\)\s*\{.*?_6\((\d+),\s*(\d+),\s*(\d+)\)',
    re.MULTILINE
)
for match in pattern.finditer(cs_code):
    method_name = match.group(1)   # 예: _2003_2057
    offset      = int(match.group(3))
    length      = int(match.group(4))
    decrypted   = get_string(offset, length)
    method_map[method_name] = decrypted
    # _2003_2057 → "chat"
```

---

## 4. Phase 2 — 바이너리 파일 포맷 분석

게임 리소스 파일들(맵, 스프라이트, 아이템DB)의 구조를 파악하는 단계.

### 4-1. 접근 방법

바이너리 파일 분석의 기본 도구:

```bash
# 파일 타입 확인
file Tile00036.irs

# 헥스 에디터로 처음 부분 확인
xxd Tile00036.irs | head -20
# 00000000: 5265 736f 7572 6365 2046 696c 6500 ...  Resource File.

# 문자열 추출
strings Tile00036.irs
```

**헥스 덤프 읽는 법:**
```
주소      16진수 바이트                          ASCII
00000000  52 65 73 6f 75 72 63 65  20 46 69 6c  Resource Fil
0000000c  65 00 00 00 00 06 00 00  00 00 00 00  e...........
```

### 4-2. 매직 바이트 (Magic Bytes)

대부분의 파일 포맷은 첫 몇 바이트로 타입을 식별할 수 있음.

| 포맷 | 매직 바이트 | ASCII |
|------|------------|-------|
| PNG | `89 50 4E 47` | `.PNG` |
| JPEG | `FF D8 FF` | |
| ZIP | `50 4B 03 04` | `PK..` |
| IRS | `52 65 73 6f...` | `Resource File\0` |
| JCR | `4A 6F 79 63...` | `Joycity #$@(RAW!...` |
| RMM | `\x12RedMoon MapData 1.0` | |

역컴파일한 C# 코드에서 매직 바이트 검사 코드를 찾으면 포맷 파악에 도움:

```csharp
// 코드에서 찾은 매직 바이트 검사
if (data[0] != 0x52 || data[1] != 0x65 ...) // "Resource File"
    throw new InvalidDataException("Not an IRS file");
```

### 4-3. 구조체 파싱 패턴

바이너리 파일은 보통 고정 헤더 + 반복 레코드 구조:

```
[헤더]
  [매직 바이트]
  [버전]
  [데이터 개수 N]

[데이터 N개]
  [레코드 1]
  [레코드 2]
  ...
```

Python으로 파싱:

```python
import struct

with open('file.bin', 'rb') as f:
    data = f.read()

pos = 0

# u32 읽기 (리틀 엔디언)
value = struct.unpack_from('<I', data, pos)[0]
pos += 4

# u16 읽기
value = struct.unpack_from('<H', data, pos)[0]
pos += 2

# 문자열 읽기 (Pascal 스타일: 길이 1바이트 + 내용)
length = data[pos]; pos += 1
text = data[pos:pos+length].decode('utf-8'); pos += length
```

**리틀 엔디언 vs 빅 엔디언:**
```
값 0x12345678을 메모리에 저장:

리틀 엔디언: 78 56 34 12  (낮은 바이트가 앞)  ← x86, .NET 기본값
빅 엔디언:   12 34 56 78  (높은 바이트가 앞)  ← 네트워크 표준
```

### 4-4. RLE (Run-Length Encoding)

JCR, IRS 포맷에서 스프라이트 픽셀을 압축하는 방식.

```
원본: A A A A A B C C C C
RLE: 5×A 1×B 4×C  → 공간 절약

JCR RLE:
  FF FE [idx] [count_u16]  ← 5바이트: count번 반복
  [idx]                    ← 1바이트: 1번만
```

```python
while pos < end:
    if data[pos] == 0xFF and data[pos+1] == 0xFE:
        idx   = data[pos+2]
        count = struct.unpack_from('<H', data, pos+3)[0]
        pos += 5
    else:
        idx   = data[pos]
        count = 1
        pos += 1

    # count 픽셀 채우기
    for _ in range(count):
        pixels[pixel_pos] = palette[idx]
        pixel_pos += 1
```

### 4-5. 팔레트 (Palette) 방식

스프라이트가 직접 RGB를 저장하지 않고 팔레트 인덱스만 저장하는 이유:

```
직접 방식: 각 픽셀에 RGB 3바이트 = 100×100 = 30,000 바이트
팔레트 방식:
  - 팔레트: 256색 × 3바이트 = 768 바이트 (1회)
  - 픽셀: 각 1바이트 인덱스 = 100×100 = 10,000 바이트
  → 총 10,768 바이트 (66% 절약!)
```

### 4-6. 발견한 5가지 포맷 요약

| 파일 | 포맷명 | 주요 특징 |
|------|--------|----------|
| `.rmm` | RedMoon MapData 1.0 | 타일 그리드, 비트 필드 인코딩, EUC-KR 지역명 |
| `.irs` | Resource File | 팔레트 인덱스, cmd 스트림(0=끝,1=픽셀,2=스킵,3=줄바꿈) |
| `.jcr` | Joycity RAW | RLE 압축, 인라인 팔레트, 특수 센티넬(57,93,197) |
| `.mst` | JcMsgList Table | 패턴 스캔 방식, EUC-KR 텍스트, 세미콜론 구분자 |
| `.gpd` | CSMI File 2.0 | Pascal 문자열(0xFF=u16 확장), 레이어/스프라이트 트리 |

---

## 5. Phase 3 — 네트워크 프로토콜 분석

### 5-1. 네트워크 분석 접근법

**정적 분석 (코드에서 찾기):**
- 역컴파일한 코드에서 TCP/UDP 소켓 생성 코드 찾기
- `TcpClient`, `UdpClient`, `NetworkStream` 검색
- 포트 번호, 호스트 이름 검색

**동적 분석 (실행 중 캡처):**
- Wireshark로 패킷 캡처
- 프록시로 중간에서 관찰
- 디버거 어태치

이번 JoyTalk 분석은 **정적 분석**만으로 완전히 파악.

### 5-2. 코드에서 네트워크 구조 찾기

```csharp
// 찾은 코드 (역컴파일)
await client.ConnectAsync("jc.joy-june.com", 7945);
NetworkStream stream = client.GetStream();

// 수신 루프
while (true) {
    byte[] header = new byte[4];
    await stream.ReadExactlyAsync(header);
    int length = BinaryPrimitives.ReadInt32LittleEndian(header);
    byte[] payload = new byte[length];
    await stream.ReadExactlyAsync(payload);
    // payload 처리...
}
```

**발견된 프레임 구조:**
```
┌────────────┬─────────────────────────────────────┐
│  u32 length│  payload (length bytes)              │
└────────────┴─────────────────────────────────────┘
```

### 5-3. 디스패처 패턴

많은 네트워크 프로토콜이 "타입 필드로 핸들러를 선택하는" 디스패처 패턴을 씀:

```csharp
// 찾은 코드
Dictionary<string, Func<JsonElement, Task>> handlers;

public static async Task HandlePacket(string json) {
    JsonElement root = JsonDocument.Parse(json).RootElement;
    string type = root.GetProperty("type").GetString();

    if (handlers.TryGetValue(type, out var handler))
        await handler(root);
}
```

이 딕셔너리의 키들이 암호화된 문자열 접근자로 초기화됨:

```csharp
handlers = new Dictionary<string, Func<JsonElement, Task>> {
    { _2003_2057(), _00A0 },   // "chat" → chat handler
    { _2007_2027(), _1680 },   // "typing" → typing handler
    // ... 131개
};
```

Phase 1에서 복호화한 `method_map`으로 전부 해독 가능:
```python
# _2003_2057 → "chat"
# → { "chat": chat_handler }
```

### 5-4. 프로토콜 완전 해독

**최종 발견된 아키텍처:**

```
포트 7942/7945: TCP 게임 프로토콜
  - 외부 프레임: [u32 length][payload]
  - payload type byte:
      1 → JSON: [u8=1][i16 len][UTF-8 JSON \n]
      3 → keepalive
      5 → 바이너리: [u8=5][u16 seq][u8 name_len][name][data]
      6 → 음성 제어

포트 7946: UDP
  - Opus 코덱, 48kHz, mono
  - 음성 채팅
```

**JSON 패킷 예시:**
```json
// 클라이언트 → 서버 (로그인)
{"type":"login","version":"2.1.0","userid":"user123","userpw":"pass456"}

// 서버 → 클라이언트 (게임 오브젝트 동기화)
{"type":"obj","gameObjects":{"1001":{"no":1001,"name":"플레이어A","type":"user","OX":450,"OY":320}}}

// 클라이언트 → 서버 (이동)
{"type":"move","no":"1001","TX":"500","TY":"350"}
```

### 5-5. 투명 프록시 구현

분석한 프로토콜을 검증하는 가장 좋은 방법 — 실제 트래픽을 관찰:

```python
async def relay(reader, writer, direction, tracker):
    while True:
        # 4바이트 헤더 읽기
        header = await reader.readexactly(4)
        length = struct.unpack_from('<I', header)[0]

        # payload 읽기
        payload = await reader.readexactly(length)

        # 분석 (S→C만)
        if direction == 'S→C':
            parsed = parse_frame(payload)
            if parsed['type_byte'] == 1:
                pkt = parsed['json']
                tracker.process_packet(pkt)  # 아이템 감지!

        # 원본 그대로 포워드
        writer.write(header + payload)
        await writer.drain()
```

**/etc/hosts를 이용한 리다이렉트:**
```
# /etc/hosts에 추가
127.0.0.1 jc.joy-june.com

# 동작 원리:
# 게임 클라이언트가 jc.joy-june.com 접속 시도
# OS가 DNS 대신 /etc/hosts 먼저 확인
# → 127.0.0.1 (로컬 프록시)로 연결
# 프록시가 실서버로 중계
```

---

## 6. 핵심 기술 정리

### 6-1. XOR 암호화

```
성질:
  A XOR B = C
  C XOR B = A  ← 같은 연산으로 복호화!

Rolling XOR (위치 기반):
  ciphertext[i] = plaintext[i] XOR (i XOR 0xAA)
  plaintext[i]  = ciphertext[i] XOR (i XOR 0xAA)  ← 동일

분석법:
  1. 이미 알고 있는 문자열이 있으면 XOR로 키 역산
  2. 시작 부분에 URL이 있을 것 같으면 'h','t','t','p' XOR 시도
  3. Python으로 여러 키 패턴 브루트포스
```

```python
# 키 역산 예시
# blob[0] = 0xDF, 예상값 = 'h' = 0x68
key = 0xDF ^ 0x68  # = 0xB7
# blob[1] = 0xDC, 예상값 = 't' = 0x74
key2 = 0xDC ^ 0x74  # = 0xA8

# 키가 일정 패턴이면? key[i] = i ^ 0xAA?
# key[0] = 0^0xAA = 0xAA ≠ 0xB7 → 아니야
# 다시... key[i] = i XOR C 아닌 다른 패턴?
# 실제 방법: 브루트포스로 찾거나 코드에서 복호화 루틴 찾기
```

### 6-2. 바이너리 파싱 (struct 모듈)

```python
import struct

data = b'\x01\x00\x02\x00\x03\x00'

# 포맷 문자:
# < = 리틀 엔디언
# > = 빅 엔디언
# B = u8  (1바이트)
# H = u16 (2바이트)
# I = u32 (4바이트)
# i = i32 (4바이트 부호있음)
# s = bytes

a = struct.unpack_from('<H', data, 0)[0]  # = 1  (offset=0, u16)
b = struct.unpack_from('<H', data, 2)[0]  # = 2  (offset=2, u16)
c = struct.unpack_from('<H', data, 4)[0]  # = 3  (offset=4, u16)

# 여러 값 한번에
a, b, c = struct.unpack_from('<3H', data, 0)  # = (1, 2, 3)
```

### 6-3. asyncio TCP 서버/클라이언트

```python
import asyncio, struct

# 서버
async def handle_client(reader, writer):
    while True:
        # 정확히 N바이트 읽기 (부족하면 대기)
        header = await reader.readexactly(4)
        length = struct.unpack('<I', header)[0]
        data = await reader.readexactly(length)
        # 처리...
        writer.write(b'response')
        await writer.drain()

server = await asyncio.start_server(handle_client, '0.0.0.0', 7945)

# 클라이언트
reader, writer = await asyncio.open_connection('jc.joy-june.com', 7945)
writer.write(struct.pack('<I', len(data)) + data)
await writer.drain()
```

### 6-4. JSON 파싱 패턴

JoyTalk의 패킷이 JSON이라는 걸 어떻게 알았나:

```csharp
// 역컴파일 코드에서 발견
StreamReader streamReader = new StreamReader(networkStream);
string line = await streamReader.ReadLineAsync();  // 줄 단위 읽기
JsonDocument.Parse(line);                          // JSON 파싱

// 송신
Dictionary<string, string> packet = new Dictionary<string, string> {
    { "type", "chat" },
    { "text", "안녕하세요" }
};
string json = JsonSerializer.Serialize(packet);  // → {"type":"chat","text":"안녕하세요"}
```

**단서들:**
1. `StreamReader.ReadLineAsync()` — 줄 단위 텍스트 프로토콜
2. `JsonDocument.Parse()` — JSON
3. `JavaScriptEncoder.Create(...)` — JSON 직렬화 시 인코더 설정

---

## 7. 도구 사용법 요약

### ilspycmd — .NET 역컴파일

```bash
# 설치
dotnet tool install -g ilspycmd

# 단일 파일 역컴파일
ilspycmd Assembly.dll -o ./output/

# 특정 클래스만
ilspycmd Assembly.dll --type MyNamespace.MyClass

# 프로젝트 구조 확인
ilspycmd Assembly.dll --list-types
```

### xxd — 헥스 덤프

```bash
# 처음 100바이트
xxd file.bin | head -7

# 특정 오프셋부터
xxd -s 0x100 -l 64 file.bin

# 바이너리 → 헥스 문자열
xxd -p file.bin | tr -d '\n'

# 비교
xxd file1.bin > /tmp/a.hex
xxd file2.bin > /tmp/b.hex
diff /tmp/a.hex /tmp/b.hex
```

### strings — 문자열 추출

```bash
# 기본 (4글자 이상 ASCII)
strings binary_file

# 최소 길이 지정
strings -n 8 binary_file

# 유니코드 포함
strings -e l binary_file  # little-endian UTF-16
```

### tcpdump / Wireshark

```bash
# 특정 호스트 캡처
sudo tcpdump -i any -w capture.pcap host jc.joy-june.com

# 특정 포트
sudo tcpdump -i any -w capture.pcap port 7945

# 실시간으로 보기 (ASCII)
sudo tcpdump -i any -A host jc.joy-june.com and port 7945

# pcap 파일 분석
tcpdump -r capture.pcap -A
```

### Python 헥스 분석 원-라이너

```python
# 파일 열기
data = open('file.bin', 'rb').read()

# 헥스 출력
print(data[:64].hex(' '))  # 스페이스 구분

# 특정 바이트 찾기
pos = data.find(b'\xFF\xFE')

# 구조체 파싱
import struct
val = struct.unpack_from('<I', data, 0)[0]
```

---

## 8. 공통 패턴과 교훈

### 8-1. 분석 순서

```
1. 파일 구조 파악   → 무엇이 있는지 목록화
2. 진입점 찾기     → main, 초기화 함수
3. 핵심 기능 찾기  → 네트워크, 파일 IO, 렌더링
4. 데이터 역추적  → 문자열 어디서 왔나? 패킷 어디서 처리?
5. 가설 수립/검증  → "이 바이트가 X일 것이다" → 검증
```

### 8-2. 문자열 찾기가 핵심

대부분의 프로그램에서 **문자열은 가장 좋은 단서**:
- URL → 서버 주소, API 엔드포인트
- 에러 메시지 → 어디서 발생하는지 역추적
- 포맷 이름 → 파일 포맷 식별
- 이벤트 이름 → 프로토콜 타입명

```bash
# 압축/암호화 안 된 경우
strings binary | grep -E 'http|\.php|error|type|packet'

# 암호화된 경우 → 복호화 루틴 찾기
# → 역컴파일 코드에서 byte[] + Encoding.UTF8.GetString 패턴 찾기
```

### 8-3. 코드 흐름 추적

역컴파일 코드에서 원하는 부분을 찾는 법:

```
목표: 패킷 수신 핸들러 찾기

방법 1: 진입점부터 아래로
  Program.Main() → ... → NetworkManager → ReceiveLoop

방법 2: 핵심 메서드로 역방향 검색
  "ReadLineAsync" 검색 → 호출 위치 → 주변 코드 파악

방법 3: 문자열 역추적
  "chat" 문자열 어디서 쓰임? → 핸들러 발견
```

### 8-4. 가설-검증 사이클

```
가설: "이 딕셔너리가 패킷 타입 → 핸들러 매핑일 것이다"

검증 1: 딕셔너리 키들을 복호화해보니 "chat", "move", "login"
        → 패킷 타입명 맞음 ✓

검증 2: 핸들러 코드를 보니 채팅 메시지를 화면에 표시하는 코드
        → "chat" 핸들러 맞음 ✓

결론: 가설 확정
```

### 8-5. 자동화의 중요성

반복 작업은 무조건 자동화:

```python
# 수작업 (나쁜 예):
# _00A0() = "https://..."
# _1680() = "http://..."
# _2000() = "http://..."
# ... 2698개 직접 복호화??? 불가능

# 자동화 (좋은 예):
for match in re.finditer(r'public static string (_[\w]+)\(\).*?_6\((\d+),\s*(\d+),\s*(\d+)\)', code):
    method_map[match.group(1)] = decrypt(blob, int(match.group(3)), int(match.group(4)))
# 2698개 0.1초 완료
```

---

## 9. 더 공부할 것들

### 기초 — 꼭 알아야 할 것들

- **진법 변환**: 2진수, 16진수, 10진수 자유롭게 변환
- **비트 연산**: AND(`&`), OR(`|`), XOR(`^`), 시프트(`<<`, `>>`)
- **엔디언**: 리틀/빅 엔디언 차이, 언제 어느 것을 쓰는지
- **인코딩**: ASCII, UTF-8, EUC-KR, UTF-16 차이
- **struct 모듈**: Python으로 바이너리 파싱

### 중급 — 실력 향상

| 주제 | 공부 방법 |
|------|----------|
| x86/x64 어셈블리 | nand2tetris, CS:APP 책 |
| 네트워크 프로토콜 | RFC 문서, Wireshark 직접 분석 |
| 암호학 기초 | Cryptopals 챌린지 |
| 파일 포맷 | 010 Editor 템플릿 라이브러리 |
| .NET 리버싱 | dnSpy, ILSpy, dotPeek 사용법 |

### 도전 과제 — 직접 해보기

```
초급:
  □ PE 파일 포맷 직접 파싱 (DOS 헤더, PE 헤더)
  □ PNG 파일 포맷 파싱 (청크 구조)
  □ 간단한 XOR 암호화 CTF 문제 풀기

중급:
  □ Wireshark로 HTTP 트래픽 분석
  □ 간단한 바이너리 패치 (조건 분기 변경)
  □ CTF의 rev 카테고리 문제 풀기

고급:
  □ 다른 게임 프로토콜 분석
  □ 안드로이드 APK 역분석 (jadx)
  □ 실제 멀웨어 정적 분석 (샌드박스 환경에서)
```

### 추천 자료

```
책:
  - "리버싱: 소프트웨어 분석의 비밀" (Eldad Eilam)
  - "실전 바이너리 분석" (Dennis Andriesse)
  - "The IDA Pro Book"

온라인:
  - CTFtime.org     → CTF 대회
  - crackmes.one    → 연습용 바이너리
  - Cryptopals      → 암호 분석
  - pwn.college     → 시스템 해킹

도구:
  - Ghidra (무료 디스어셈블러/디컴파일러, NSA 제공)
  - IDA Pro (유료, 업계 표준)
  - x64dbg (Windows 디버거)
  - dnSpy (.NET 전용 디버거+디컴파일러)
  - Frida (동적 계측, iOS/Android 분석)
  - 010 Editor (바이너리 에디터, 템플릿 기능)
```

---

## 전체 분석 타임라인 요약

```
Phase 1: DLL 역컴파일
  ├─ ilspycmd로 65,597줄 C# 코드 복원
  ├─ 유니코드 난독화 파악 (_2047, _2051 등)
  ├─ 문자열 XOR 암호화 발견 (key = position ^ 0xAA)
  └─ 2698개 문자열 전체 복호화

Phase 2: 파일 포맷 분석
  ├─ RMM: 맵 데이터 (65개, 비트필드 타일)
  ├─ IRS: 타일 스프라이트 (96개, 팔레트 인덱스)
  ├─ JCR: 캐릭터 스프라이트 (79개, RLE+팔레트)
  ├─ MST: 아이템 텍스트 DB (750/1019개, EUC-KR)
  └─ CSMI: 오브젝트 배치 (1032개, Pascal 문자열)

Phase 3: 네트워크 프로토콜
  ├─ TCP 7942/7945: JSON 패킷 (131 인바운드, 188 아웃바운드)
  ├─ UDP 7946: Opus 음성 채팅
  ├─ 인증 플로우: login → webtoken → 게임 진입
  ├─ 투명 프록시 구현
  └─ 아이템 스폰 트래커 구현
```

---

*분석 완료일: 2026-04-19*  
*총 복호화된 문자열: 2,698개 / 인바운드 패킷: 131종 / 아웃바운드 패킷: 188종*
