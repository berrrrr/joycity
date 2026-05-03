"""obj.gpd (CSMI) collision_layers 검증.

가설: RMM cell.obj_code → CSMI object_id → collision_layers.point_ids 가
       비어있으면 walkable, 점들이 있으면 blocked.

실행: py -3.11 playground/verify_csmi_collision.py
"""
import io, pathlib, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "parsers"))
import csmi_parser, rmm_parser

GAME = pathlib.Path("C:/Users/berrr/AppData/Local/Joytalk")

# obj.gpd 로드
gpd = csmi_parser.parse(str(GAME / "Street/M/A/obj.gpd"))
print(f"obj.gpd objects: {len(gpd)}")

# 각 object 의 collision points 통계
coll_stats = []
for obj in gpd:
    total_points = sum(len(cl.point_ids) for cl in obj.collision_layers)
    coll_stats.append((obj.object_id, total_points))

# 분포
print(f"\n=== object 별 collision point 수 분포 ===")
zeros = sum(1 for _, n in coll_stats if n == 0)
nonzero = len(coll_stats) - zeros
print(f"  point 0개 (walkable): {zeros} / {len(coll_stats)} ({100*zeros/len(coll_stats):.1f}%)")
print(f"  point 있음 (blocking): {nonzero}")
print(f"  최대 point 수: {max(s[1] for s in coll_stats)}")
# 첫 10개 sample
print(f"\n  첫 10 object:")
for oid, n in coll_stats[:10]:
    print(f"    object#{oid}: {n} collision points")

# RMM 의 obj_code 분포 vs CSMI object_id
m = rmm_parser.parse(str(GAME / "Street/M/Map01006.rmm"))
rmm_obj_codes = collections.Counter()
for row in m.grid:
    for c in row:
        rmm_obj_codes[c.obj_code] += 1
print(f"\n=== Map01006 RMM obj_code top 10 ===")
for code, n in rmm_obj_codes.most_common(10):
    # CSMI 에서 해당 object 찾아 collision 비교
    matched = [s for s in coll_stats if s[0] == code]
    coll = matched[0][1] if matched else "(no match)"
    print(f"  obj_code={code:4d}: {n:5d}회 등장   CSMI collision points = {coll}")

# 만약 매칭되면, walked 셀의 obj_code → coll 분포
print(f"\n=== 사용자 walked 셀의 obj_code 별 CSMI collision ===")
import json
# 가장 최근 tracker 캡처에서 walked cells
captures = sorted(pathlib.Path("C:/Users/berrr/Workspaces/joycity/captures").glob("tracker_7942_*.s2c.jsonl"))
if captures:
    s = captures[-1].read_text(encoding="utf-8").splitlines()
    my_id = None
    for l in s[:60]:
        try:
            p = json.loads(l)
            if p.get("type") == "login":
                my_id = p.get("myId"); break
        except: pass

    walked = set()
    for l in s:
        if not l.strip(): continue
        try: p = json.loads(l)
        except: continue
        if p.get("type") == "move" and str(p.get("no")) == str(my_id):
            try: walked.add((int(p["VX"]), int(p["VY"])))
            except: pass

    print(f"  walked cells: {len(walked)}")
    coll_at_walked = collections.Counter()
    for x, y in walked:
        if 0 <= x < m.width and 0 <= y < m.height:
            code = m.grid[y][x].obj_code
            matched = [s for s in coll_stats if s[0] == code]
            coll = matched[0][1] if matched else -1
            coll_at_walked[coll] += 1
    print(f"  walked 셀 위치의 CSMI collision points 분포:")
    for c, n in sorted(coll_at_walked.items()):
        label = "(no CSMI match)" if c == -1 else f"{c} points"
        print(f"    {label}: {n} cells")
