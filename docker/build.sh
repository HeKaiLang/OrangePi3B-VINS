#!/bin/bash
# 构建 vins-noetic:latest 镜像（BuildKit，用户三件套与宿主持平）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

USER_NAME="$(id -un)"
USER_UID="$(id -u)"
USER_GID="$(id -g)"

export DOCKER_BUILDKIT=1

# 透传宿主机代理到构建过程（容器内 DNS 不通，apt/pip 需走代理）
PROXY_ARGS=()
for v in http_proxy https_proxy no_proxy; do
    if [ -n "${!v:-}" ]; then
        PROXY_ARGS+=(--build-arg "${v}=${!v}")
    fi
done

docker build \
    --tag vins-noetic:latest \
    --build-arg USER_NAME="${USER_NAME}" \
    --build-arg USER_UID="${USER_UID}" \
    --build-arg USER_GID="${USER_GID}" \
    "${PROXY_ARGS[@]}" \
    -f "${SCRIPT_DIR}/Dockerfile" \
    "${PROJECT_ROOT}"

echo ""
echo "[build.sh] 构建完成。查看镜像:"
echo "    docker images | grep vins-noetic"
echo "[build.sh] 启动容器:"
echo "    ${SCRIPT_DIR}/run.sh            # 默认容器名 vins-noetic-container"
echo "    ${SCRIPT_DIR}/run.sh my-vins    # 自定义容器名"
