// UVC 双目同步相机拆帧节点 (C++)
//
// 相机输出 side-by-side 拼帧（默认 1280x480@30 MJPG，单目原生 640x480），
// 拆为左右两路发布。高分辨率档位必须用 MJPG（YUYV 在 3840x1080 仅 1fps），
// 因此先指定 FOURCC 再设分辨率。开机前若干帧为自动曝光收敛期，预热丢弃。
//
// 话题:
//   /camera/left/image_raw   (bgr8, frame_id=camera_left)
//   /camera/right/image_raw  (bgr8, frame_id=camera_right)
// 两路共用同一采集时刻的时间戳。
#include <ros/ros.h>
#include <sensor_msgs/Image.h>
#include <cv_bridge/cv_bridge.h>
#include <opencv2/opencv.hpp>

class StereoNode {
 public:
  StereoNode() : nh_("~") {
    nh_.param<std::string>("video_device", device_, "/dev/video0");
    nh_.param<int>("width", width_, 1280);
    nh_.param<int>("height", height_, 480);
    nh_.param<double>("fps", fps_, 30.0);
    nh_.param<int>("out_width", out_w_, 0);
    nh_.param<int>("out_height", out_h_, 0);
    nh_.param<int>("warmup_frames", warmup_, 30);

    cap_.open(device_, cv::CAP_V4L2);
    if (!cap_.isOpened()) {
      ROS_FATAL("无法打开视频设备: %s", device_.c_str());
      ros::shutdown();
      return;
    }
    cap_.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    cap_.set(cv::CAP_PROP_FRAME_WIDTH, width_);
    cap_.set(cv::CAP_PROP_FRAME_HEIGHT, height_);
    cap_.set(cv::CAP_PROP_FPS, fps_);
    ROS_INFO("%s opened: %dx%d @ %.1ffps (requested %dx%d)", device_.c_str(),
             static_cast<int>(cap_.get(cv::CAP_PROP_FRAME_WIDTH)),
             static_cast<int>(cap_.get(cv::CAP_PROP_FRAME_HEIGHT)),
             fps_, width_, height_);

    for (int i = 0; i < warmup_; ++i) {
      cap_.grab();
    }
    ROS_INFO("warmup done: dropped first %d frames", warmup_);

    pub_left_ = nh_.advertise<sensor_msgs::Image>("/camera/left/image_raw", 5);
    pub_right_ = nh_.advertise<sensor_msgs::Image>("/camera/right/image_raw", 5);
  }

  void publish(const cv::Mat &img, const ros::Publisher &pub,
               const std::string &frame_id, const ros::Time &stamp) {
    cv::Mat out = img;
    if (out_w_ > 0 && out_h_ > 0 &&
        (img.cols != out_w_ || img.rows != out_h_)) {
      cv::resize(img, out, cv::Size(out_w_, out_h_), 0, 0, cv::INTER_LINEAR);
    }
    cv_bridge::CvImage msg;
    msg.header.stamp = stamp;
    msg.header.frame_id = frame_id;
    msg.encoding = "bgr8";
    msg.image = out;
    pub.publish(msg.toImageMsg());
  }

  void spin() {
    ros::Rate rate(fps_);
    int n = 0;
    ros::WallTime t_win = ros::WallTime::now();
    while (ros::ok()) {
      cv::Mat frame;
      if (!cap_.read(frame) || frame.empty()) {
        ROS_WARN_THROTTLE(1.0, "frame grab failed, device busy or disconnected");
        rate.sleep();
        continue;
      }
      const ros::Time stamp = ros::Time::now();
      const int half = frame.cols / 2;
      publish(frame(cv::Rect(0, 0, half, frame.rows)).clone(),
              pub_left_, "camera_left", stamp);
      publish(frame(cv::Rect(half, 0, frame.cols - half, frame.rows)).clone(),
              pub_right_, "camera_right", stamp);

      ++n;
      if (n % 150 == 0) {
        const double dt = (ros::WallTime::now() - t_win).toSec();
        ROS_INFO("published %d frames, last 150 avg %.1f fps", n,
                 dt > 0 ? 150.0 / dt : 0.0);
        t_win = ros::WallTime::now();
      }
      ros::spinOnce();
      rate.sleep();
    }
    cap_.release();
  }

 private:
  ros::NodeHandle nh_;
  cv::VideoCapture cap_;
  ros::Publisher pub_left_, pub_right_;
  std::string device_;
  int width_, height_, out_w_, out_h_, warmup_;
  double fps_;
};

int main(int argc, char **argv) {
  ros::init(argc, argv, "stereo_camera");
  StereoNode node;
  if (ros::ok()) {
    node.spin();
  }
  return 0;
}
