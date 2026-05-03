#!/usr/bin/env python3
"""
Joytalk.dll의 UpdateBaseUrl 상수 (https://download.joy-june.com/joytalk/) 를
도달 불가능한 URL 로 바꿔서 자동 업데이트 흐름 차단.

C# 디컴파일 결과 (Joytalk/Program.cs):
  private const string UpdateBaseUrl = "https://download.joy-june.com/joytalk/";

const string 은 IL 의 #US 힙에 UTF-16LE 로 저장됨. 길이 동일한 다른 문자열로
오버라이트하면 메타데이터가 바뀌지 않아도 된다 (\\0 종결 없이 길이 prefix).

DownloadAndRunUpdater() 가 이 URL 로 GET 요청 → 호스트 해석/연결 실패 →
catch 블록 진입 → MessageBox 띄우고 false 리턴 → main 은 종료 안하고
게임 진행. CheckNeedsUpdate() 의 manifest URL 은 따로 (encrypted blob 안)
이지만, 성공해도 다음 단계(DownloadAndRunUpdater)가 실패해서 결과는 같음.

실행: py -3.11 playground/patch_update_url.py [--restore]
"""
import argparse, pathlib, shutil, sys

DLL  = pathlib.Path(r"C:/Users/berrr/AppData/Local/Joytalk/Joytalk.dll")
BAK  = DLL.with_suffix(".dll.bak")

ORIG = "https://download.joy-june.com/joytalk/"
NEW  = "https://localhost.invalid/joytalkXXXX/"   # 길이 동일 (38)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true", help="백업본으로 원복")
    ap.add_argument("--target", default=str(DLL))
    args = ap.parse_args()

    target = pathlib.Path(args.target)

    if args.restore:
        if not BAK.exists():
            sys.exit("백업 파일 없음")
        shutil.copy2(BAK, target)
        print(f"원복 완료: {BAK} → {target}")
        return

    assert len(NEW) == len(ORIG), f"길이 불일치 {len(NEW)} != {len(ORIG)}"

    if not BAK.exists():
        shutil.copy2(target, BAK)
        print(f"백업 생성: {BAK}")

    raw = bytearray(target.read_bytes())
    needle = ORIG.encode("utf-16-le")
    replace = NEW.encode("utf-16-le")

    matches = []
    start = 0
    while True:
        i = raw.find(needle, start)
        if i < 0: break
        matches.append(i)
        start = i + 1
    if not matches:
        sys.exit("URL 패턴을 DLL 에서 찾지 못함 — 이미 패치됐거나 빌드가 다름")

    for off in matches:
        raw[off:off+len(needle)] = replace
    target.write_bytes(raw)

    print(f"패치 완료: {len(matches)} 곳에서 URL 교체")
    for o in matches:
        print(f"  offset 0x{o:x}")
    print(f"\n원복 명령:")
    print(f"  py -3.11 playground/patch_update_url.py --restore")

if __name__ == "__main__":
    main()
