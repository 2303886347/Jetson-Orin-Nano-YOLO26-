# collect_picture 安装与使用教程

在教程同一文件夹下的 **“资源文件”** 文件夹中找到 `collect_picture` 和
`collect_picture_setup`，使用 MobaXterm 将两个完整文件夹传入 Jetson 的
`~/Downloads/` 目录。文件夹名称和内部结构必须保持不变；如果目标位置已经存在
同名目录，先核对版本，不要直接混合覆盖。

## 1. 安装内容

`collect_picture` 是一个基于 PyQt5 和 ROS 2 图像话题的图片采集工具。源码、安装材料和最终安装目录彼此分开：安装器从下载目录读取源码，并把可运行程序部署到 `$HOME/Software/collect_picture`。

| 路径 | 用途 |
| --- | --- |
| `$HOME/Downloads/collect_picture/` | 程序源码和界面资源。 |
| `$HOME/Downloads/collect_picture_setup/` | 安装器、教程和安装日志目录，不存放程序源码。 |
| `$HOME/Downloads/collect_picture_setup/install_collect_picture.sh` | 一键安装和验证脚本。 |
| `$HOME/Downloads/collect_picture_setup/collect_picture安装与使用教程.md` | 本教程。 |
| `$HOME/Downloads/collect_picture_setup/logs/` | 每次安装或验证的日志。 |
| `$HOME/Software/collect_picture/` | 安装后的程序目录。 |
| `$HOME/Software/collect_picture/run_collect_picture.sh` | 程序启动器。 |
| `$HOME/Software/collect_picture/camera.env` | 相机话题与 ROS 2 工作空间配置。 |

安装器会部署 ROS 2 Humble 相机适配文件，使程序能够以传感器数据 QoS 订阅
`sensor_msgs/msg/Image`，默认图像话题为 `/image_raw`。

## 2. 环境要求

适用环境：

- Ubuntu 22.04
- Python 3.10
- ROS 2 Humble
- AArch64 或 x86_64 图形桌面

主要依赖如下：

| 依赖 | 作用 |
| --- | --- |
| `python3-pyqt5` | 图形界面。 |
| `python3-opencv`、`python3-numpy` | 图像处理与保存。 |
| `ros-humble-rclpy` | ROS 2 Python 节点。 |
| `ros-humble-sensor-msgs` | 相机图像消息类型。 |
| `ros-humble-cv-bridge` | ROS 图像与 OpenCV 图像转换。 |
| Qt/OpenGL/xcb 运行库 | 本地图形界面显示。 |

脚本会先检查这些系统包。仅在发现缺失包时调用 `sudo apt-get`，不要在脚本命令前加 `sudo`。

### 新终端必须重新加载 ROS 2 环境

`source` 只对当前终端有效。每次新开终端、标签页或 SSH 会话，都要在运行 ROS
命令或 `collect_picture` 前重新执行：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash
```

终端 A 加载过环境，不代表终端 B 已加载。下面涉及 ROS 的命令块均可单独复制执行。

## 3. 一键安装

在普通用户终端中执行：

```bash
chmod +x $HOME/Downloads/collect_picture_setup/install_collect_picture.sh
bash $HOME/Downloads/collect_picture_setup/install_collect_picture.sh
```

安装器会依次完成：

1. 检查源码和系统依赖。
2. 将程序部署到 `$HOME/Software/collect_picture`。
3. 补充 ROS 2 相机适配文件。
4. 创建启动器和应用菜单入口“图片采集”。
5. 在无显示器模式下验证 Qt 界面、ROS 2 节点和 Python 模块。

验证不检查真实相机画面。真实采集前仍需启动能够发布图像的相机节点。

## 4. 安装器选项

```bash
# 系统依赖已经安装时，禁止脚本调用 APT。
bash $HOME/Downloads/collect_picture_setup/install_collect_picture.sh --skip-system

# 只验证安装结果，不复制程序文件。
bash $HOME/Downloads/collect_picture_setup/install_collect_picture.sh --verify-only

# 不创建应用菜单入口。
bash $HOME/Downloads/collect_picture_setup/install_collect_picture.sh --no-desktop
```

重复安装时，程序文件会更新，但以下用户配置会保留：

- `$HOME/Software/collect_picture/config.ini`
- `$HOME/Software/collect_picture/camera.env`

## 5. 启动相机话题

程序默认订阅统一图像话题：

```text
/image_raw
```

先加载 ROS 2 环境并确认相机话题存在：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash

ros2 topic list
ros2 topic info /image_raw
ros2 topic hz /image_raw
```

CSI 或 USB 相机节点启动后，需要将画面发布到 `/image_raw`，并保证消息类型为 `sensor_msgs/msg/Image`。例如可在发布节点中创建：

```python
from sensor_msgs.msg import Image

image_pub = node.create_publisher(Image, "/image_raw", 10)
```

相机来源可以是 CSI、USB 或深度相机。`collect_picture` 不直接操作摄像头设备，只负责订阅你的相机节点发布的 ROS 2 图像。

程序以非阻塞方式读取最新相机帧。建议先确认 `ros2 topic hz` 能持续收到数据，再启动
应用，以便打开界面后立即显示画面。

## 6. 启动 collect_picture

相机节点运行后，新开一个终端执行：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash

$HOME/Software/collect_picture/run_collect_picture.sh
```

也可以在桌面应用菜单中搜索“图片采集”或“Collect Picture”。必须在桌面、VNC 或
NoMachine 等具有图形显示的会话中启动。

## 7. 修改相机话题

### 临时修改

只对本次启动生效：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash

COLLECT_PICTURE_CAMERA_TOPIC=/other_camera/image_raw \
  $HOME/Software/collect_picture/run_collect_picture.sh
```

启用第二个相机切换按钮：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash

COLLECT_PICTURE_CAMERA_TOPIC=/camera1/image_raw \
COLLECT_PICTURE_CAMERA_TOPIC_2=/camera2/image_raw \
  $HOME/Software/collect_picture/run_collect_picture.sh
```

### 永久修改

如系统尚未安装 Gedit，先执行：

```bash
sudo apt update
sudo apt install -y gedit
```

编辑：

```bash
gedit "$HOME/Software/collect_picture/camera.env"
```

修改完成后，按 `Ctrl + S` 保存文件，然后关闭 Gedit。

将默认话题改成实际名称，例如：

```bash
COLLECT_PICTURE_CAMERA_TOPIC="${COLLECT_PICTURE_CAMERA_TOPIC:-/image_raw}"
COLLECT_PICTURE_CAMERA_TOPIC_2="${COLLECT_PICTURE_CAMERA_TOPIC_2:-}"
```

如果相机消息或自定义接口来自另一个 ROS 2 工作空间，可在同一文件中填写其环境脚本：

```bash
COLLECT_PICTURE_ROS_OVERLAY="${COLLECT_PICTURE_ROS_OVERLAY:-$HOME/my_ros2_ws/install/setup.bash}"
```

## 8. 界面操作

YOLO26 工作流应先按照总教程创建数据集，再在“保存路径”中选择该数据集的
`source` 目录。通用示例为：

```text
$HOME/ros2_ws/src/YOLO26/datasets/my_dataset/source
```

`my_dataset` 应替换为用户创建的实际数据集名。单类别和多类别使用同一目录结构。

随后执行：

1. 在“保存路径”处确认上述数据集目录。
2. 设置输出图片宽度和高度，默认是 `640 x 480`。
3. 点击“保存”或按空格键采集当前画面。
4. 点击“删除”或按 `d` 删除本次启动后最近保存的一张图片。
5. 按 `q` 或点击“退出”关闭程序。

采集目录结构如下：

```text
所选目录/
├── JPEGImages/
│   ├── image_1.jpg
│   ├── image_2.jpg
│   └── ...
├── Annotations/
└── ImageSets/
```

程序只把图片写入 `JPEGImages`。`Annotations` 和 `ImageSets` 是为后续标注和数据集处理预留的目录。

完成采集后，不要把 XML 保存到 `JPEGImages`。按照下面的总教程使用 LabelImg，将
Pascal VOC XML 保存到同级 `Annotations`。类别可以是任意单类别或多个类别；持续
增加数据时继续使用同一个数据集的 `source`，不要丢弃旧图片和旧标注：

```text
$HOME/ros2_ws/src/YOLO26/docs/YOLO26_采集标注训练与ROS识别教程.md
```

## 9. 常见问题

### 界面没有画面或启动后无响应

先检查默认话题是否存在并持续发布：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash

ros2 topic info /image_raw
ros2 topic hz /image_raw
```

若实际话题名称不同，按第 7 节修改配置。应先启动相机，再启动采集程序。

### 选择保存目录时界面无响应

正式安装版使用非阻塞相机帧读取和异步 Qt 目录选择器，选择目录期间画面应继续刷新。
如果界面无响应，先确认没有重复运行多个采集程序，再重新启动：

重新启动：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash

$HOME/Software/collect_picture/run_collect_picture.sh
```

取消目录选择不会改变已经填写的保存路径。

### `/image_raw` 不存在

这表示 CSI 或 USB 相机发布节点还没有启动，或者发布节点使用了其他话题名。推荐直接让发布节点发布 `/image_raw`；也可以通过 `COLLECT_PICTURE_CAMERA_TOPIC` 指定其他图像话题。

### `ModuleNotFoundError`

重新执行默认安装器，让它补齐系统依赖：

```bash
bash $HOME/Downloads/collect_picture_setup/install_collect_picture.sh
```

然后运行只验证模式：

```bash
bash $HOME/Downloads/collect_picture_setup/install_collect_picture.sh --verify-only
```

### Qt 提示无法连接显示器

检查当前终端是否处于图形会话：

```bash
echo "$DISPLAY"
```

空输出通常表示终端没有图形显示环境。请在桌面、VNC、NoMachine，或正确启用 X11
转发后启动。

### 查看安装日志

```bash
latest_log=$(ls -t $HOME/Downloads/collect_picture_setup/logs/install-*.log | head -n 1)
tail -n 100 "$latest_log"
```

成功安装的结尾应显示：

```text
collect_picture installation completed.
Start the camera publisher first, then run:
  $HOME/Software/collect_picture/run_collect_picture.sh
```
