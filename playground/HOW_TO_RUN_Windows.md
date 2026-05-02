# 역컴파일 코드 수정 & 실행 가이드 — Windows

---

## 목차

- [방법 선택](#방법-선택)
- [파일 공유 (macOS에서 받아오기)](#파일-공유-macos에서-받아오기)
- [방법 1 — Playground (로직 테스트)](#방법-1--playground--로직-테스트)
- [방법 2 — dnSpy로 DLL 직접 수정](#방법-2--dnspy로-dll-직접-수정)
- [방법 3 — 전체 재빌드 (Visual Studio)](#방법-3--전체-재빌드-visual-studio)
- [프록시 / 패킷 캡처 (Windows)](#프록시--패킷-캡처-windows)
- [디버깅 팁](#디버깅-팁)
- [파일 경로 레퍼런스](#파일-경로-레퍼런스)

---

## 방법 선택

| 목적 | 방법 |
|------|------|
| 파싱/프로토콜 로직 테스트 | 방법 1: Playground |
| 게임 클라이언트 일부 동작 수정 | 방법 2: dnSpy (네이티브, 디버깅 포함) |
| 게임 전체를 크게 수정 | 방법 3: Visual Studio / dotnet build |
| 실시간 패킷 캡처 | 프록시 도구 (Python) |

> Windows에서는 macOS와 달리 WinForms 빌드 제약이 없음.  
> 전체 재빌드, 실시간 디버깅 모두 로컬에서 바로 가능.

---

## 파일 공유 (macOS에서 받아오기)

분석 도구와 역컴파일 코드는 macOS에 있으므로 먼저 Windows로 가져와야 함.

### 방법 A: Git 저장소 (권장)

```bash
# macOS에서 (최초 1회)
cd /Applications/JoyTalk.app
git init
git add decompiled/ parsers/ server/ tools/ playground/
git commit -m "init"
git remote add origin https://github.com/본인계정/joytalk-re.git
git push -u origin main
```

```powershell
# Windows에서
git clone https://github.com/본인계정/joytalk-re.git C:\joytalk-re
```

`.gitignore` 설정 (게임 바이너리 제외):

```gitignore
*.dll
*.exe
string_blob.bin
captures/
dll_backups/
```

### 방법 B: SMB 네트워크 드라이브

```
macOS: 시스템 환경설정 → 공유 → 파일 공유 → /Applications/JoyTalk.app 공유
Windows: 탐색기 → \\[맥IP주소]\JoyTalk.app
```

### 방법 C: USB / OneDrive

복사 후 `C:\joytalk-re\` 에 배치.

---

## 방법 1 — Playground (로직 테스트)

macOS 방법 1과 동일한 흐름. Python과 .NET SDK만 있으면 됨.

### 설치

```powershell
winget install Microsoft.DotNet.SDK.10   # .NET 10 SDK
winget install Python.Python.3.11        # Python 3.11+
winget install Microsoft.VisualStudioCode  # VS Code (선택)
```

### 실행

```powershell
cd C:\joytalk-re\playground

# 최초 1회: 문자열 블롭 추출
python extract_blob.py

# 실행
dotnet run

# 빌드만 (오류 확인)
dotnet build
```

### VS Code로 열기

```powershell
code C:\joytalk-re\playground
```

C# Dev Kit 익스텐션 설치하면 자동완성, 인라인 오류 표시, 디버거 모두 사용 가능.

### 역컴파일 코드 붙여넣기

`C:\joytalk-re\decompiled\-\-.cs` 에서 원하는 클래스를 복사 → `Program.cs` 하단에 추가.

```csharp
// Program.cs 하단에 붙여넣기
class _2047  // 원래 이름 그대로 써도 됨
{
    // ... 내용 ...
}
```

| 오류 원인 | 해결법 |
|-----------|--------|
| `using` 누락 | 파일 상단에 필요한 `using` 추가 |
| Windows 전용 타입 | `System.Windows.Forms.*` → 여기선 OK (Windows이므로) |
| 다른 클래스 의존 | 해당 클래스도 같이 복사 |
| 알 수 없는 타입 | NuGet 패키지 추가 |

---

## 방법 2 — dnSpy로 DLL 직접 수정

Windows용 dnSpy는 기능이 가장 완전함.  
게임 설치 폴더에서 DLL을 직접 열고 수정하고 실시간 디버깅까지 가능.

### 설치

```powershell
winget install dnSpy.dnSpy

# 또는 GitHub에서 직접 다운로드
# https://github.com/dnSpy/dnSpy/releases → dnSpy-net-win64.zip
```

### DLL 수정

1. `dnSpy.exe` 실행
2. **File → Open** → `C:\Program Files\JoyTalk\Joytalk.dll`
3. 왼쪽 트리에서 클래스 탐색  
   (난독화된 이름 `_2047`, `_2051` 등은 [Phase 3 결과](../phase3_results.md) 참고)
4. 메서드 우클릭 → **Edit Method (C#)**
5. C# 코드 수정 → **Compile**
6. **File → Save Module** → 원본 덮어쓰기

### 백업 & 복원

```powershell
# 백업
Copy-Item "C:\Program Files\JoyTalk\Joytalk.dll" "C:\Program Files\JoyTalk\Joytalk.dll.bak"

# 복원
Copy-Item "C:\Program Files\JoyTalk\Joytalk.dll.bak" "C:\Program Files\JoyTalk\Joytalk.dll"
```

### 실시간 디버깅 (Windows 전용 기능)

```
1. dnSpy → Debug → Start (Joytalk.exe 선택)
2. 코드에서 확인하고 싶은 줄 클릭 → F9 (브레이크포인트 설정)
3. 게임에서 해당 동작 실행
4. 실행이 멈추면 변수 값, 스택, 메모리 확인 가능
```

| 기능 | 방법 |
|------|------|
| 실시간 디버깅 | Debug → Start (게임 실행 중 브레이크포인트) |
| 메모리 값 확인 | Debug 모드에서 변수 hover |
| IL 직접 수정 | Edit → Edit IL Instructions |
| 전체 문자열 검색 | Edit → Search Assemblies → String |

> 코드 수정 없이 "관찰" 용도로도 매우 유용.  
> 패킷이 어떤 값으로 들어오는지, 어떤 조건 분기를 타는지 실시간 확인 가능.

---

## 방법 3 — 전체 재빌드 (Visual Studio)

macOS에서 불가능했던 WinForms 전체 재빌드를 Windows에서 직접 수행.

### 설치

```powershell
# Visual Studio 2022 Community (무료)
winget install Microsoft.VisualStudio.2022.Community
# 설치 시 ".NET 데스크톱 개발" 워크로드 선택

# 또는 VS Code + SDK만으로도 가능
winget install Microsoft.DotNet.SDK.10
```

### 프로젝트 파일 생성

`C:\joytalk-re\rebuild\JoyTalkMod.csproj` 생성:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows</TargetFramework>
    <UseWindowsForms>true</UseWindowsForms>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <LangVersion>preview</LangVersion>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
    <Optimize>false</Optimize>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="..\decompiled\-\-.cs" />
    <Compile Include="..\decompiled\-PrivateImplementationDetails--AC6C2DFE-D87B-4B2C-94F2-0C219A0FF1EF-\*.cs" />
  </ItemGroup>
  <ItemGroup>
    <PackageReference Include="Concentus"         Version="2.2.2" />
    <PackageReference Include="NAudio"            Version="2.2.1" />
    <PackageReference Include="CefSharp.WinForms" Version="131.3.30" />
  </ItemGroup>
</Project>
```

### 빌드

```powershell
cd C:\joytalk-re\rebuild

dotnet restore

# 빌드 (로그 저장)
dotnet build 2>&1 | Tee-Object build_log.txt

# 오류 수만 확인
dotnet build 2>&1 | Select-String "error CS"
```

### 예상 컴파일 오류와 해결법

| 오류 코드 | 메시지 | 해결 |
|-----------|--------|------|
| `CS0246` | `형식 'XXX'을(를) 찾을 수 없음` | NuGet 패키지 추가 또는 `using` 추가 |
| `CS0103` | `이름 'XXX'이(가) 없음` | 의존 클래스도 같이 포함 |
| `CS0051` | `접근성 불일치` | `private` → `internal` 변경 |
| `CS8803` | `최상위 문은 하나만` | 진입점 중복 → `Program.cs` 하나만 유지 |
| `CS1503` | `인수 형식 변환 불가` | 명시적 캐스트 `(int)` 추가 |
| `CS0200` | `읽기 전용에 할당 불가` | getter-only → 필드로 변경 |

### 오류가 많을 때 — 점진적 포함 전략

```
1단계: 문자열 복호화 클래스만 (오류 적음)
2단계: 네트워크 클래스 추가
3단계: 게임 오브젝트 클래스 추가
4단계: UI 클래스 추가 (오류 가장 많음)
```

### 빌드 후 게임 폴더에 복사

```powershell
$built = "bin\Debug\net10.0-windows\JoyTalkMod.dll"
$game  = "C:\Program Files\JoyTalk\Joytalk.dll"

Copy-Item $game "$game.bak"
Copy-Item $built $game

Write-Host "완료. 게임을 재시작하세요."
```

---

## 프록시 / 패킷 캡처 (Windows)

Python 도구(`tools/proxy.py`, `tools/item_tracker.py`)는 Windows에서도 동일하게 동작.

### hosts 파일 수정 (관리자 PowerShell)

```powershell
# 트래픽 가로채기 (추가)
Add-Content C:\Windows\System32\drivers\etc\hosts "127.0.0.1 jc.joy-june.com"

# 원복
(Get-Content C:\Windows\System32\drivers\etc\hosts) |
    Where-Object { $_ -notmatch 'jc.joy-june.com' } |
    Set-Content C:\Windows\System32\drivers\etc\hosts
```

### 프록시 실행

```powershell
cd C:\joytalk-re

# 아이템 감지 (실시간)
python tools\item_tracker.py --discover

# 패킷 캡처
python tools\proxy.py
```

---

## 디버깅 팁

### 역컴파일 코드에서 원하는 부분 찾기

```powershell
# PowerShell에서 grep 대용
Select-String '"chat"' C:\joytalk-re\decompiled\-\-.cs
Select-String 'ReadLineAsync' C:\joytalk-re\decompiled\-\-.cs | Select-Object -First 20
```

### VS Code로 편집

```powershell
code C:\joytalk-re\playground
```

Visual Studio 2022는 더 강력한 리팩터링/디버깅 지원 (IntelliSense, 실시간 오류, 브레이크포인트 등).

---

## 파일 경로 레퍼런스

```
게임 DLL:
  C:\Program Files\JoyTalk\Joytalk.dll

게임 실행 파일:
  C:\Program Files\JoyTalk\Joytalk.exe

리소스 파일:
  C:\Program Files\JoyTalk\Res\

역컴파일 코드 (git clone 후):
  C:\joytalk-re\decompiled\-\-.cs

Playground:
  C:\joytalk-re\playground\Program.cs

재빌드 프로젝트:
  C:\joytalk-re\rebuild\JoyTalkMod.csproj

Python 도구:
  C:\joytalk-re\tools\
  C:\joytalk-re\server\

Windows hosts 파일:
  C:\Windows\System32\drivers\etc\hosts
```
