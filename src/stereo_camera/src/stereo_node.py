#!/usr/bin/env python3
"""UVC 双目同步相机拆帧节点。

相机输出 side-by-side 拼帧 3840x1080@30fps（左半幅左眼 / 右半幅右眼，
基线 60mm），节点将其拆分为两路并可选降采样后发布:

  /camera/left/image_raw   sensor_msgs/Image (bgr8, frame_id=camera_left)
  /camera/right/image_raw  sensor_msgs/Image (bgr8, frame_id=camera_right)

两路共用同一时间戳 (ros::Time::now() 取帧时刻)，供 VINS-Fusion 双目使用。
"""

import cv2
import rospy
from cv_bridge import CvBridge
from sensor_msgs.msg import Image


class StereoNode:
    def __init__(self):
        self.device = rospy.get_param('~video_device', '/dev/video0')
        self.width = int(rospy.get_param('~width', 3840))
        self.height = int(rospy.get_param('~height', 1080))
        self.fps = float(rospy.get_param('~fps', 30))
        # 降采样输出分辨率（单幅），0 表示不缩放
        self.out_width = int(rospy.get_param('~out_width', 0))
        self.out_height = int(rospy.get_param('~out_height', 0))

        self.cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            raise RuntimeError('无法打开视频设备: {}'.format(self.device))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        rospy.loginfo('%s 打开成功: %dx%d @ %.1ffps (请求 %dx%d)',
                      self.device, actual_w, actual_h, self.fps,
                      self.width, self.height)

        self.bridge = CvBridge()
        self.pub_left = rospy.Publisher('/camera/left/image_raw', Image,
                                        queue_size=5)
        self.pub_right = rospy.Publisher('/camera/right/image_raw', Image,
                                         queue_size=5)

    def _publish(self, img, pub, frame_id, stamp):
        if self.out_width > 0 and self.out_height > 0:
            img = cv2.resize(img, (self.out_width, self.out_height),
                             interpolation=cv2.INTER_AREA)
        msg = self.bridge.cv2_to_imgmsg(img, encoding='bgr8')
        msg.header.stamp = stamp
        msg.header.frame_id = frame_id
        pub.publish(msg)

    def spin(self):
        rate = rospy.Rate(self.fps)
        while not rospy.is_shutdown():
            ok, frame = self.cap.read()
            if not ok:
                rospy.logwarn_throttle(1.0, '取帧失败，设备可能被占用或断开')
                rate.sleep()
                continue
            stamp = rospy.Time.now()
            half = frame.shape[1] // 2
            left = frame[:, :half]
            right = frame[:, half:]
            self._publish(left, self.pub_left, 'camera_left', stamp)
            self._publish(right, self.pub_right, 'camera_right', stamp)
            rate.sleep()

        self.cap.release()


def main():
    rospy.init_node('stereo_camera')
    StereoNode().spin()


if __name__ == '__main__':
    main()
