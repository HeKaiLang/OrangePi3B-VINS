#!/bin/bash
# fix_clock.sh —— Orange Pi 3B 无 RTC 电池，断电后系统时钟倒退（曾观测慢 15 天）。
#
# 为什么要用 HTTP Date 头而不是 NTP：
#   板子 DNS 不可靠，且时钟错乱时 TLS 证书会报 "not yet valid"，
#   所以这里用 curl -k 忽略证书校验，只从 HTTP 响应头里取 Date 字段。
#
# 用法：
#   sudo bash /workspace/scripts/fix_clock.sh            自动取时并设置
#   sudo bash /workspace/scripts/fix_clock.sh --dry-run  只报告偏差，不修改
#   sudo bash /workspace/scripts/fix_clock.sh "2026-11-18 22:40:00"   手动按本地时间设置
#
# 注意：vins-noetic-container 是 --privileged，容器内执行同样能改正宿主机时钟。

set -u
DRY=0
ARG=""
for a in "$@"; do
  case "$a" in
    -n|--dry-run) DRY=1 ;;
    *) ARG="$a" ;;
  esac
done

say(){ printf '%s\n' "$*"; }
stamp(){ date '+%Y-%m-%d %H:%M:%S %Z (UTC%z)'; }

if [ "$(id -u)" -ne 0 ] && [ "$DRY" -eq 0 ]; then
  say "需要 root 权限：请用 sudo 运行"; exit 1
fi

BEFORE=$(date -u +%s)
say "=== 当前时间 ==="
say "local : $(stamp)"
say "utc   : $(date -u '+%Y-%m-%d %H:%M:%S')   epoch=$BEFORE"

# ---------- 手动模式 ----------
if [ -n "$ARG" ]; then
  say "=== 手动设置（按本地时间解释）：$ARG ==="
  if [ "$DRY" -eq 1 ]; then say "[dry-run] 跳过修改"; exit 0; fi
  if date -s "$ARG"; then say "OK -> $(stamp)"; exit 0; else say "FAIL：时间格式无法解析"; exit 1; fi
fi

# ---------- 自动取时 ----------
fetch_header_epoch(){
  local url="$1" proxy="$2" raw hdr
  if [ -n "$proxy" ]; then
    raw=$(curl -sI -m 8 -k --proxy "$proxy" "$url" 2>/dev/null)
  else
    raw=$(curl -sI -m 8 -k --noproxy '*' "$url" 2>/dev/null)
  fi
  [ -z "$raw" ] && return 1
  hdr=$(printf '%s' "$raw" | tr -d '\r' | grep -i '^date:' | head -1 | sed 's/^[^:]*:[[:space:]]*//')
  [ -z "$hdr" ] && return 1
  date -u -d "$hdr" +%s 2>/dev/null
}

EPOCH=""
SRC=""
URLS="https://www.baidu.com https://www.aliyun.com https://www.cloudflare.com http://www.baidu.com"

PROXIES=""
for p in "${https_proxy:-}" "${http_proxy:-}" "${HTTPS_PROXY:-}" "${HTTP_PROXY:-}"; do
  [ -n "$p" ] && PROXIES="$PROXIES $p"
done
# 本机已知的 ICS 共享网关代理（换网络会变，仅作最后兜底）
PROXIES="$PROXIES 192.168.137.1:7897"

if command -v curl >/dev/null 2>&1; then
  for u in $URLS; do
    for p in "" $PROXIES; do
      e=$(fetch_header_epoch "$u" "$p") && { EPOCH="$e"; SRC="curl $u [${p:-直连}]"; break 2; }
    done
  done
fi

if [ -z "$EPOCH" ] && command -v python3 >/dev/null 2>&1; then
  EPOCH=$(python3 - <<'PY' 2>/dev/null
import ssl, urllib.request, email.utils, sys
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
for u in ("https://www.baidu.com", "https://www.cloudflare.com"):
    try:
        r = urllib.request.urlopen(u, timeout=8, context=ctx)
        d = r.headers.get("Date")
        if d:
            print(int(email.utils.parsedate_to_datetime(d).timestamp()))
            sys.exit(0)
    except Exception:
        pass
sys.exit(1)
PY
)
  [ -n "$EPOCH" ] && SRC="python3 urllib"
fi

if [ -z "$EPOCH" ] && command -v sntp >/dev/null 2>&1; then
  T=$(sntp -t 5 pool.ntp.org 2>/dev/null | awk '/^[0-9]{4}-/{print $1" "$2}')
  if [ -n "$T" ]; then
    EPOCH=$(date -u -d "$T" +%s 2>/dev/null)
    [ -n "$EPOCH" ] && SRC="sntp pool.ntp.org"
  fi
fi

if [ -z "$EPOCH" ]; then
  say "=== 取时失败 ==="
  say "网络或 DNS 不通。请手动指定时间："
  say "  sudo bash $0 \"YYYY-MM-DD HH:MM:SS\""
  exit 2
fi

DELTA=$(( EPOCH - BEFORE ))
say "=== 取到网络时间（来源：$SRC）==="
say "utc   : $(date -u -d "@$EPOCH" '+%Y-%m-%d %H:%M:%S')"
if [ "$DELTA" -ge 0 ]; then
  say "差值  : 慢 $DELTA 秒（约 $((DELTA/3600)) 小时 $((DELTA%3600/60)) 分）"
else
  D=$(( -DELTA ))
  say "差值  : 快 $D 秒（约 $((D/3600)) 小时 $((D%3600/60)) 分）"
fi

if [ "$DELTA" -eq 0 ]; then
  say "已经准确，无需修改"; exit 0
fi
if [ "$DRY" -eq 1 ]; then
  say "[dry-run] 未修改。去掉 --dry-run 即会写入。"; exit 0
fi
if date -u -s "@$EPOCH"; then
  say "OK -> $(stamp)"
else
  say "FAIL：设置失败（需要 CAP_SYS_TIME，容器须为 --privileged）"; exit 1
fi