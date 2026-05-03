#!/usr/bin/env python3
"""
Step 4 smoke test — emulator 가 C→S 골든 캡처에 대해 그럴듯하게 응답하는지 확인.

emulator 를 in-process 로 띄우고, 골든 capture C→S 의 첫 몇 패킷을 보낸 뒤,
S→C 응답을 모은다. 응답 type 카운트가 골든 S→C 와 비슷한 분포인지 확인.

실행: py -3.11 tests/test_emulator_smoke.py
"""
import asyncio, io, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import emulator  # noqa


GOLDEN = ROOT / "captures" / "golden"
C2S = GOLDEN / "proxy_7942_20260503_002756.raw.bin.c2s.jsonl"


async def run_test():
    server = emulator.GameServer()
    srv = await asyncio.start_server(server.handle_client, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    print(f"emulator @ 127.0.0.1:{port}")

    serve_task = asyncio.create_task(srv.serve_forever())

    reader, writer = await asyncio.open_connection("127.0.0.1", port)

    # 캡처 시나리오 — chat 까지 포함되도록 끝까지 (exit 제외)
    c2s_pkts = [json.loads(l) for l in C2S.read_text(encoding="utf-8").splitlines() if l.strip()]
    scenario = [p for p in c2s_pkts if p.get("type") != "exit"]

    # 발송
    for p in scenario:
        line = json.dumps(p, ensure_ascii=False).encode("utf-8") + b"\n"
        writer.write(line)
        await writer.drain()
        print(f"  C→S  {p.get('type')}")
    await writer.drain()

    # 응답 수신 — 1초 idle 까지
    received = []
    while True:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=1.0)
        except asyncio.TimeoutError:
            break
        if not line:
            break
        try:
            received.append(json.loads(line.decode("utf-8")))
        except Exception:
            pass

    writer.close()
    await asyncio.sleep(0.05)
    srv.close()
    serve_task.cancel()
    try:
        await serve_task
    except (asyncio.CancelledError, Exception):
        pass

    # 결과 검증
    print(f"\n받은 응답 {len(received)}개:")
    type_counter = {}
    for p in received:
        t = p.get("type")
        type_counter[t] = type_counter.get(t, 0) + 1
    for t, n in sorted(type_counter.items(), key=lambda x: -x[1]):
        print(f"  {n:3d}  {t}")

    # 최소 검증: ping/login/exp/bn/hp/refresh/info 가 모두 등장해야 함
    required = {"ping", "login", "exp", "bn", "hp", "refresh", "info"}
    missing = required - type_counter.keys()
    if missing:
        print(f"\n❌ 필수 응답 빠짐: {missing}")
        sys.exit(1)
    print("\n✅ 로그인 시퀀스 OK")

    # move/chat 도 echo back 되어야 함
    if "move" not in type_counter:
        print("❌ move echo 없음")
        sys.exit(1)
    if "chat" not in type_counter:
        print("❌ chat echo 없음")
        sys.exit(1)
    print("✅ move/chat echo OK")

if __name__ == "__main__":
    asyncio.run(run_test())
