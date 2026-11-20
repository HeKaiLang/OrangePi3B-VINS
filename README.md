# Radar_duoCamera — Orange Pi 3B 阿克曼底盘小车 VINS-Fusion 工作区

硬件平台：Orange Pi 3B（RK3566, ARM64, Ubuntu 22.04 宿主机）
传感器：UVC 双目同步相机（side-by-side 拼帧；3840x1080 实测仅 ~10fps 为固件上限；
RK3566 解码算力下采用 1280x480 档 = 单目原生 640x480@30fps 作为 VINS 工作分辨率；
标定录 bag 时可用 2160x1080 档（单目 1080x1080，管线 ~13fps，Kalibr 够用），基线 60mm）、
BMI088 IMU + QMC5883P 罗盘（i2c-2）、ESP32 阿克曼底盘（不进 Docker）

## 目录结构

```
docker/          Docker 构建与启动
  Dockerfile     vins-noetic 镜像（osrf/ros:noetic-desktop, ARM64）
  build.sh       构建脚本
  run.sh         启动脚本（X11 转发，--privileged，挂 /dev）
  ros.asc        ROS GPG key（备用：基础镜像拉取失败时手搭 ROS 用）
src/
  imu_bmi088_qmc5883p/   IMU 驱动包（/imu/data, /imu/mag, 100Hz）
  stereo_camera/         UVC 双目拆帧包（/camera/left|right/image_raw）
scripts/
  record_calib_bag.sh    录标定 bag（双目图像 + IMU）
  imu_static_calib.py    静止 30s 零偏标定 → calibration/*.yaml
  run_allan_variance.sh  imu_utils Allan 方差流程说明
bags/            rosbag 输出
calibration/     标定结果（gyro_bias.yaml / acc_bias.yaml / Kalibr 输出）
```

注意：I2C 地址为 BMI088 `0x19/0x69`、QMC5883P `0x2c`，**不是**常见的
`0x18/0x68/0x0d`。传感器安装为 y 轴朝天、z 轴朝车尾，驱动节点内部已做
`(xb,yb,zb)=(-zi,-xi,yi)` 映射到 ROS FLU 系。

## 首次使用

```bash
# 1. 构建镜像（约需拉取 ARM64 noetic-desktop，建议挂代理）
./docker/build.sh

# 2. 启动容器（第二次起复用同一容器）
./docker/run.sh

# 3. 容器内编译 catkin 工作空间（项目根即 /workspace）
cd /workspace
mkdir -p vins_ws
ln -sfn /workspace/src vins_ws/src
cd vins_ws && catkin build
source devel/setup.bash

# 4. 验证 IMU 节点
roslaunch imu_bmi088_qmc5883p imu.launch
# 另开终端进容器: docker exec -it vins-noetic-container bash
rostopic hz /imu/data        # 应约 100Hz
rostopic echo /imu/mag -n 1

# 5. 验证双目节点
roslaunch stereo_camera stereo.launch   # 默认发布 640x480
rostopic hz /camera/left/image_raw      # 应约 30Hz

# 6. 静止标定陀螺零偏（整车静止，先删旧 gyro_bias.yaml 再重启 IMU 节点）
python3 /workspace/scripts/imu_static_calib.py

# 7. 录标定 bag（图像 + IMU）
./scripts/record_calib_bag.sh
```

## 后续 Kalibr 标定注意事项

- **相机模型**：80° 视场角属广角，推荐 `pinhole-equi`（pinhole 投影 +
  equidistant 畸变）；普通 `pinhole-radtan` 在边缘拟合会差。
- **标定板**：Aprilgrid 打印后贴刚性平整底板（KT 板/铝塑板），卷尺实测
  tag 边长填入 yaml，打印缩放误差会直接传染到尺度和外参。
- **imu.yaml 噪声参数**：不要照抄模板，用 `scripts/run_allan_variance.sh`
  的流程跑 2 小时静止数据出 Allan 方差，再填噪声密度/随机游走。
- **激励方式**：camera-IMU 联合标定时手持小车在标定板前做全 6 自由度
  激励（三轴平移 + 三轴旋转），每个轴都要有充分角速度，动作慢而平滑，
  标定板尽量占画面 1/3 以上，避免运动模糊（可降曝光、补光）。
- **时间同步**：UVC 相机与 IMU 都是上位机打时间戳，存在固定偏移；Kalibr
  标定加 `--time-calibration` 估计时间偏移，VINS-Fusion 配置里填回
  `td`。
- **双目外参**：基线标称 60mm，Kalibr 双目标定结果若偏离超过几 mm 要
  检查拼帧左右是否接反、是否有单帧丢半边。
- **录 bag 帧率**：标定 bag 不必 30Hz 全采，10~20Hz 足够且体积小；可用
  launch 参数降采样或 `rosrun topic_tools throttle`。
- **VINS-Fusion 配置**：`estimate_td` 建议先开；`body` 到 `cam` 外参用
  Kalibr 结果；IMU 噪声参数用 Allan 结果（给 VINS 时适当放大 5~10 倍
  提高鲁棒性）。

## 常用命令

```bash
docker exec -it vins-noetic-container bash   # 再开一个容器终端
v4l2-ctl --list-formats-ext -d /dev/video0   # 查相机支持的格式
i2cdetect -y 2                                # 应看到 19 69 2c
rosbag info bags/calib_*.bag
```
