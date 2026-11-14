# =============================================================================
# Orange Pi 3B (RK3566, ARM64) 阿克曼底盘小车 —— VINS-Fusion Docker 开发环境
# 镜像: vins-noetic:latest
#
# 基底说明: 首选的 osrf/ros:noetic-desktop 经查只有 amd64 单架构清单，
#           官方 ros 镜像又无 noetic-desktop tag，均无 ARM64 版，
#           故回退到 ubuntu:20.04 手搭 ROS（TUNA 源 + COPY ros.asc）。
# =============================================================================
FROM ubuntu:20.04

# 构建期代理（由 build.sh 透传宿主机 http_proxy/https_proxy）。
# ARG 只作用于构建过程，不会写进最终镜像的环境变量。
ARG http_proxy
ARG https_proxy
ARG no_proxy

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# ros.asc: ROS 官方 apt 仓库的 GPG key（维护者放入 docker/ros.asc），
# 用于 Step A 中把 TUNA 的 ROS 镜像源加入 apt 并校验签名。
COPY docker/ros.asc /tmp/ros.asc

# ---- Step A: 系统基础工具 ---------------------------------------------------
# ca-certificates 必须先走 HTTP 源安装（否则 HTTPS 源证书校验会失败），
# 装完后统一切换到清华 TUNA HTTPS 源；ROS 仓库使用 TUNA 镜像 + ros.asc 验签。
RUN sed -i \
        -e 's|https\?://archive.ubuntu.com/ubuntu|http://mirrors.tuna.tsinghua.edu.cn/ubuntu|g' \
        -e 's|https\?://security.ubuntu.com/ubuntu|http://mirrors.tuna.tsinghua.edu.cn/ubuntu|g' \
        -e 's|https\?://ports.ubuntu.com/ubuntu-ports|http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports|g' \
        /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates gnupg \
 && apt-key add /tmp/ros.asc \
 && echo "deb https://mirrors.tuna.tsinghua.edu.cn/ros/ubuntu focal main" \
        > /etc/apt/sources.list.d/ros1-latest.list \
 && sed -i 's|http://mirrors.tuna.tsinghua.edu.cn|https://mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        git vim build-essential cmake \
        i2c-tools v4l-utils can-utils \
 && rm -rf /var/lib/apt/lists/*

# ---- Step ROS: 安装 ROS Noetic desktop（TUNA 镜像源） ------------------------
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ros-noetic-desktop python3-rosdep \
 && rm -rf /var/lib/apt/lists/*

# ---- Step B: VINS-Fusion 依赖 ----------------------------------------------
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libceres-dev libeigen3-dev libopencv-dev \
        libgoogle-glog-dev libatlas-base-dev \
        python3-catkin-tools \
        ros-noetic-cv-bridge ros-noetic-tf ros-noetic-message-filters \
 && rm -rf /var/lib/apt/lists/*

# ---- Step C: 标定工具链依赖 (Kalibr / imu_utils) ----------------------------
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3-scipy python3-matplotlib python3-pandas python3-igraph \
        python3-numpy \
        ros-noetic-image-transport ros-noetic-camera-info-manager \
        libdw-dev \
 && rm -rf /var/lib/apt/lists/*

# ---- Step D: 网络/工具小件 + pip (TUNA PyPI 源) -----------------------------
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        net-tools htop iputils-ping python3-pip \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m pip install --upgrade \
        -i https://pypi.tuna.tsinghua.edu.cn/simple pip \
 && printf '[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\n' \
        > /etc/pip.conf \
 && python3 -m pip install smbus2 rospkg pyyaml

# ---- Step E: rosdep ---------------------------------------------------------
# rosdep update 依赖 GitHub raw 资源，构建机上若无外网可能失败；
# 失败不阻塞构建（容器内可挂代理后重跑）。
RUN rosdep init 2>/dev/null || true \
 && rosdep update || echo "[WARN] rosdep update 失败, 可进入容器后重跑"

# ---- 普通用户: 与宿主持平 ----------------------------------------------------
ARG USER_NAME=ubuntu
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd -f i2c \
 && (getent group "${USER_GID}" >/dev/null || groupadd -g "${USER_GID}" "${USER_NAME}") \
 && useradd -m -u "${USER_UID}" -g "${USER_GID}" -s /bin/bash "${USER_NAME}" \
 && usermod -aG sudo,dialout,plugdev,video,i2c "${USER_NAME}" \
 && echo "${USER_NAME} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${USER_NAME}" \
 && chmod 0440 "/etc/sudoers.d/${USER_NAME}"

# ---- 统一入口: source ROS 环境后 exec 传入命令 -------------------------------
RUN printf '#!/bin/bash\nset -e\nsource /opt/ros/noetic/setup.bash\nexec "$@"\n' \
        > /usr/local/bin/ros_entrypoint.sh \
 && chmod +x /usr/local/bin/ros_entrypoint.sh

USER ${USER_NAME}
RUN echo 'source /opt/ros/noetic/setup.bash' >> "${HOME}/.bashrc" \
 && echo 'cd /workspace/vins_ws 2>/dev/null || cd /workspace 2>/dev/null || true' \
        >> "${HOME}/.bashrc"

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/ros_entrypoint.sh"]
CMD ["bash"]
