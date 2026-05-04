"""JoyTalk 아이템 트래커 패키지.

진입점: `python -m item_tracker [--preset NAME] [...]`

모듈 구성:
  notify     — 로그/비프/디스코드, ANSI 색
  collision  — RMM 정적 collision + 런타임 학습 + A*
  tracker    — Tracker 클래스 (패킷 처리, walker/proximity 루프)
  proxy      — TCP MITM 프록시 (relay_lines, handle_client, passthrough)
  cli        — argparse + TOML 프리셋 + run()
"""
