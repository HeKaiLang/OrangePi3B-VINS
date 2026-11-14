#!/bin/bash
# 启动 vins-noetic 容器（RK3566 无 NVIDIA，不含 GPU/TurtleBot3/WSL2 逻辑）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

IMAGE_NAME="vins-noetic:latest"
CONTAINER_NAME="${1:-vins-noetic-container}"

USER_UID="$(id -u)"
USER_GID="$(id -g)"

# 已存在同名容器则直接复用（保留容器内改动，不使用 --rm）
if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
    echo "[run.sh] 复用已存在容器: ${CONTAINER_NAME}"
    docker start -ai "${CONTAINER_NAME}"
    exit 0
fi

DOCKER_ARGS=(
    --name "${CONTAINER_NAME}"
    --user "${USER_UID}:${USER_GID}"
    --env "USER=${USER}"
    --env "HOME=/home/${USER}"
    --network host
    --privileged
    -v "${PROJECT_ROOT}:/workspace:rw"
    -v /dev:/dev
    -v /etc/localtime:/etc/localtime:ro
    -w /workspace
)

# X11 转发（rviz / rqt 等 GUI）
if [ -n "${DISPLAY:-}" ]; then
    xhost +local:docker >/dev/null 2>&1 || true
    DOCKER_ARGS+=(
        -e DISPLAY="${DISPLAY}"
        -e QT_X11_NO_MITSHM=1
        -e LIBGL_ALWAYS_SOFTWARE=1
        -e QT_QPA_PLATFORM=xcb
        -v /tmp/.X11-unix:/tmp/.X11-unix:rw
    )
fi

docker run -it "${DOCKER_ARGS[@]}" "${IMAGE_NAME}"
