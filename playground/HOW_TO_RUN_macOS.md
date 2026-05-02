# 역컴파일 코드 수정 & 실행 가이드 — macOS

---

## 목차

- [방법 선택](#방법-선택)
- [방법 1 — Playground (로직 테스트)](#방법-1--playground--로직-테스트)
- [방법 2 — DLL 직접 패치](#방법-2--dll-직접-패치)
- [방법 3 — 전체 재빌드 (GitHub CI)](#방법-3--전체-재빌드-github-ci)
- [디버깅 팁](#디버깅-팁)
- [파일 경로 레퍼런스](#파일-경로-레퍼런스)

---

## 방법 선택

| 목적 | 방법 |
|------|------|
| 파싱/프로토콜 로직 테스트 | 방법 1: Playground |
| 게임 클라이언트 일부 동작 수정 | 방법 2: DLL 패치 (dnSpyEx) |
| 게임 전체를 크게 수정 | 방법 3: GitHub Actions CI |

---

## 방법 1 — Playground (로직 테스트)

게임 UI 없이 네트워크/파서 로직만 C#으로 테스트.  
역컴파일 코드에서 원하는 클래스를 붙여넣고 바로 실행 가능.

### 폴더 구조

```
playground/
  Program.cs          ← 여기에 테스트 코드 작성
  JoyTalkLab.csproj   ← 프로젝트 설정 (패키지 추가도 여기서)
  extract_blob.py     ← string_blob.bin 추출 (최초 1회)
  patch_dll.py        ← DLL 패치 도구 (방법 2)
  string_blob.bin     ← extract_blob.py 실행 후 생성됨
```

### 실행

```bash
cd /Applications/JoyTalk.app/playground

# 최초 1회: 문자열 블롭 추출
python3 extract_blob.py

# 실행
dotnet run

# 빌드만 (오류 확인)
dotnet build
```

### 역컴파일 코드 붙여넣기

`decompiled/-/-.cs` 에서 원하는 클래스를 복사해서 `Program.cs` 하단에 추가.

```csharp
// Program.cs 하단에 붙여넣기
class _2047  // 원래 이름 그대로 써도 됨
{
    // ... 내용 ...
}
```

### 컴파일 오류 해결

| 오류 원인 | 해결법 |
|-----------|--------|
| `using` 누락 | 파일 상단에 필요한 `using` 추가 |
| Windows 전용 타입 | `System.Windows.Forms.*` → 주석 처리 또는 대체 |
| 다른 클래스 의존 | 해당 클래스도 같이 복사 |
| 알 수 없는 타입 | NuGet 패키지 추가 (아래 참고) |

### 자주 쓰는 패키지 추가

```bash
dotnet add package Concentus   # 음성 코덱
dotnet add package NAudio      # 오디오
# System.Net.Http → 기본 내장, 추가 불필요
```

---

## 방법 2 — DLL 직접 패치

게임 클라이언트 자체를 수정. UI 포함 실제 게임에 적용됨.

### dnSpyEx 설치

```bash
# Homebrew
brew install --cask dnspyex

# 또는 GitHub Releases에서 직접 다운로드
# https://github.com/dnSpyEx/dnSpy/releases
```

### 사용법

1. dnSpyEx 실행 → **File → Open**
2. DLL 열기:  
   `/Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Joytalk.dll`
3. 왼쪽 트리에서 수정할 클래스/메서드 찾기  
   (클래스명이 `_2047` 같이 난독화 — [Phase 3 결과](../phase3_results.md) 참고)
4. 메서드 우클릭 → **Edit Method (C#)**
5. C# 코드 수정
6. **Compile** → **File → Save Module**

### 백업 & 복원

```bash
# 백업
cp /Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Joytalk.dll \
   /Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Joytalk.dll.bak

# 복원 (Python 스크립트)
python3 patch_dll.py --restore
```

---

## 프록시 / 패킷 캡처 (macOS)

게임이 서버 IP를 하드코딩(`119.200.71.233`)해서 `/etc/hosts` 방식은 동작하지 않음.  
`pfctl`로 커널 레벨에서 트래픽을 가로채야 함.

### 설정 및 실행

```bash
cd /Applications/JoyTalk.app

# 터미널 1: pfctl 리다이렉트 활성화
sudo bash tools/pf_redirect.sh start

# 상태 확인
sudo bash tools/pf_redirect.sh status

# 터미널 2: 프록시 실행
python3 tools/proxy.py

# 또는 아이템 트래커
python3 tools/item_tracker.py --discover
```

### 종료 후 원복

```bash
# 터미널에서 Ctrl+C 후
sudo bash tools/pf_redirect.sh stop
```

### 수정 예시

```csharp
// 버전 체크 우회
// if (version != expectedVersion)
//     ShowUpdateDialog();
```

---

## 방법 3 — 전체 재빌드 (GitHub CI)

WinForms 때문에 macOS에서는 직접 빌드 불가.  
GitHub Actions (windows-latest runner)를 이용해 빌드.

### GitHub Actions 워크플로

`.github/workflows/build.yml`:

```yaml
name: Build JoyTalk

on: push

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '10.0.x'

      - run: dotnet build JoyTalkMod.csproj -c Release

      - uses: actions/upload-artifact@v4
        with:
          name: JoyTalk-patched
          path: bin/Release/net10.0-windows/JoyTalk.dll
```

### 프로젝트 파일

```xml
<!-- rebuild/JoyTalkMod.csproj -->
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows</TargetFramework>
    <UseWindowsForms>true</UseWindowsForms>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <LangVersion>preview</LangVersion>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="../decompiled/-/-.cs" />
    <Compile Include="../decompiled/-PrivateImplementationDetails-.../*.cs" />
    <PackageReference Include="Concentus"         Version="2.2.2" />
    <PackageReference Include="NAudio"            Version="2.2.1" />
    <PackageReference Include="CefSharp.WinForms" Version="131.3.30" />
  </ItemGroup>
</Project>
```

### 흐름

```
코드 수정 → git push → GitHub Actions 빌드
→ Actions 탭에서 Artifact 다운로드 → 게임 폴더에 복사
```

---

## 디버깅 팁

### 역컴파일 코드에서 원하는 부분 찾기

```bash
# 패킷 타입으로 핸들러 찾기
grep -n '"chat"\|"move"\|"login"' /Applications/JoyTalk.app/decompiled/-/-.cs

# 특정 API 사용 위치
grep -n 'ReadLineAsync\|JsonDocument' /Applications/JoyTalk.app/decompiled/-/-.cs | head -20

# 클래스 목록
grep -n '^class \|^\tclass ' /Applications/JoyTalk.app/decompiled/-/-.cs | head -30
```

### VS Code로 편집

```bash
code /Applications/JoyTalk.app/playground
```

C# Dev Kit 익스텐션 설치하면 자동완성, 인라인 오류 표시 지원.

---

## 파일 경로 레퍼런스

```
게임 DLL:
  /Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Joytalk.dll

역컴파일 메인 코드 (65,597줄):
  /Applications/JoyTalk.app/decompiled/-/-.cs

역컴파일 문자열 클래스:
  /Applications/JoyTalk.app/decompiled/-PrivateImplementationDetails--AC6C2DFE-.../3CDA3D22-...cs

Playground:
  /Applications/JoyTalk.app/playground/Program.cs

Python 도구:
  /Applications/JoyTalk.app/tools/    ← 프록시, 트래커
  /Applications/JoyTalk.app/server/   ← 에뮬레이터
  /Applications/JoyTalk.app/parsers/  ← 파일 파서
```
