import io, json, pathlib, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

p = pathlib.Path(r"C:/Users/berrr/Workspaces/joycity/captures/golden/proxy_7942_20260503_002756.raw.bin.s2c.jsonl")
pkts = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

print("=== S->C 처음 25개 ===")
for i, x in enumerate(pkts[:25]):
    t = x.get("type", "?")
    extra = ""
    if t == "map":
        extra = "  MapNum=" + str(x.get("MapNum"))
    elif t == "obj":
        extra = "  GO=" + str(len(x.get("gameObjects", {})))
    print(f"  #{i:3d}  {t}{extra}")

# 두 번째 obj (GO=1) 풀 dump
print("\n=== 두 번째 obj 풀 ===")
n = 0
for x in pkts:
    if x.get("type") == "obj":
        n += 1
        if n == 2:
            print(json.dumps(x, ensure_ascii=False, indent=2)[:1500])
            break

print("\n=== objc 첫번째 ===")
for x in pkts:
    if x.get("type") == "objc":
        print(json.dumps(x, ensure_ascii=False, indent=2)[:1500])
        break

print("\n=== type 다양성 (obj/objc 안에 등장한 모든 type 값) ===")
seen_types = set()
for x in pkts:
    if x.get("type") in ("obj", "objc"):
        for v in x.get("gameObjects", {}).values():
            seen_types.add(v.get("type"))
print(" ", seen_types)
