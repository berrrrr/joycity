"""현재 tracker 상태 + 최근 walker 로그 진단."""
import io, json, pathlib, sys, urllib.request, collections

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 1) /state
try:
    s = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/state", timeout=3).read())
    print("=== /state ===")
    print(f"connected:    {s['connected']}")
    print(f"myId:         {s['my_id']}")
    print(f"server pos:   ({s['server_x']}, {s['server_y']})")
    print(f"my_x/y pos:   ({s['my_x']}, {s['my_y']})  (낙관적 클라 트래킹)")
    print(f"walk_target:  {s['walk_target']}")
    print(f"path queued:  {s['path_remaining']}")
    print(f"walkable:     {s['walkable_cells']}")
    print(f"blocked:      {s['blocked_cells']}")
    print(f"map:          {s['map_id']}")
    print(f"items match:  {len(s['items'])}")
    s['items'].sort(key=lambda x: x['dist'])
    print("\n--- top 10 매칭 아이템 (가까운 순) ---")
    for i in s['items'][:10]:
        m = '★' if s['walk_target'] and s['walk_target'][0] == i['oid'] else ' '
        in_range = '🟢' if i['dist'] <= s.get('max_dist', 30) else '🔴'
        print(f"  {m} {in_range} {i['name']:8s} #{i['oid']:8d} ({i['x']:4d},{i['y']:4d}) dist={i['dist']:.0f}")
except Exception as e:
    print(f"/state 실패: {e}")

# 2) 최근 LOG_BUF 일부 (SSE 통해 가져오는 게 정석이지만 단순화 — /events 한 번만 read)
print("\n=== 최근 walker 로그 (LOG_BUF) ===")
try:
    import socket
    sock = socket.create_connection(("127.0.0.1", 8765), timeout=2)
    sock.send(b"GET /events HTTP/1.1\r\nHost: localhost\r\n\r\n")
    sock.settimeout(0.8)
    buf = b""
    try:
        while len(buf) < 30000:
            chunk = sock.recv(4096)
            if not chunk: break
            buf += chunk
    except socket.timeout:
        pass
    sock.close()
    # data: ... lines 만 추출
    body = buf.decode('utf-8', 'replace')
    lines = []
    for line in body.split("\n"):
        if line.startswith("data: "):
            try:
                p = json.loads(line[6:])
                if p.get("kind") == "log":
                    lines.append(p)
            except: pass
    # 최근 30개만
    for l in lines[-30:]:
        print(f"  [{l['ts']}] [{l['level']:7s}] {l['msg']}")
except Exception as e:
    print(f"/events 실패: {e}")

# 3) 최근 injected.jsonl 분석 — walker 가 진짜 뭘 보냈는지
print("\n=== 최근 injected 패킷 (walker 발사) ===")
inj = sorted(pathlib.Path("C:/Users/berrr/Workspaces/joycity/captures").glob("tracker_*.injected.jsonl"))
if inj:
    p = inj[-1]
    print(f"파일: {p.name} ({p.stat().st_size}B)")
    lines = p.read_text(encoding="utf-8").splitlines()
    print(f"총 packets: {len(lines)}")
    type_cnt = collections.Counter()
    for l in lines:
        try: type_cnt[json.loads(l).get('type')] += 1
        except: pass
    print(f"types: {dict(type_cnt)}")
    print("\n--- 마지막 10개 ---")
    for l in lines[-10:]:
        print(f"  {l[:180]}")
else:
    print("(injected 파일 없음)")
