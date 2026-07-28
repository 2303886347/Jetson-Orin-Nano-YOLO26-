# Jetson Orin Nano YOLO26 目标检测工作流

<p align="center">
  <strong>从 ROS 2 图像话题出发，完成采图、标注、训练、测试与 TensorRT 部署</strong>
</p>


<p align="center">
  <img src="https://img.shields.io/badge/Platform-Jetson%20Orin%20Nano-76B900?style=flat-square&logo=nvidia&logoColor=white" alt="Jetson Orin Nano" />
  <img src="https://img.shields.io/badge/Ubuntu-22.04-E95420?style=flat-square&logo=ubuntu&logoColor=white" alt="Ubuntu 22.04" />
  <img src="https://img.shields.io/badge/ROS%202-Humble-22314E?style=flat-square&logo=ros&logoColor=white" alt="ROS 2 Humble" />
  <img src="https://img.shields.io/badge/Python-3.10-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10" />
  <img src="https://img.shields.io/badge/CUDA-12.6-76B900?style=flat-square&logo=nvidia&logoColor=white" alt="CUDA 12.6" />
  <img src="https://img.shields.io/badge/TensorRT-10-76B900?style=flat-square&logo=nvidia&logoColor=white" alt="TensorRT 10" />
</p>


这是一个面向 NVIDIA Jetson Orin Nano 的 YOLO26 目标检测完整工程。项目把机器人视觉中最容易出错、最难复现的几个环节整理成了一条可执行链路：

~~~text
ROS 2 相机图像话题 /image_raw
        -> collect_picture 采集 JPG
        -> LabelImg 标注 Pascal VOC XML
        -> prepare_dataset.py 校验并转换数据集
        -> train_yolo26.py 训练自定义模型
        -> best.pt 离线测试与 ROS 2 实时识别
        -> TensorRT FP16 engine 加速部署
~~~

项目的最大特点是：安装和验证主要由脚本完成。安装器会检查平台、安装系统依赖、创建独立 Python 环境、部署源码、校验本地 wheel，并在结束时自动执行导入检查、GPU 实算和模型冒烟推理。采图工具、LabelImg 和 YOLO26 环境彼此独立，便于重装、排错和迁移。

## 这个项目能做什么

- 使用已有 ROS 2 相机节点发布的图像，实时采集训练图片。
- 对单类别或多类别目标进行矩形框标注，并保留可回溯的 Pascal VOC XML。
- 自动检查数据集、固定 train/val/test 切分，并生成 YOLO 格式数据。
- 基于随工程提供的轻量级 yolo26n.pt 进行迁移训练。
- 使用 best.pt 进行离线测试和 ROS 2 实时识别。
- 在目标 Jetson 上导出 TensorRT FP16 engine，用于低延迟部署。
- 输出带检测框的图像和标准 vision_msgs/msg/Detection2DArray 检测消息，方便接入机器人后续逻辑。

## 统一接口：ROS 2 图像话题

这是使用本项目的前提。采图和实时识别都不直接操作 CSI 或 USB 摄像头设备，而是订阅 ROS 2 发布的图像话题。摄像头驱动、相机分辨率和设备初始化由外部的 ROS 2 相机功能包负责。

默认接口如下：

| 用途           | 话题                    | 消息类型                         | 说明                                     |
| -------------- | ----------------------- | -------------------------------- | ---------------------------------------- |
| 原始相机图像   | /image_raw              | sensor_msgs/msg/Image            | collect_picture 和 yolo26_ros 的默认输入 |
| 带检测框图像   | /yolo26/annotated_image | sensor_msgs/msg/Image            | YOLO26 绘制类别、置信度和 FPS 后的图像   |
| 结构化检测结果 | /yolo26/detections      | vision_msgs/msg/Detection2DArray | 目标类别、置信度和边界框                 |
| 恢复推理       | /yolo26/start           | std_srvs/srv/Trigger             | 启用检测                                 |
| 暂停推理       | /yolo26/stop            | std_srvs/srv/Trigger             | 暂停检测但保持节点运行                   |

启动任何工具前，先确认上游图像话题存在且持续发布：

~~~bash
source /opt/ros/humble/setup.bash
source "$HOME/ros2_ws/install/setup.bash"

ros2 topic info /image_raw --verbose
ros2 topic hz /image_raw
~~~

/image_raw 必须由一个 ROS 2 节点发布，类型应为 sensor_msgs/msg/Image。同一时间建议只运行一个向 /image_raw 发布图像的相机节点，避免多个发布者造成画面和时间戳混乱。

> [!NOTE]
>
> LabelImg 是离线标注工具，本身不订阅 ROS 2 话题。它处理的是 collect_picture 保存到磁盘的图片；因此本项目的统一上游接口是 ROS 2 图像话题，标注阶段则通过标准数据集目录衔接。

如果实际相机使用的是其他话题，采图工具可以临时修改输入：

~~~bash
COLLECT_PICTURE_CAMERA_TOPIC=/camera/color/image_raw \
  "$HOME/Software/collect_picture/run_collect_picture.sh"
~~~

YOLO26 检测节点可以通过启动参数修改：

~~~bash
ros2 launch yolo26_ros detector.launch.py \
  image_topic:=/camera/color/image_raw \
  model_path:="$YOLO26_ROOT/models/pretrained/yolo26n.pt"
~~~

## 目录结构

当前资源包实际包含 5 个配套目录，上传到 GitHub 后建议保持目录名和内部结构不变：

~~~text
.
├── README.md
├── YOLO26/
├── collect_picture/
├── collect_picture_setup/
├── labelimg/
└── labelimg_setup/
~~~

| 目录                                              | 内容                                                         | 典型使用位置                          |
| ------------------------------------------------- | ------------------------------------------------------------ | ------------------------------------- |
| [YOLO26](YOLO26/)                                 | YOLO26 主工程、数据集目录、训练/推理工具、预训练模型和 ROS 2 检测包 | $HOME/ros2_ws/src/YOLO26              |
| [YOLO26/setup](YOLO26/setup/)                     | Jetson 环境安装器、激活脚本、依赖约束、本地 wheel、DLA 后备文件和安装日志 | 安装与激活 GPU 环境                   |
| [YOLO26/tools](YOLO26/tools/)                     | create_dataset.py、prepare_dataset.py、train_yolo26.py、predict_yolo26.py、export_yolo26.py | 数据集和模型生命周期                  |
| [YOLO26/ros2/yolo26_ros](YOLO26/ros2/yolo26_ros/) | ROS 2 检测节点、消息转换、启动文件和默认模型                 | 实时识别                              |
| [collect_picture](collect_picture/)               | 基于 PyQt5 的 ROS 2 图像采集 GUI 源码                        | 安装器读取的源代码                    |
| [collect_picture_setup](collect_picture_setup/)   | 采图工具安装脚本和使用教程                                   | $HOME/Downloads/collect_picture_setup |
| [labelimg](labelimg/)                             | LabelImg 1.8.6 源码和资源                                    | 安装器读取的源代码                    |
| [labelimg_setup](labelimg_setup/)                 | LabelImg 独立安装脚本和使用教程                              | $HOME/Downloads/labelimg_setup        |

YOLO26 工程内部的重要产物：

~~~text
YOLO26/
├── datasets/                 # 用户创建的数据集
├── models/pretrained/        # 随工程提供的 yolo26n.pt
├── models/deployed/          # 当前 Jetson 上导出的 TensorRT engine
├── runs/                     # 训练和离线推理结果
├── ros2/yolo26_ros/          # ROS 2 检测功能包
├── tools/                    # 数据、训练、推理、导出脚本
├── docs/                     # 完整工作流教程
└── setup/                    # 环境安装材料
~~~

## 适用环境与前置条件

完整的 YOLO26 GPU 安装器针对以下环境制作，并且会主动检查其中的关键版本：

| 项目        | 要求                                                  |
| ----------- | ----------------------------------------------------- |
| 硬件        | NVIDIA Jetson Orin Nano                               |
| CPU 架构    | AArch64 / aarch64                                     |
| 操作系统    | Ubuntu 22.04                                          |
| 系统 Python | /usr/bin/python3，Python 3.10                         |
| NVIDIA L4T  | R36.4.7                                               |
| CUDA        | 12.6                                                  |
| cuDNN       | 9                                                     |
| TensorRT    | 10                                                    |
| ROS 2       | Humble                                                |
| 磁盘空间    | 首次安装建议至少 15 GiB 可用空间                      |
| 图形环境    | 采图和标注运行时需要桌面、VNC 或 NoMachine 等显示会话 |

安装前建议先检查：

~~~bash
uname -m
/usr/bin/python3 --version
dpkg-query -W nvidia-l4t-core
df -h "$HOME"
~~~

预期结果是 aarch64、Python 3.10，以及以 36.4.7- 开头的 nvidia-l4t-core 版本。YOLO26 安装器使用随项目提供的 cp310、linux_aarch64 wheel；不满足这些条件时，不建议强行安装或混用其他 Jetson 版本的 wheel。

还需要一个可以发布 /image_raw 的 ROS 2 相机节点。配套课程第 4 章中的 camera_usb_and_csi 可以完成 CSI/USB 摄像头发布，但该相机功能包不包含在本仓库的 5 个目录中。摄像头驱动、设备绑定、CSI/USB 启动参数和 ROS 2 发布配置可以参考 [2303886347/USB_and_CSI_Camera_ROS2_publish_pkg](https://github.com/2303886347/USB_and_CSI_Camera_ROS2_publish_pkg)。

建议先按照该项目完成摄像头的硬件识别和 ROS 2 发布，再回到本仓库执行后续步骤：确认相机节点已经发布 sensor_msgs/msg/Image，默认话题为 /image_raw，并通过 ros2 topic info 和 ros2 topic hz 验证话题类型与帧率。验证通过后，同一个 /image_raw 话题即可被 collect_picture 用于采集图片，也可以被 yolo26_ros 用于实时目标检测；如果相机项目使用了其他话题名，请在本项目中通过 COLLECT_PICTURE_CAMERA_TOPIC 或 image_topic:=... 指定对应话题。

## 安装顺序

推荐严格按照下面的顺序操作。每个安装器都应由普通用户启动，不要在整个命令前加 sudo；脚本只会在需要安装 APT 系统包时自行请求 sudo 权限。

### 1. 将源码放到安装器期望的位置

假设已经把 GitHub 仓库下载到 Jetson 的 $HOME/YOLO26-Jetson：

~~~bash
export REPO="$HOME/YOLO26-Jetson"

mkdir -p "$HOME/ros2_ws/src" "$HOME/Downloads"

# 目标目录存在同名版本时，请先核对版本，不要直接混合覆盖。
test ! -e "$HOME/ros2_ws/src/YOLO26"
test ! -e "$HOME/Downloads/collect_picture"
test ! -e "$HOME/Downloads/collect_picture_setup"
test ! -e "$HOME/Downloads/labelimg"
test ! -e "$HOME/Downloads/labelimg_setup"

cp -a "$REPO/YOLO26" "$HOME/ros2_ws/src/"
cp -a "$REPO/collect_picture" "$HOME/Downloads/"
cp -a "$REPO/collect_picture_setup" "$HOME/Downloads/"
cp -a "$REPO/labelimg" "$HOME/Downloads/"
cp -a "$REPO/labelimg_setup" "$HOME/Downloads/"
~~~

YOLO26 安装器也支持从 YOLO26_ROOT 查找工程。完成复制后先确认关键文件：

~~~bash
export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"

test -f "$YOLO26_ROOT/setup/install_yolo26.sh"
test -f "$YOLO26_ROOT/setup/wheels/torch-2.7.0-cp310-cp310-linux_aarch64.whl"
test -f "$YOLO26_ROOT/models/pretrained/yolo26n.pt"
test -f "$YOLO26_ROOT/ros2/yolo26_ros/package.xml"
~~~

### 2. 安装 YOLO26 Jetson GPU 环境

YOLO26 环境应优先安装，因为后续训练、离线推理和 ROS 2 检测都依赖它：

~~~bash
export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"

chmod +x "$YOLO26_ROOT/setup/install_yolo26.sh"
bash "$YOLO26_ROOT/setup/install_yolo26.sh"
~~~

安装器会完成以下工作：

- 检查 AArch64、Python 3.10、L4T R36.4.7 和磁盘空间。
- 检查或安装 CUDA 12.6、cuDNN 9、TensorRT 10、编译工具和运行库。
- 在 $HOME/.venvs/yolo26 创建可复用的 Python 虚拟环境。
- 安装项目提供的 PyTorch 2.7.0、TorchVision 0.22.0、TorchAudio 2.7.0 及 YOLO26 相关 Python 依赖。
- 校验本地 wheel 的 SHA256，避免误用被替换或版本不匹配的文件。
- 验证 CUDA、PyTorch、Ultralytics、TensorRT 和 yolo26n.pt 的基础推理链路。
- 把安装日志写入 YOLO26_ROOT/setup/logs/。

常用选项：

~~~bash
# 仅在 CUDA/cuDNN/TensorRT 和 DLA 运行库已经准备好时使用
bash "$YOLO26_ROOT/setup/install_yolo26.sh" --skip-system

# 只验证现有环境，不修改已安装的软件包
bash "$YOLO26_ROOT/setup/install_yolo26.sh" --verify-only

# 跳过可选的 TorchAO、PyCUDA 和 ONNX Runtime GPU
bash "$YOLO26_ROOT/setup/install_yolo26.sh" --skip-optional
~~~

安装成功后，每个新终端都要重新激活：

~~~bash
export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"
source "$YOLO26_ROOT/setup/activate_yolo26.sh"

echo "$YOLO26_ROOT"
echo "$YOLO26_PYTHON"
python --version
~~~

### 3. 安装 ROS 2 图像采集工具和 LabelImg

两个 GUI 工具使用独立的安装器，不依赖 YOLO26 虚拟环境互相覆盖：

~~~bash
chmod +x "$HOME/Downloads/collect_picture_setup/install_collect_picture.sh"
bash "$HOME/Downloads/collect_picture_setup/install_collect_picture.sh"

chmod +x "$HOME/Downloads/labelimg_setup/install_labelimg.sh"
bash "$HOME/Downloads/labelimg_setup/install_labelimg.sh"
~~~

安装位置和启动器如下：

| 工具            | 安装目录                       | 启动命令                                              |
| --------------- | ------------------------------ | ----------------------------------------------------- |
| collect_picture | $HOME/Software/collect_picture | $HOME/Software/collect_picture/run_collect_picture.sh |
| LabelImg        | $HOME/Software/labelimg        | $HOME/Software/labelimg/run_labelimg.sh               |

两个安装器也支持：

~~~bash
# 系统依赖已经存在时跳过 APT
bash "$HOME/Downloads/collect_picture_setup/install_collect_picture.sh" --skip-system
bash "$HOME/Downloads/labelimg_setup/install_labelimg.sh" --skip-system

# 只验证安装结果
bash "$HOME/Downloads/collect_picture_setup/install_collect_picture.sh" --verify-only
bash "$HOME/Downloads/labelimg_setup/install_labelimg.sh" --verify-only
~~~

采图和标注工具的安装日志分别位于：

~~~text
$HOME/Downloads/collect_picture_setup/logs/
$HOME/Downloads/labelimg_setup/logs/
~~~

### 4. 编译 YOLO26 ROS 2 功能包

加载 ROS 2、YOLO26 虚拟环境和工作空间后，编译本仓库中的 yolo26_ros：

~~~bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"
source "$YOLO26_ROOT/setup/activate_yolo26.sh"

cd "$HOME/ros2_ws"
colcon list | rg 'yolo26_ros|camera_usb_and_csi'
colcon build --symlink-install --packages-select yolo26_ros
source install/setup.bash

ros2 pkg prefix yolo26_ros
ros2 pkg executables yolo26_ros
~~~

如果第 4 章的 camera_usb_and_csi 已经放入同一个工作空间，可以一并构建：

~~~bash
colcon build --symlink-install \
  --packages-select camera_usb_and_csi yolo26_ros
source install/setup.bash
~~~

## 最小可运行示例：预训练模型实时识别

### 1. 启动相机并确认 /image_raw

CSI 摄像头示例：

~~~bash
source /opt/ros/humble/setup.bash
source "$HOME/ros2_ws/install/setup.bash"
ros2 launch camera_usb_and_csi camera.launch.py camera_type:=CSI
~~~

USB 摄像头示例：

~~~bash
source /opt/ros/humble/setup.bash
source "$HOME/ros2_ws/install/setup.bash"
ros2 launch camera_usb_and_csi camera.launch.py \
  camera_type:=USB usb_device:=/dev/usb_cam
~~~

在另一个终端检查：

~~~bash
source /opt/ros/humble/setup.bash
source "$HOME/ros2_ws/install/setup.bash"
ros2 topic info /image_raw --verbose
ros2 topic hz /image_raw
~~~

### 2. 复用已经启动的相机话题

detector.launch.py 只启动 YOLO26 检测节点和可选的 rqt_image_view，不会重复启动相机：

~~~bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source "$HOME/ros2_ws/install/setup.bash"

ros2 launch yolo26_ros detector.launch.py \
  image_topic:=/image_raw \
  model_path:="$YOLO26_ROOT/models/pretrained/yolo26n.pt" \
  imgsz:=640 confidence:=0.25 iou:=0.45 \
  device:=0 show_rqt:=true
~~~

识别窗口会显示检测框、类别、置信度和当前平滑 FPS。结构化结果可在新终端查看：

~~~bash
source /opt/ros/humble/setup.bash
source "$HOME/ros2_ws/install/setup.bash"

ros2 topic echo --once /yolo26/detections
ros2 service call /yolo26/stop std_srvs/srv/Trigger "{}"
ros2 service call /yolo26/start std_srvs/srv/Trigger "{}"
~~~

如果希望由一个 launch 文件同时启动相机、检测节点和图像查看器，并且工作空间中已经安装 camera_usb_and_csi，可以使用：

~~~bash
ros2 launch yolo26_ros camera_detector.launch.py \
  camera_type:=CSI \
  model_path:="$YOLO26_ROOT/models/pretrained/yolo26n.pt" \
  image_topic:=/image_raw \
  imgsz:=640 confidence:=0.25 iou:=0.45 \
  device:=0 show_rqt:=true
~~~

## 自定义目标检测完整使用流程

下面的示例使用 my_dataset、target_a 和 target_b 作为占位符。请替换为自己的数据集名和类别名，并保持类别顺序稳定。下面命令默认在已经激活 YOLO26 环境的终端中连续执行；新开终端时必须重新执行环境加载命令。

### 1. 创建数据集

~~~bash
export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

DATASET_NAME=my_dataset
python tools/create_dataset.py \
  --name "$DATASET_NAME" \
  --classes target_a target_b
~~~

创建后的源数据目录：

~~~text
datasets/my_dataset/
└── source/
    ├── JPEGImages/       # 采集的 JPG
    ├── Annotations/      # LabelImg 保存的 Pascal VOC XML
    ├── ImageSets/        # train/val/test 清单
    └── classes.names     # 一行一个类别，行号就是类别 ID
~~~

类别名称和顺序是训练数据的一部分。训练开始后不要重排、删除或重命名已有类别；如果要增加新类别，只追加到 classes.names 末尾，并回看旧图片是否也需要补标。

### 2. 通过 ROS 2 话题采集图片

确认 /image_raw 正常发布后，启动采图工具：

~~~bash
source /opt/ros/humble/setup.bash
source "$HOME/ros2_ws/install/setup.bash"

ros2 topic hz /image_raw
"$HOME/Software/collect_picture/run_collect_picture.sh"
~~~

在采图界面中将保存路径选择为：

~~~text
$YOLO26_ROOT/datasets/my_dataset/source
~~~

程序默认使用 640 x 480 图像，并将 JPG 写入 source/JPEGImages/。采集时尽量覆盖不同背景、光照、距离、角度、目标大小、遮挡和多个目标组合；不要把一段视频中的大量相邻帧同时分到 train 和 test，否则会产生数据泄漏。

### 3. 使用 LabelImg 保存 Pascal VOC XML

采集完成后，可以停止相机和采图程序，再启动 LabelImg：

~~~bash
export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"
source "$YOLO26_ROOT/setup/activate_yolo26.sh"

DATASET_NAME=my_dataset
"$HOME/Software/labelimg/run_labelimg.sh" \
  "$YOLO26_ROOT/datasets/$DATASET_NAME/source/JPEGImages"
~~~

当传入的是标准数据集的 source/JPEGImages 目录时，启动器会自动：

- 从同级 source/classes.names 加载类别。
- 固定使用 PascalVOC 格式。
- 将 XML 保存到同级 source/Annotations/。
- 使用与 JPG 相同的基本文件名保存 XML。

标注时应完整框住每个清晰可见的目标；一个目标只使用一个固定类别；正样本 JPG 应有同名 XML。没有目标的图片可以作为负样本保留，但只有在人工确认确实没有目标时，后续转换才允许将其作为无 XML 负样本。

### 4. 校验、切分并转换数据集

只维护 source/ 中的 JPG、XML 和 classes.names，不要手工修改工具生成的 yolo/ 目录：

~~~bash
export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

DATASET_NAME=my_dataset
python tools/prepare_dataset.py \
  --dataset "datasets/$DATASET_NAME" \
  --train-ratio 0.8 --val-ratio 0.1 --test-ratio 0.1 \
  --seed 42 --normalize-xml-paths
~~~

如果目录中存在已经人工确认的无 XML 负样本，显式增加：

~~~bash
python tools/prepare_dataset.py \
  --dataset "datasets/$DATASET_NAME" \
  --train-ratio 0.8 --val-ratio 0.1 --test-ratio 0.1 \
  --seed 42 --normalize-xml-paths \
  --allow-unannotated-negatives
~~~

工具会检查缺图、未知类别、重复文件、非法尺寸、越界框以及未明确允许的无 XML 图片，生成：

~~~text
datasets/my_dataset/yolo/
├── images/{train,val,test}/
├── labels/{train,val,test}/
├── data.yaml
└── dataset_report.json
~~~

### 5. 先做冒烟训练，再做正式训练

建议先用 10 epoch 确认数据和训练链路：

~~~bash
DATASET_NAME=my_dataset
RUN_NAME="$DATASET_NAME"_smoke

python tools/train_yolo26.py \
  --model models/pretrained/yolo26n.pt \
  --data "datasets/$DATASET_NAME/yolo/data.yaml" \
  --name "$RUN_NAME" \
  --imgsz 640 --batch 1 --epochs 10 \
  --device 0 --workers 1 --seed 42
~~~

冒烟训练成功并生成 runs/$RUN_NAME/weights/best.pt 后，再进行正式训练：

~~~bash
RUN_NAME="$DATASET_NAME"_v1

python tools/train_yolo26.py \
  --model models/pretrained/yolo26n.pt \
  --data "datasets/$DATASET_NAME/yolo/data.yaml" \
  --name "$RUN_NAME" \
  --imgsz 640 --batch 1 --epochs 100 \
  --device 0 --workers 1 --seed 42 --patience 20
~~~

训练前应关闭相机、采图工具、LabelImg、rqt 和其他持续占用 GPU 或共享内存的程序。8GB 版本通常使用 imgsz 640、batch 1；4GB 版本或出现显存不足时，可使用 imgsz 512，并在导出和推理阶段保持相同尺寸。

### 6. 离线测试 best.pt

实时识别前先使用没有参与训练的 test 集：

~~~bash
DATASET_NAME=my_dataset
RUN_NAME="$DATASET_NAME"_v1

python tools/predict_yolo26.py \
  --model "runs/$RUN_NAME/weights/best.pt" \
  --source "datasets/$DATASET_NAME/yolo/images/test" \
  --name "$RUN_NAME"_test \
  --imgsz 640 --conf 0.25 --iou 0.45 --device 0
~~~

结果位于 runs/predict/<run_name>_test/。应逐张检查漏检、误检、类别和边界框位置，不能只看训练损失或单张截图判断模型是否可用。

### 7. 使用自定义 best.pt 进行 ROS 2 实时识别

相机已经发布 /image_raw 时：

~~~bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source "$HOME/ros2_ws/install/setup.bash"

RUN_NAME=my_dataset_v1
MODEL_PATH="$YOLO26_ROOT/runs/$RUN_NAME/weights/best.pt"

ros2 launch yolo26_ros detector.launch.py \
  image_topic:=/image_raw \
  model_path:="$MODEL_PATH" \
  imgsz:=640 confidence:=0.25 iou:=0.45 \
  device:=0 show_rqt:=true
~~~

### 8. 导出并使用 TensorRT FP16 engine

只有在 best.pt 已经通过 test 集和真实 /image_raw 实时测试后，才建议导出 engine：

~~~bash
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

RUN_NAME=my_dataset_v1
ENGINE_NAME="$RUN_NAME".engine

python tools/export_yolo26.py \
  --model "runs/$RUN_NAME/weights/best.pt" \
  --format engine \
  --output "models/deployed/$ENGINE_NAME" \
  --imgsz 640 --device 0 --half
~~~

使用 engine 识别：

~~~bash
ENGINE_PATH="$YOLO26_ROOT/models/deployed/my_dataset_v1.engine"

ros2 launch yolo26_ros detector.launch.py \
  image_topic:=/image_raw \
  model_path:="$ENGINE_PATH" \
  imgsz:=640 confidence:=0.25 iou:=0.45 \
  device:=0 show_rqt:=true
~~~

TensorRT engine 与生成它的 GPU、CUDA、TensorRT、输入尺寸和精度模式相关。请在最终部署的 Jetson 上导出 engine；系统镜像、JetPack/L4T、CUDA、TensorRT 或 imgsz 发生变化后，应从保留的 best.pt 重新导出并验证。best.pt 是后续继续训练的主要成果，不能用 engine 代替。

## 详细文档应该看哪个文件

README 负责项目入口、接口约定和安装链路；具体操作以仓库内对应目录的 Markdown 为准：

| 你的目标                                                     | 详细阅读                                                     |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| 安装 YOLO26 GPU 环境、检查版本、处理 wheel 和常见环境问题    | [YOLO26/setup/YOLO26_环境安装教程.md](YOLO26/setup/YOLO26_环境安装教程.md) |
| 从创建数据集到采图、标注、训练、测试、ROS 识别和 TensorRT 导出 | [YOLO26/docs/YOLO26_采集标注训练与ROS识别教程.md](YOLO26/docs/YOLO26_采集标注训练与ROS识别教程.md) |
| 了解 YOLO26 工程目录和快速开始                               | [YOLO26/README.md](YOLO26/README.md)                         |
| 了解 ROS 2 检测包                                            | [YOLO26/ros2/yolo26_ros/README.md](YOLO26/ros2/yolo26_ros/README.md) |
| 安装和使用 ROS 2 图像采集工具                                | [collect_picture_setup/collect_picture安装与使用教程.md](collect_picture_setup/collect_picture安装与使用教程.md) |
| 安装和使用 LabelImg、自动配置 Pascal VOC XML                 | [labelimg_setup/LabelImg_安装教程.md](labelimg_setup/LabelImg_安装教程.md) |
| 查看环境安装脚本                                             | [YOLO26/setup/install_yolo26.sh](YOLO26/setup/install_yolo26.sh) |
| 查看采图安装脚本                                             | [collect_picture_setup/install_collect_picture.sh](collect_picture_setup/install_collect_picture.sh) |
| 查看 LabelImg 安装脚本                                       | [labelimg_setup/install_labelimg.sh](labelimg_setup/install_labelimg.sh) |

建议的阅读和执行顺序是：

~~~text
YOLO26/setup/YOLO26_环境安装教程.md
        -> install_yolo26.sh
        -> collect_picture_setup/collect_picture安装与使用教程.md
        -> labelimg_setup/LabelImg_安装教程.md
        -> YOLO26/docs/YOLO26_采集标注训练与ROS识别教程.md
~~~

## 常见问题

### /image_raw 不存在或没有数据

先确认相机发布节点已经启动，再在同一 ROS 2 工作空间环境下检查：

~~~bash
source /opt/ros/humble/setup.bash
source "$HOME/ros2_ws/install/setup.bash"
ros2 topic list | rg 'image_raw|camera'
ros2 topic info /image_raw --verbose
ros2 topic hz /image_raw
~~~

如果实际话题不是 /image_raw，要么让相机节点统一发布 /image_raw，要么分别通过 COLLECT_PICTURE_CAMERA_TOPIC 和 image_topic:=... 指定真实话题。

### GUI 提示无法连接显示器

采图和 LabelImg 的安装器可以在无显示器环境中执行离屏验证，但实际打开窗口必须位于桌面、VNC 或 NoMachine 会话中：

~~~bash
echo "$DISPLAY"
~~~

如果为空，请切换到图形会话后再启动 run_collect_picture.sh 或 run_labelimg.sh。

### ROS 节点找不到 ultralytics 或模型

新终端必须按顺序加载 ROS 2、YOLO26 虚拟环境和工作空间：

~~~bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT="$HOME/ros2_ws/src/YOLO26"
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source "$HOME/ros2_ws/install/setup.bash"
~~~

然后检查：

~~~bash
echo "$YOLO26_PYTHON"
python -c 'import torch, ultralytics; print(torch.__version__); print(ultralytics.__version__)'
test -f "$YOLO26_ROOT/models/pretrained/yolo26n.pt"
~~~

### 安装失败

先查看对应安装器生成的最新日志，不要使用未经验证的 sudo pip 或 pip --user 混装依赖：

~~~bash
tail -n 100 "$(ls -t "$YOLO26_ROOT/setup/logs/"install-*.log | head -n 1)"
tail -n 100 "$(ls -t "$HOME/Downloads/collect_picture_setup/logs/"install-*.log | head -n 1)"
tail -n 100 "$(ls -t "$HOME/Downloads/labelimg_setup/logs/"install-*.log | head -n 1)"
~~~

YOLO26 安装器默认需要网络访问 APT 和 Python 软件源；PyTorch 等 Jetson 专用 wheel 在项目中提供，但其余依赖仍可能从镜像或 PyPI 获取。

### 训练显存不足或共享内存不足

训练前关闭相机、采图、LabelImg、rqt 和其他图形程序；保持 batch 1，将 imgsz 从 640 调整为 512，并确保导出、离线测试和 ROS 推理使用同一个输入尺寸。

### engine 在另一台 Jetson 上无法加载

这是 TensorRT engine 的平台绑定特性。保留原始 best.pt，在目标 Jetson 上重新运行环境验证、导出和离线测试，不要只复制 engine 后跳过验证。

## 第三方组件说明

labelimg/ 目录保留了 LabelImg 的源码、资源和 LICENSE。第三方组件的使用、再分发和修改请以各目录中的许可证及其上游项目要求为准；本项目中的安装脚本只负责把随仓库提供的源码和依赖部署到目标系统。

## License

本仓库中的各组件可能具有不同的许可证。使用或再分发前，请分别阅读 labelimg/LICENSE 以及相关依赖和模型的许可证说明。
