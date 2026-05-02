#!/bin/bash
# pfctl 기반 IP 리다이렉트
# hosts 수정이 소용없을 때 (게임이 IP 하드코딩) 사용
#
# 원리:
#   게임 → 119.200.71.233:7942  →(pfctl rdr)→  127.0.0.1:17942 (proxy)
#   proxy → 119.200.71.233:7942  →(pass quick, src=127.0.0.2)→  실서버
#
# 사용법:
#   sudo bash pf_redirect.sh start   # 활성화
#   sudo bash pf_redirect.sh stop    # 원복
#   sudo bash pf_redirect.sh status  # 확인

REAL_IP="119.200.71.233"
PROXY_SRC="127.0.0.2"     # proxy outbound 전용 loopback alias (pfctl 제외)
ANCHOR="joytalk"
ANCHOR_FILE="/etc/pf.anchors/$ANCHOR"
PF_CONF="/etc/pf.conf"

start() {
    echo "[1/3] loopback alias 추가: $PROXY_SRC"
    ifconfig lo0 alias $PROXY_SRC 255.255.255.255 2>/dev/null && echo "  추가됨" || echo "  이미 존재"

    echo "[2/3] pf anchor 규칙 작성: $ANCHOR_FILE"
    tee $ANCHOR_FILE > /dev/null << RULES
# proxy outbound는 리다이렉트 제외 (루프 방지)
pass out quick proto tcp from $PROXY_SRC to $REAL_IP port {7942, 7945}

# 게임 클라이언트 트래픽을 로컬 프록시로 리다이렉트
rdr pass proto tcp from any to $REAL_IP port 7942 -> 127.0.0.1 port 17942
rdr pass proto tcp from any to $REAL_IP port 7945 -> 127.0.0.1 port 17945
RULES

    echo "[3/3] pf.conf anchor 등록 및 reload"
    if ! grep -q "anchor \"$ANCHOR\"" $PF_CONF 2>/dev/null; then
        tee -a $PF_CONF > /dev/null << CONF

# JoyTalk proxy anchor
rdr-anchor "$ANCHOR"
anchor "$ANCHOR"
load anchor "$ANCHOR" from "$ANCHOR_FILE"
CONF
        echo "  → $PF_CONF 업데이트됨"
    else
        echo "  → anchor 이미 등록됨"
    fi

    pfctl -e 2>/dev/null || true
    pfctl -f $PF_CONF && echo "  → pf reload 완료"

    echo ""
    echo "✓ 리다이렉트 활성화:"
    echo "  $REAL_IP:7942  →  127.0.0.1:17942"
    echo "  $REAL_IP:7945  →  127.0.0.1:17945"
    echo ""
    echo "다음 단계:"
    echo "  python3 tools/proxy.py"
}

stop() {
    echo "pfctl anchor 초기화..."
    pfctl -a $ANCHOR -F all 2>/dev/null && echo "  규칙 제거됨" || echo "  (anchor 없었음)"

    echo "loopback alias 제거..."
    ifconfig lo0 -alias $PROXY_SRC 2>/dev/null && echo "  $PROXY_SRC 제거됨" || echo "  (없었음)"

    echo ""
    echo "✓ 리다이렉트 해제"
    echo "  (pf.conf 추가 라인은 수동으로 정리하거나 무시해도 됨)"
}

status() {
    echo "=== pfctl anchor 규칙 ==="
    pfctl -a $ANCHOR -s rules 2>/dev/null || echo "  (anchor 없음)"
    echo ""
    echo "=== pfctl NAT/RDR ==="
    pfctl -a $ANCHOR -s nat 2>/dev/null || echo "  (없음)"
    echo ""
    echo "=== lo0 loopback aliases ==="
    ifconfig lo0 | grep "inet 127\."
}

# root 확인
if [ "$(id -u)" != "0" ]; then
    echo "오류: root 권한 필요"
    echo "  sudo bash $0 $1"
    exit 1
fi

case "$1" in
    start)  start ;;
    stop)   stop ;;
    status) status ;;
    *)
        echo "사용법: sudo bash pf_redirect.sh start|stop|status"
        echo ""
        echo "  start  — pfctl 리다이렉트 + loopback alias 설정"
        echo "  stop   — 원복"
        echo "  status — 현재 규칙 확인"
        ;;
esac
