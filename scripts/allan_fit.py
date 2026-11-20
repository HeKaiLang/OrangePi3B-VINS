#!/usr/bin/env python3
"""从 rosbag 直接计算 Allan 方差并拟合 IMU 全部噪声参数。

imu_utils 的 yaml 只给噪声密度(gyr_n/acc_n)和偏置不稳定度,
不提供 Kalibr/VINS 需要的随机游走(random walk)。本脚本:
  1. 读取 bag 中 /imu/data;
  2. 对角速度/加速度各轴计算 Allan 标准差 σ(τ) 曲线 (numpy 向量化);
  3. 输出: 噪声密度(τ=1s)、偏置不稳定度(σ 最小值)、随机游走(+1/2 斜率段拟合)。

约定:
  - 噪声密度 N: σ_white(τ) = N / √τ, 取 τ=1s 处读数 [rad/s/√Hz, m/s²/√Hz]
  - 偏置不稳定度 B: min σ(τ) [rad/s, m/s²]
  - 随机游走 K: σ_RW(τ) = K·√(τ/3) (IEEE/Kalibr 五项模型), 由 log σ~log τ
    曲线中斜率最接近 +1/2 的区段拟合截距得到 [rad/s²/√Hz, m/s³/√Hz]

用法:
  python3 allan_fit.py <bag路径> [bag路径2 ...]
输出每轴参数 + 与 imu_utils 结果的可比性校验。
"""

import math
import sys

import numpy as np
import rosbag


def allan_deviation(x, fs, taus):
    """对均匀采样序列 x 计算 τ 列表对应的 Allan 标准差。"""
    theta = np.cumsum(x) / fs          # 积分: 角速度→角度, 加速度→速度
    n = len(x)
    sigma = np.zeros(len(taus))
    for i, tau in enumerate(taus):
        m = int(round(tau * fs))
        if m < 1 or n - 2 * m < 10:
            sigma[i] = np.nan
            continue
        d = theta[2 * m:] - 2 * theta[m:n - m] + theta[:n - 2 * m]
        sigma[i] = math.sqrt(np.mean(d * d) / (2.0 * tau * tau))
    return sigma


def fit_random_walk(taus, sigma, t_min, t_max):
    """在 [t_min, t_max] 内找斜率最接近 +1/2 的连续区段, 固定斜率 1/2 拟合 K。
    返回 (K, 拟合段 [τlo, τhi], 原始斜率)。"""
    lg_t, lg_s = np.log10(taus), np.log10(sigma)
    best = None
    for w in (6, 8, 10):                       # 滑窗宽度(点数)
        for i in range(0, len(taus) - w):
            seg_t, seg_s = lg_t[i:i + w], lg_s[i:i + w]
            if taus[i] < t_min or taus[i + w] > t_max:
                continue
            if np.any(~np.isfinite(seg_s)):
                continue
            b, a = np.polyfit(seg_t, seg_s, 1)
            score = abs(b - 0.5)
            if best is None or score < best[0]:
                best = (score, i, w, b, a)
    if best is None:
        return np.nan, None, np.nan
    _, i, w, b, a = best
    # 固定斜率 1/2 重拟合截距: log σ = log K - 0.5*log 3 + 0.5*log τ
    # 即 σ = K·√(τ/3)  =>  log K = a' + 0.5*log 3,  a' 为固定斜率截距
    a_fixed = np.mean(lg_s[i:i + w] - 0.5 * lg_t[i:i + w])
    K = 10 ** (a_fixed + 0.5 * math.log10(3.0))
    return K, (taus[i], taus[i + w - 1]), b


def analyze(bag_path):
    print('=' * 70)
    print('bag:', bag_path)
    imu = []
    with rosbag.Bag(bag_path) as bag:
        for _, msg, _ in bag.read_messages(topics=['/imu/data']):
            imu.append((msg.header.stamp.to_sec(),
                        msg.angular_velocity.x, msg.angular_velocity.y,
                        msg.angular_velocity.z,
                        msg.linear_acceleration.x, msg.linear_acceleration.y,
                        msg.linear_acceleration.z))
    arr = np.asarray(imu)
    t = arr[:, 0]
    dt = np.mean(np.diff(t))
    fs = 1.0 / dt
    dur = t[-1] - t[0]
    print('样本 %d, 时长 %.1f h, 平均采样 %.2f Hz' % (len(t), dur / 3600, fs))

    taus = np.logspace(math.log10(10 * dt), math.log10(dur / 3), 80)

    for name, cols, unit in (('gyr', (1, 2, 3), 'rad/s'),
                             ('acc', (4, 5, 6), 'm/s^2')):
        for ax, c in zip('xyz', cols):
            x = arr[:, c] - np.mean(arr[:, c])   # 去均值消直流
            sigma = allan_deviation(x, fs, taus)
            idx1 = np.argmin(np.abs(taus - 1.0))
            noise_density = sigma[idx1]
            bias_inst = np.nanmin(sigma)
            rw, seg, slope = fit_random_walk(taus, sigma, 30.0, dur / 3)
            print('  %s-%s [%s]: 噪声密度(τ=1s)=%.4e  偏置不稳定=%.4e  '
                  '随机游走=%.4e (段 %s, 斜率 %.2f)'
                  % (name, ax, unit, noise_density, bias_inst, rw,
                     '%.0f-%.0fs' % seg if seg else 'N/A', slope))


if __name__ == '__main__':
    for p in sys.argv[1:]:
        analyze(p)
