cmake_minimum_required(VERSION 3.0.2)
project(stereo_camera)

find_package(catkin REQUIRED COMPONENTS
  roscpp
  std_msgs
  sensor_msgs
  cv_bridge
)

find_package(OpenCV REQUIRED)

catkin_package()

include_directories(${catkin_INCLUDE_DIRS} ${OpenCV_INCLUDE_DIRS})

add_executable(stereo_node src/stereo_node.cpp)
target_link_libraries(stereo_node ${catkin_LIBRARIES} ${OpenCV_LIBS})

install(TARGETS stereo_node
  RUNTIME DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})

install(DIRECTORY launch/
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}/launch)
