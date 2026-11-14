#!/bin/bash
# 录制标定 bag：双目图像 + IMU（+磁力计），输出到 bags/ 并按时间戳命名
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
BAG_DIR="${PROJECT_ROOT}/bags"
mkdir -p "${BAG_DIR}"

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${BAG_DIR}/calib_${STAMP}.bag"

TOPICS=(
    /camera/left/image_raw
    /camera/right/image_raw
    /imu/data
    /imu/mag
)

echo "[record_calib_bag] 录制话题: ${TOPICS[*]}"
echo "[record_calib_bag] 输出文件: ${OUT}"
echo "[record_calib_bag] 按 Ctrl-C 停止录制"

cd "${BAG_DIR}"
exec rosbag record -O "${OUT}" "${TOPICS[@]}"
