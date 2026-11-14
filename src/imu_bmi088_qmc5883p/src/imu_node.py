#!/usr/bin/env python3
"""BMI088 IMU + QMC5883P 罗盘 ROS 驱动节点 (Orange Pi 3B, /dev/i2c-2, smbus2)。

I2C 地址（注意与常见默认不同）:
  BMI088   加速度计 0x19 / 陀螺仪 0x69   (不是 0x18/0x68)
  QMC5883P 罗盘    0x2c                  (不是 0x0d)

传感器安装: y 轴朝天, z 轴朝车尾。
发布前统一做 (xb, yb, zb) = (-zi, -xi, yi) 映射到 ROS FLU (x 前, y 左, z 上)。

话题:
  /imu/data  sensor_msgs/Imu            frame_id=imu_link, 100Hz
  /imu/mag   sensor_msgs/MagneticField  (可选, ~publish_mag)

零偏补偿:
  启动时读取 ~gyro_bias_file (默认 /workspace/calibration/gyro_bias.yaml),
  若存在则在发布前扣除陀螺零偏 (FLU 机体系, rad/s)。
  标定流程见 scripts/imu_static_calib.py。
"""

import math
import os
import struct
import time

import rospy
import yaml
from sensor_msgs.msg import Imu, MagneticField
from smbus2 import SMBus

G = 9.80665
DEG2RAD = math.pi / 180.0

BMI088_ACC_ADDR = 0x19
BMI088_GYRO_ADDR = 0x69
QMC5883P_ADDR = 0x2C

# BMI088 加速度计寄存器
ACC_PWR_CONF = 0x7C   # 电源配置: 0x00 = active（BMI088 上电默认 suspend, 必须显式唤醒）
ACC_PWR_CTRL = 0x7D   # 0x04 = 加速度计使能
ACC_RANGE = 0x41      # 0x01 = ±6g
ACC_DATA = 0x12       # 加速度数据起始寄存器（6 字节, 小端 int16: x, y, z）

# BMI088 陀螺仪寄存器
GYRO_ENABLE = 0x15    # 写 0x00 使能（按项目约定）
GYRO_RANGE = 0x0F     # 0x00 = ±2000 dps
GYRO_DATA = 0x02      # 角速度数据起始寄存器（6 字节, 小端 int16: x, y, z）

# QMC5883P 寄存器
QMC_SOFT_RESET = 0x0B  # 0x01 = 软复位（按项目约定）
QMC_MODE = 0x0A        # 0xC0 = 连续测量模式（按项目约定）
QMC_DATA = 0x01        # 磁场数据起始寄存器（6 字节, 小端 int16: x, y, z）

ACC_SENS = 5460.0    # LSB/g   @ ±6g
GYRO_SENS = 16.384   # LSB/dps @ ±2000dps


def to_flu(xi, yi, zi):
    """传感器安装系 → ROS FLU: (xb, yb, zb) = (-zi, -xi, yi)。"""
    return -zi, -xi, yi


class ImuNode:
    def __init__(self):
        self.i2c_bus = int(rospy.get_param('~i2c_bus', 2))
        self.rate_hz = float(rospy.get_param('~rate', 100.0))
        self.frame_id = rospy.get_param('~frame_id', 'imu_link')
        self.publish_mag = bool(rospy.get_param('~publish_mag', True))
        # QMC5883P 灵敏度与量程设置相关, 默认 3000 LSB/G, 请按数据手册核对
        self.mag_lsb_per_gauss = float(rospy.get_param('~mag_lsb_per_gauss', 3000.0))
        bias_file = rospy.get_param('~gyro_bias_file',
                                    '/workspace/calibration/gyro_bias.yaml')
        self.gyro_bias = self._load_gyro_bias(bias_file)

        self.bus = SMBus(self.i2c_bus)
        self._init_bmi088()
        self.mag_ok = False
        if self.publish_mag:
            try:
                self._init_qmc5883p()
                self.mag_ok = True
            except OSError as exc:
                rospy.logwarn('QMC5883P 初始化失败 (%s), 跳过 /imu/mag', exc)

        self.pub_imu = rospy.Publisher('/imu/data', Imu, queue_size=100)
        self.pub_mag = rospy.Publisher('/imu/mag', MagneticField, queue_size=100)

    @staticmethod
    def _load_gyro_bias(path):
        if not os.path.exists(path):
            rospy.loginfo('未找到 %s, 不做陀螺零偏补偿', path)
            return (0.0, 0.0, 0.0)
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        bias = data.get('gyro_bias_rad_per_s', data)
        if isinstance(bias, dict):
            out = (float(bias['x']), float(bias['y']), float(bias['z']))
        else:
            out = tuple(float(v) for v in bias[:3])
        rospy.loginfo('加载陀螺零偏 %s: %s', path, out)
        return out

    def _init_bmi088(self):
        # 加速度计: 唤醒 → 使能 → 量程 ±6g
        self.bus.write_byte_data(BMI088_ACC_ADDR, ACC_PWR_CONF, 0x00)
        time.sleep(0.05)
        self.bus.write_byte_data(BMI088_ACC_ADDR, ACC_PWR_CTRL, 0x04)
        time.sleep(0.05)
        self.bus.write_byte_data(BMI088_ACC_ADDR, ACC_RANGE, 0x01)
        # 陀螺仪: 使能 → 量程 ±2000dps
        self.bus.write_byte_data(BMI088_GYRO_ADDR, GYRO_ENABLE, 0x00)
        self.bus.write_byte_data(BMI088_GYRO_ADDR, GYRO_RANGE, 0x00)
        time.sleep(0.01)
        rospy.loginfo('BMI088 初始化完成 (acc ±6g, gyro ±2000dps)')

    def _init_qmc5883p(self):
        self.bus.write_byte_data(QMC5883P_ADDR, QMC_SOFT_RESET, 0x01)
        time.sleep(0.05)
        self.bus.write_byte_data(QMC5883P_ADDR, QMC_MODE, 0xC0)
        time.sleep(0.01)
        rospy.loginfo('QMC5883P 初始化完成 (连续模式)')

    def _read_s16x3(self, addr, reg):
        raw = self.bus.read_i2c_block_data(addr, reg, 6)
        return struct.unpack('<hhh', bytes(raw))

    def spin(self):
        rate = rospy.Rate(self.rate_hz)
        while not rospy.is_shutdown():
            try:
                ax, ay, az = self._read_s16x3(BMI088_ACC_ADDR, ACC_DATA)
                gx, gy, gz = self._read_s16x3(BMI088_GYRO_ADDR, GYRO_DATA)
            except OSError as exc:
                rospy.logwarn_throttle(1.0, 'I2C 读取失败: %s', exc)
                rate.sleep()
                continue

            stamp = rospy.Time.now()

            # 单位换算 + FLU 坐标映射
            acc_b = to_flu(ax / ACC_SENS * G, ay / ACC_SENS * G, az / ACC_SENS * G)
            gyro_raw = (gx / GYRO_SENS * DEG2RAD,
                        gy / GYRO_SENS * DEG2RAD,
                        gz / GYRO_SENS * DEG2RAD)
            gyro_b = to_flu(*gyro_raw)
            gyro_b = tuple(w - b for w, b in zip(gyro_b, self.gyro_bias))

            imu_msg = Imu()
            imu_msg.header.stamp = stamp
            imu_msg.header.frame_id = self.frame_id
            imu_msg.linear_acceleration.x, \
                imu_msg.linear_acceleration.y, \
                imu_msg.linear_acceleration.z = acc_b
            imu_msg.angular_velocity.x, \
                imu_msg.angular_velocity.y, \
                imu_msg.angular_velocity.z = gyro_b
            imu_msg.orientation_covariance[0] = -1.0  # 无姿态解算
            self.pub_imu.publish(imu_msg)

            if self.mag_ok:
                try:
                    mx, my, mz = self._read_s16x3(QMC5883P_ADDR, QMC_DATA)
                except OSError as exc:
                    rospy.logwarn_throttle(1.0, 'QMC5883P 读取失败: %s', exc)
                    rate.sleep()
                    continue
                # LSB → 高斯 → 特斯拉, 并映射到 FLU
                scale = 1e-4 / self.mag_lsb_per_gauss
                mag_b = to_flu(mx * scale, my * scale, mz * scale)
                mag_msg = MagneticField()
                mag_msg.header.stamp = stamp
                mag_msg.header.frame_id = self.frame_id
                mag_msg.magnetic_field.x, \
                    mag_msg.magnetic_field.y, \
                    mag_msg.magnetic_field.z = mag_b
                self.pub_mag.publish(mag_msg)

            rate.sleep()


def main():
    rospy.init_node('imu_bmi088_qmc5883p')
    ImuNode().spin()


if __name__ == '__main__':
    main()
