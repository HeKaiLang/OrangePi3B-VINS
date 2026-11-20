#!/bin/bash
# 断电重启后的一键启动: docker 容器 + 单个 tmux 会话跑 stream_calib.launch
# 用法: ./scripts/start_robot_stream.sh [width height]
#   标定档(默认): 2160 1080 (单目1080x1080@~10fps)
#   运行档:       1280  480 (单目 640x480@30fps, 任务E/上车用)
set -euo pipefail

CONTAINER=vins-noetic-container
ENV='export ROS_IP=192.168.10.3 ROS_MASTER_URI=http://192.168.10.3:11311; source /opt/ros/noetic/setup.bash; source /workspace/vins_ws/devel/setup.bash'
WIDTH="${1:-2160}"
HEIGHT="${2:-1080}"

echo "[1/4] 启动 docker 容器..."
docker start "${CONTAINER}"
sleep 3
docker exec "${CONTAINER}" tmux kill-server 2>/dev/null || true

echo "[2/4] 清理可能残留的 launch 实例 (防双开互杀)..."
docker exec "${CONTAINER}" bash -c "pkill -f '[s]tream_calib' 2>/dev/null; sleep 1; true"
docker exec "${CONTAINER}" bash -c "pkill -f '[r]oslaunch' 2>/dev/null; sleep 1; true"

echo "[3/4] 启动推流 launch ${WIDTH}x${HEIGHT} (imu+stereo+压缩, 单master)..."
docker exec "${CONTAINER}" tmux new-session -d -s stream "${ENV}; roslaunch stereo_camera stream_calib.launch width:=${WIDTH} height:=${HEIGHT}; exec bash"

echo "[4/4] 等待就绪并验证..."
sleep 18
docker exec "${CONTAINER}" bash -c "${ENV}; rostopic list | grep -E 'compressed$|imu/data'"
echo ""
echo "看频率: docker exec -it ${CONTAINER} bash -c 'rostopic hz /camera/left/compressed'"
echo "PC 侧: export ROS_MASTER_URI=http://192.168.10.3:11311 ROS_IP=192.168.137.1"
echo "档位: ${WIDTH}x${HEIGHT}"
