#!/usr/bin/env python3
"""
Joytalk.dll 메서드 IL 패치 도구

동작 방식:
  1. ildasm으로 DLL → IL 텍스트 변환
  2. IL 수정
  3. ilasm으로 IL → DLL 재빌드
  4. Wine prefix의 DLL 교체

사용법:
  python3 patch_dll.py --dump          # IL 덤프만
  python3 patch_dll.py --patch         # 패치 적용 후 DLL 교체
  python3 patch_dll.py --restore       # 백업에서 원본 복원

요구사항:
  dotnet tool install -g dotnet-ildasm  (또는 mono의 ildasm/ilasm 사용)

실제 IL 수정은 patch_method() 함수 안에서 텍스트 치환으로 수행.
"""

import subprocess
import shutil
import argparse
from pathlib import Path
import datetime

GAME_DLL   = Path("/Applications/JoyTalk.app/Contents/SharedSupport/prefix/drive_c/Joytalk/Joytalk.dll")
BACKUP_DIR = Path("/Applications/JoyTalk.app/playground/dll_backups")
IL_DIR     = Path("/Applications/JoyTalk.app/playground/il_dump")


def dump_il():
    """DLL을 IL 텍스트로 변환"""
    IL_DIR.mkdir(exist_ok=True)

    # mono의 ildasm 또는 dotnet 도구 사용
    # macOS에서는 dotnet-ildasm 패키지 필요
    try:
        result = subprocess.run(
            ["dotnet-ildasm", str(GAME_DLL), "-o", str(IL_DIR / "Joytalk.il")],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"IL 덤프 완료: {IL_DIR / 'Joytalk.il'}")
            return True
    except FileNotFoundError:
        pass

    # ildasm이 없으면 ilspycmd로 C# 코드만 확인 가능
    print("ildasm 없음. 설치:")
    print("  dotnet tool install -g dotnet-ildasm")
    print()
    print("대안: C# 코드 수정 후 전체 재빌드 (방법 3 참조)")
    return False


def backup_dll():
    """원본 DLL 백업"""
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"Joytalk_{stamp}.dll"
    shutil.copy2(GAME_DLL, backup)
    print(f"백업: {backup}")
    return backup


def restore_dll():
    """가장 최근 백업으로 복원"""
    backups = sorted(BACKUP_DIR.glob("Joytalk_*.dll"))
    if not backups:
        print("백업 없음")
        return
    latest = backups[-1]
    shutil.copy2(latest, GAME_DLL)
    print(f"복원 완료: {latest} → {GAME_DLL}")


# ── IL 패치 예시들 ────────────────────────────────────────────────────────────

def patch_method(il_text: str) -> str:
    """
    IL 코드를 수정하는 곳.
    텍스트 치환으로 특정 메서드의 동작을 바꿀 수 있음.

    예시 1: 버전 체크 우회
    예시 2: 로그 추가
    예시 3: 조건 분기 변경 (brtrue → brfalse 등)
    """

    # 예시: "version check" 관련 조건 분기 우회
    # IL에서 brtrue.s (조건 분기) 를 찾아서 br.s (무조건 분기) 로 바꾸기
    #
    # il_text = il_text.replace(
    #     'brtrue.s   VERSION_FAIL',
    #     'br.s       VERSION_OK'   # 항상 OK로 점프
    # )

    # 여기에 원하는 패치 추가
    return il_text


def apply_patch():
    """패치 적용 후 DLL 교체"""
    il_file = IL_DIR / "Joytalk.il"
    if not il_file.exists():
        print("IL 덤프 먼저 실행: python3 patch_dll.py --dump")
        return

    # IL 읽기
    il_text = il_file.read_text(encoding='utf-8')
    original_size = len(il_text)

    # 패치 적용
    patched = patch_method(il_text)
    changed = patched != il_text

    if not changed:
        print("변경사항 없음 — patch_method() 안에 패치 코드를 작성하세요")
        return

    # 수정된 IL 저장
    patched_il = IL_DIR / "Joytalk_patched.il"
    patched_il.write_text(patched, encoding='utf-8')
    print(f"패치된 IL: {patched_il}")
    print(f"변경 크기: {original_size} → {len(patched)} bytes")

    # ilasm으로 재빌드
    patched_dll = IL_DIR / "Joytalk_patched.dll"
    result = subprocess.run(
        ["ilasm", str(patched_il), f"/output:{patched_dll}", "/dll"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"빌드 실패:\n{result.stderr}")
        return

    # 원본 백업 후 교체
    backup_dll()
    shutil.copy2(patched_dll, GAME_DLL)
    print(f"DLL 교체 완료: {GAME_DLL}")
    print("게임을 재시작하면 패치가 적용됩니다.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump",    action="store_true", help="IL 덤프")
    parser.add_argument("--patch",   action="store_true", help="패치 적용")
    parser.add_argument("--restore", action="store_true", help="원본 복원")
    args = parser.parse_args()

    if args.dump:
        dump_il()
    elif args.patch:
        apply_patch()
    elif args.restore:
        restore_dll()
    else:
        parser.print_help()
