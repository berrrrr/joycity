#!/usr/bin/env python3
"""
캡처 raw bin 의 비밀번호/개인정보 마스킹 + NDJSON 줄로 변환.

input  : captures/proxy_*.raw.bin.{c2s,s2c}
output : captures/golden/<basename>.jsonl   (한 줄당 JSON 한 패킷)

마스킹 규칙:
  - userpw      → "***"
  - userid      → "tester"
  - id (uuid)   → 그대로 유지 (장면 재현 위해)
  - email/phone → 발견 시 ***

실행: py -3.11 tools/sanitize_capture.py captures/proxy_7942_*.raw.bin.c2s [...]
"""
import argparse, io, json, pathlib, re, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = pathlib.Path(__file__).resolve().parent.parent
GOLD = REPO / "captures" / "golden"
GOLD.mkdir(parents=True, exist_ok=True)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\b01[0-9]-?\d{3,4}-?\d{4}\b")

def sanitize(p: dict) -> dict:
    if isinstance(p, dict):
        if "userpw" in p:    p["userpw"]   = "***"
        if "userid" in p:    p["userid"]   = "tester"
        if "password" in p:  p["password"] = "***"
        if "email" in p:     p["email"]    = "***"
        if "phone" in p:     p["phone"]    = "***"
        for k, v in list(p.items()):
            if isinstance(v, str):
                v = EMAIL_RE.sub("***@***", v)
                v = PHONE_RE.sub("***", v)
                p[k] = v
            elif isinstance(v, (dict, list)):
                p[k] = sanitize(v)
    elif isinstance(p, list):
        return [sanitize(x) for x in p]
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args()

    for src in args.paths:
        src = pathlib.Path(src)
        b = src.read_bytes()
        lines = [l for l in b.split(b"\n") if l.strip()]
        ok = err = 0
        # 방향 suffix 보존 (.c2s / .s2c)
        suffix = src.suffix
        out = GOLD / (src.stem + suffix + ".jsonl")
        with open(out, "w", encoding="utf-8") as f:
            for l in lines:
                try:
                    j = json.loads(l.decode("utf-8"))
                    j = sanitize(j)
                    f.write(json.dumps(j, ensure_ascii=False) + "\n")
                    ok += 1
                except Exception:
                    err += 1
        print(f"  {src.name}  →  {out}  ({ok} 패킷, {err} 에러)")


if __name__ == "__main__":
    main()
