#!/bin/bash
# =============================================================================
# imu_utils Allan 方差分析流程说明
# -----------------------------------------------------------------------------
# 目的: 标定 BMI088 的陀螺/加计噪声密度 (noise density) 与随机游走
#       (random walk)，填入 Kalibr 的 imu.yaml:
#           gyroscope_noise_density / gyroscope_random_walk
#           accelerometer_noise_density / accelerometer_random_walk
#
# 前置: vins_ws 中已 clone 并编译 imu_utils（含 code_utils）:
#           cd /workspace/vins_ws/src
#           git clone https://github.com/gaowenliang/code_utils.git
#           git clone https://github.com/gaowenliang/imu_utils.git
#           cd .. && catkin build
#       （code_utils 依赖 libdw-dev，镜像中已安装；注意先编 code_utils
#        再编 imu_utils，catkin 会自动处理顺序。）
#
# 步骤:
#   1. 整车断电静止放置于无振动台面，仅启动 IMU 节点:
#          roslaunch imu_bmi088_qmc5883p imu.launch
#   2. 录制至少 2 小时静止数据（100Hz，时间越长低频段越准）:
#          rosbag record -O bags/imu_allan.bag /imu/data --duration=2h
#   3. 编辑 imu_utils/launch/xxx_imu_calib.launch（以自带模板复制一份）:
#          imu_topic   = /imu/data
#          imu_name    = bmi088
#          data_save_path 指向输出目录
#          max_time_min  ≥ 120
#   4. 回放并分析:
#          roslaunch imu_utils bmi088_imu_calib.launch
#          rosbag play -r 200 bags/imu_allan.bag   # 加速回放
#      结束后在 data_save_path 生成 *_imu_param.yaml 与 .mat 数据。
#   5. 绘图: 用 imu_utils/scripts/matlab/draw_allan.m（需 MATLAB/Octave）
#      或 python + allantools 自行绘制 Allan 标准差曲线。
#      从曲线上读取: 白噪声段 τ=1s 处斜率 -1/2 的值为噪声密度 σ，
#      随机游走段斜率 +1/2 与 τ=3s 交点约为 σ_b。
#   6. 将结果填入 Kalibr 标定用的 imu.yaml（单位 SI: rad/s/√Hz 等）。
#
# 注意: imu_utils 分析的是原始 IMU 输出。若 gyro_bias.yaml 已被节点加载
#       补偿，录制 Allan bag 前请先移除该文件并重启节点，保持数据原始。
# =============================================================================
set -euo pipefail

echo "本脚本为流程说明，请用编辑器打开查看: $0"
echo "关键命令速查:"
echo "  rosbag record -O bags/imu_allan.bag /imu/data --duration=2h"
echo "  roslaunch imu_utils bmi088_imu_calib.launch"
echo "  rosbag play -r 200 bags/imu_allan.bag"
