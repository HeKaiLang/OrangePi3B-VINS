#!/usr/bin/env python3
"""IMU 静止零偏标定：采集 30 秒数据，输出陀螺/加速度零偏与方差。

前提: IMU 节点已在运行（roslaunch imu_bmi088_qmc5883p imu.launch），
且整车保持绝对静止。

输出:
  calibration/gyro_bias.yaml   陀螺零偏（均值/方差，FLU 系 rad/s）
                               imu_node 启动时自动读取并在发布前扣除
  calibration/acc_bias.yaml    加速度零偏（均值/方差，FLU 系 m/s^2，
                               z 轴已扣除重力 g，仅供分析参考）

注意: 标定前请删除（或移走）旧的 calibration/gyro_bias.yaml 并重启
imu_node，否则节点已在补偿旧零偏，本次测得的均值会接近 0。

Allan 方差提示:
  本脚本的 30s 采样只够估零偏。Allan 方差（噪声密度/随机游走，Kalibr
  的 imu.yaml 需要）需静止录制约 2 小时数据后用 imu_utils 分析：
    1. 录 bag:  rosbag record -O bags/imu_allan.bag /imu/data --duration=2h
    2. 编译 imu_utils（含 code_utils，依赖 libdw-dev，镜像已装）
    3. 修改 imu_utils/launch 中 imu_topic 为 /imu/data、采样率 100Hz
    4. roslaunch imu_utils imu_utils.launch 后运行 matlab 脚本
       draw_allan.m（或 python 的 allantools）读 mat 文件出图
  详细步骤见 scripts/run_allan_variance.sh。
"""

import os
import sys
import time

import numpy as np
import rospy
import yaml
from sensor_msgs.msg import Imu

G = 9.80665
DURATION_S = 30.0


def main():
    rospy.init_node('imu_static_calib', anonymous=True)
    duration = float(rospy.get_param('~duration', DURATION_S))
    out_dir = rospy.get_param('~out_dir', '/workspace/calibration')
    os.makedirs(out_dir, exist_ok=True)

    gyro_samples = []
    acc_samples = []

    def cb(msg):
        gyro_samples.append((msg.angular_velocity.x,
                             msg.angular_velocity.y,
                             msg.angular_velocity.z))
        acc_samples.append((msg.linear_acceleration.x,
                            msg.linear_acceleration.y,
                            msg.linear_acceleration.z))

    rospy.Subscriber('/imu/data', Imu, cb, queue_size=1000)

    rospy.loginfo('开始静止采样 %.0f 秒，请勿触碰小车...', duration)
    t0 = time.time()
    while time.time() - t0 < duration and not rospy.is_shutdown():
        time.sleep(0.5)

    if len(gyro_samples) < 100:
        rospy.logerr('样本过少 (%d)，请确认 /imu/data 正在发布', len(gyro_samples))
        sys.exit(1)

    gyro = np.asarray(gyro_samples)
    acc = np.asarray(acc_samples)

    gyro_mean = gyro.mean(axis=0)
    gyro_var = gyro.var(axis=0)
    acc_mean = acc.mean(axis=0)
    acc_var = acc.var(axis=0)
    # 加速度 z 轴（FLU）含重力，零偏 = 均值 - 重力
    acc_bias = acc_mean.copy()
    acc_bias[2] -= G

    stamp = time.strftime('%Y-%m-%d %H:%M:%S')
    n = len(gyro_samples)

    gyro_yaml = {
        'created': stamp,
        'duration_s': duration,
        'samples': int(n),
        'frame': 'FLU body frame, rad/s',
        'gyro_bias_rad_per_s': {'x': float(gyro_mean[0]),
                                'y': float(gyro_mean[1]),
                                'z': float(gyro_mean[2])},
        'gyro_var_rad2_per_s2': {'x': float(gyro_var[0]),
                                 'y': float(gyro_var[1]),
                                 'z': float(gyro_var[2])},
    }
    acc_yaml = {
        'created': stamp,
        'duration_s': duration,
        'samples': int(n),
        'frame': 'FLU body frame, m/s^2, z 已扣除 g=%.5f' % G,
        'acc_bias_m_per_s2': {'x': float(acc_bias[0]),
                              'y': float(acc_bias[1]),
                              'z': float(acc_bias[2])},
        'acc_mean_m_per_s2': {'x': float(acc_mean[0]),
                              'y': float(acc_mean[1]),
                              'z': float(acc_mean[2])},
        'acc_var_m2_per_s4': {'x': float(acc_var[0]),
                              'y': float(acc_var[1]),
                              'z': float(acc_var[2])},
    }

    gyro_path = os.path.join(out_dir, 'gyro_bias.yaml')
    acc_path = os.path.join(out_dir, 'acc_bias.yaml')
    with open(gyro_path, 'w') as f:
        yaml.safe_dump(gyro_yaml, f, allow_unicode=True, sort_keys=False)
    with open(acc_path, 'w') as f:
        yaml.safe_dump(acc_yaml, f, allow_unicode=True, sort_keys=False)

    print('\n===== 静止标定结果（%d 样本 / %.0fs）=====' % (n, duration))
    print('陀螺零偏 [rad/s]  x=%+.6f y=%+.6f z=%+.6f' % tuple(gyro_mean))
    print('陀螺方差          x=%.3e y=%.3e z=%.3e' % tuple(gyro_var))
    print('加计零偏 [m/s^2]  x=%+.5f y=%+.5f z=%+.5f' % tuple(acc_bias))
    print('已写入:\n  %s\n  %s' % (gyro_path, acc_path))
    print('\n重启 imu_node 后零偏补偿生效。')
    print('提示: Kalibr 的 imu.yaml 需要 Allan 方差参数，')
    print('      请静止录制约 2 小时 bag 后用 imu_utils 分析，')
    print('      流程见 scripts/run_allan_variance.sh。')


if __name__ == '__main__':
    main()
