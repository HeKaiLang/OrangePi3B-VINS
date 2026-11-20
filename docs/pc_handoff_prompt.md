# PC 端标定环境交接 Prompt（WSL2 Ubuntu 22.04）

> 本文件是给 PC 端 AI 编码助手（或你自己）的任务交接书。
> 嵌入式侧（Orange Pi 3B）已完成：传感器驱动、IMU 噪声标定、标定数据录制。
> 从现在起所有标定计算在 PC 完成。

---

## 背景

为 Orange Pi 3B（RK3566, ARM64）阿克曼小车的 VINS-Fusion 双目 SLAM 做标定。
传感器：UVC 双目拼帧相机（side-by-side，弱光注意补光，标定档 2160x1080 =
单目 1080x1080@~13fps，运行档 1280x480 = 单目原生 640x480@30fps，基线 60mm，
FOV 100°）；BMI088+QMC5883P IMU（i2c-2，100Hz，FLU 坐标系，y 轴朝天 z 轴朝车尾）。
双目话题：/camera/left/image_raw、/camera/right/image_raw；IMU：/imu/data。
左右拆分为 frame[:, :w/2] / frame[:, w/2:]，左右归属已在 640x480 档验证无误。

## 数据获取（从香橙派拷贝，二选一）

```bash
# 方式1: PC 直连路由/交换机时
scp -r org3b-of-c@<派IP>:~/Radar_duoCamera/{bags,calibration,scripts} ~/
# 方式2: 派经 Zero3-ICS 链路时 IP 为 192.168.137.193
scp -r org3b-of-c@192.168.137.193:~/Radar_duoCamera/{bags,calibration,scripts} ~/
```

关键文件：
- `bags/imu_allan_v2.bag` —— 2h 静止陀螺数据（100Hz，260MB），陀螺噪声参数来源
- `bags/imu_allan.bag` —— 2h 静止加计数据（同上），加计噪声参数来源
- `calibration/imu.yaml` —— **已终审的 Kalibr 格式 IMU 噪声参数，直接用，勿重算**
- 后续会追加相机标定 bag（届时用同样方式拷贝）

## 任务 A：搭建标定环境（现在做）

PC 已有现成 ROS Noetic 容器 `wsr-ros-noetic-container`（amd64, WSL2），**直接复用，
不要新建镜像**。（注: Kalibr 不能直接在 22.04 跑——Noetic 只发布到 20.04，
22.04 需源码编 ROS+大量补丁, 不值得; 20.04 容器是标准解法。）

```bash
docker start -ai wsr-ros-noetic-container

# —— 容器内 ——
sudo apt-get update && sudo apt-get install -y --no-install-recommends \
  git wget python3-catkin-tools libeigen3-dev libboost-all-dev \
  libsuitesparse-dev libopencv-dev python3-igraph python3-scipy \
  python3-matplotlib python3-wxgtk4.0 python3-pyx libpoco-dev \
  libtbb-dev libblas-dev liblapack-dev libv4l-dev doxygen python3-dev

mkdir -p ~/kalibr_ws/src && cd ~/kalibr_ws
catkin init
catkin config --extend /opt/ros/noetic --cmake-args -DCMAKE_BUILD_TYPE=Release
git clone --depth 1 https://github.com/ethz-asl/kalibr.git src/kalibr
catkin build -j$(nproc)      # 若 WSL2 内存少导致 OOM 则降为 -j4
```

验证容器内三个可执行文件存在：
`kalibr_calibrate_cameras` / `kalibr_calibrate_imu_camera` / `kalibr_allan_variance`
（在 ~/kalibr_ws/devel/lib/kalibr 下，catkin build 成功即有）。

工作目录放 WSL2 原生文件系统（`~/`，勿放 /mnt/c，IO 慢一个数量级）。
bag 等数据文件通过 docker cp 或共享目录挂进容器均可。

## 任务 B：陀螺随机游走终审交叉验证（现在做）

背景：imu_utils 不给随机游走；自研拟合脚本 `scripts/allan_fit.py`（随 bags 提供）
给出陀螺 RW=2.3e-6 rad/s²/√Hz，但 σ(τ) 曲线没有干净的 +1/2 段，此值置信度中等。
做法：容器内对 `imu_allan_v2.bag` 跑 `allan_variance_ros`（ori-drs 社区实现；注意其
陀螺通道有刻度缺陷，输出仅作上界参考），对比其 gyro RW 与 2.3e-6：
- 【已执行 2026-11-17】工具输出 2.4e-5（判为缺陷产物不采纳）；PC 直接复算 2.1e-6；
  人工终审签认：维持 `calibration/imu.yaml` 的 2.3e-6。

## 任务 C：生成 Aprilgrid 标定板 PDF（现在做）

```bash
kalibr_create_target_pdf --type apriltag \
  --nx 6 --ny 8 --tsize 0.08 --tspace 0.3
```
（行列/尺寸可按打印纸调整；生成 PDF 后告诉我参数，我去打印并实测 tag 尺寸回填。）

## 任务 D：相机标定（等相机 bag 到位后做）

前置：录制规范 = 标定档 2160x1080 手持全 6 自由度激励 1-2 分钟，
标定板占画面 1/3 以上、动作慢、补光防糊。

```bash
kalibr_calibrate_cameras \
  --bag calib_cam.bag \
  --topics /camera/left/image_raw /camera/right/image_raw \
  --models pinhole-equi pinhole-equi \
  --target aprilgrid.yaml
```
验收点：基线应 ≈60mm（偏差 >1cm 先怀疑左右反/板不平）；出 PDF report 存 calibration/。

## 任务 E：相机-IMU 联合标定（D 之后）

```bash
kalibr_calibrate_imu_camera \
  --bag calib_imucam.bag \        # 运行档 1280x480 录制, 旋转激励为主, 2-3 分钟
  --cam camchain-*.yaml \         # D 的结果
  --imu calibration/imu.yaml \
  --target aprilgrid.yaml \
  --time-calibration
```
产出 T_cam_imu 与时间偏移 td → 翻译成 VINS-Fusion stereo 配置（分辨率从 1080 换算
到 640x480：fx/fy/cx/cy 乘 640/1080 的相应轴向缩放，畸变系数不变；噪声参数按
imu.yaml 字面量，VINS 实战建议放大 5-10 倍）。

## 硬约束与已踩过的坑（务必遵守）

1. **`calibration/imu.yaml` 是终审值，不要拿 imu_utils 的原始输出覆盖它**
   （imu_utils 的 noise_density 是每样本 σ_sample=密度×√f，Kalibr 要连续密度，
   差 √100=10 倍；网上教程多数填错）。
2. 相机模型必须用 `pinhole-equi`（100° FOV，radtan 边缘拟合不够）。
3. Aprilgrid 的 tag 实际尺寸必须打印后实测回填，A4 打印缩放误差直接变成尺度误差。
4. 派上的 `imu_bmi088_qmc5883p` / `stereo_camera` 驱动已完成联调，PC 端不要改动
   嵌入式代码；发现数据问题反馈回来改。
5. WSL2 内跑 GUI（rviz/看图）用 WSLg（Win11 自带 DISPLAY）；纯离线标定不需要 GUI。

## 交付物清单

- [ ] kalibr:noetic 镜像可用（任务A）
- [ ] 交叉验证后的定稿 `imu.yaml`（任务B）
- [ ] aprilgrid PDF + 参数文件（任务C）
- [ ] 相机链 yaml + PDF report（任务D）
- [ ] imucam 外参 + td + VINS stereo_config.yaml（任务E）

---

# 补充（2026-11-17 下午）：网络化标定方案（替代任务D/E的"派上录bag+scp"流程）

## 网络拓扑与 ROS 多机配置

PC(192.168.137.1) —网线— 中继节点(192.168.137.250 / 192.168.10.4) —IBSS+batman mesh— 小车(192.168.10.3)。
PC↔小车已互通, iperf 实测 ~95Mbps(PC→小车方向)。

**PC 侧环境变量**（每个工作 shell 都要）：
```bash
export ROS_MASTER_URI=http://192.168.10.3:11311   # master 在小车容器内
export ROS_IP=192.168.137.1                        # PC 对小车可达的地址
```
PC 自己的 roscore 停用（或仅作备用），避免双 master 混乱。

## 小车侧已部署（单 launch 单 tmux 会话, 一键脚本 scripts/start_robot_stream.sh）

- 容器 `vins-noetic-container` 内唯一 tmux 会话 `stream`，跑
  `roslaunch stereo_camera stream_calib.launch`（imu + 双目标定档 + 双路JPEG压缩,
  roslaunch 自建单 master, 无 run_id 冲突; 质量60 实测 0.16MB/帧 ≈ 11Mbps/路）
- 断电重启后只需在派上执行 `~/Radar_duoCamera/scripts/start_robot_stream.sh`
- **话题名注意**：压缩流是 `/camera/left/compressed`、`/camera/right/compressed`
- 任务E前: 改启动脚本/launch 参数切运行档 1280x480
- 依赖: ros-noetic-compressed-image-transport（PC 端 republish/看图也要装）

## PC 侧操作（任务D录制 + 实时看图）

```bash
docker start -ai wsr-ros-noetic-container
source /opt/ros/noetic/setup.bash && source ~/kalibr_ws/devel/setup.bash
export ROS_MASTER_URI=http://192.168.10.3:11311 ROS_IP=192.168.137.1
rostopic hz /camera/left/compressed     # 验证连通

# 实时看图（防标定板出画）:
rqt_image_view    # 选 /camera/left/compressed

# 录制 kalibr 可用 bag（PC 就地压缩转raw, 保时间戳）:
rosrun image_transport republish compressed in:=/camera/left  raw out:=/pc/left  __name:=pc_repub_l &
rosrun image_transport republish compressed in:=/camera/right raw out:=/pc/right __name:=pc_repub_r &
rosbag record -O calib_cam.bag /pc/left /pc/right /imu/data --duration=90
```

kalibr 命令对应 `--topics /pc/left /pc/right`。

## 标定板参数更新（任务C产物作废重生成或改yaml）

新版板：A4 打印, 6列x8行, **tagSize 0.022**, tagSpacing 0.3（间距6.6mm）, 实测无误差。
→ PC 端 aprilgrid.yaml 的 tagSize 从 0.08 改为 0.022 即可。
**板小(22mm tag) → 工作距离拉近到 0.2~0.5m**, 平移幅度相应缩到 10~15cm,
动作仍要覆盖画面中央/四边/倾斜各姿态。

---

# 补充（2026-11-17 晚）：任务 E 事故与整改

## 事故
首录 calib_imucam.bag 失败（重投影 20px / td 秒级 / 平移 0.6m）。
根因：over-mesh 录制时 rosbag 用 PC 到达时刻打戳，mesh WiFi 延迟尖峰使
IMU 相邻样本间隔失真，预积分被带飞；叠加当时派上存在运行期校时跳变。
**常数偏移无害，跳变/抖动致命。**

## 已整改（派端，已执行）
删除校时 cron；chronyd kill + disable（它是 17:26 被手动拉起的，无 NTP 源，
但属隐患）；核实无其他校时组件（无 30s timer、无 timesyncd）。
校时改为"启动时一次性"：~/Radar_duoCamera/scripts/fix_clock.sh 手动执行。
录制期间派时钟自由光滑漂移。本地监控确认无周期性跳钟。

## 任务 E 录制流程（不变，坚持走 mesh）
PC 端 republish(compressed→raw) + rosbag record 与之前完全相同。

## 新增：洗袋步骤（cook, PC 端, kalibr 前必做）
用 cookbag.py（Allan 分析用过的同款）把 bag 内每个消息的 bag-time 重写为
其 header.stamp（小车时钟，已确认光滑）。产物如 calib_imucam_cooked.bag。
洗后自检：IMU 相邻 dt 应 ≈0.01s、方差极小、无负值尖刺，再给
kalibr_calibrate_imu_camera。
