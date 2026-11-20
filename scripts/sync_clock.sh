#!/bin/bash
# 定时校时(cron 每5分钟): 从 HTTPS Date 头取网络时间, 漂移≥1s 才拨钟
# 依赖: /etc/sudoers.d/90-clock-sync 里的 date 免密; 代理 192.168.137.1:7897
export http_proxy="http://192.168.137.1:7897"
export https_proxy="http://192.168.137.1:7897"

NET_EPOCH="$(curl -sI -m 8 https://mirrors.tuna.tsinghua.edu.cn/ | awk '/^[Dd]ate:/ {print $0}' | tr -d '\r' | cut -d' ' -f2- | date -f - +%s 2>/dev/null)"
[ -z "${NET_EPOCH}" ] && exit 0

LOCAL_EPOCH="$(date +%s)"
DRIFT=$(( NET_EPOCH - LOCAL_EPOCH ))
if [ "${DRIFT#-}" -gt 0 ]; then
    sudo -n date -s "@${NET_EPOCH}" >/dev/null 2>&1 \
        && echo "$(date '+%F %T') synced, drift was ${DRIFT}s"
fi
exit 0
