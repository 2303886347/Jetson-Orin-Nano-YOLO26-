# YOLO26 通用目标检测与 ROS 2 工程

本目录是一套可整体迁移的 YOLO26 自定义目标检测工程，支持任意单类别、多类别、
一张图片中的多个目标，以及后续增加图片或类别后继续训练新模型版本。

推荐安装位置：

```text
/home/ubuntu/ros2_ws/src/YOLO26
```

工程不附带用户数据集、训练结果、Python 虚拟环境或大型 wheel。保留的
`models/pretrained/yolo26n.pt` 是通用 COCO 预训练模型，用于迁移学习和验证环境。

## 目录

```text
YOLO26/
├── datasets/                 # 用户通过工具创建自己的数据集
├── docs/                     # 完整采集、标注、训练与 ROS 教程
├── models/pretrained/        # 通用预训练模型
├── models/deployed/          # 导出的 engine/ONNX/OpenVINO 模型
├── ros2/yolo26_ros/          # ROS 2 检测包
├── runs/                     # 训练和离线推理输出
├── setup/                    # Jetson 环境安装与激活材料
├── tests/
└── tools/
```

## 快速开始

新终端先加载环境：

```bash
export YOLO26_ROOT=/home/ubuntu/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"
```

创建单类别数据集：

下面的 `my_dataset` 只是教程示例名。执行命令前，请替换为实际使用的数据集目录名；
后续所有命令都要继续使用同一个名称。

```bash
export YOLO26_ROOT=/home/ubuntu/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

python tools/create_dataset.py \
  --name my_dataset \
  --classes target_a
```

创建多类别数据集：

下面的 `my_dataset` 只是教程示例名。执行命令前，请替换为实际使用的数据集目录名；
后续所有命令都要继续使用同一个名称。

```bash
export YOLO26_ROOT=/home/ubuntu/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

python tools/create_dataset.py \
  --name my_dataset \
  --classes target_a target_b target_c
```

采集 JPG 并保存 Pascal VOC XML 后，首次转换：

下面的 `my_dataset` 只是教程示例名。执行命令前，请替换为实际使用的数据集目录名；
后续所有命令都要继续使用同一个名称。

```bash
export YOLO26_ROOT=/home/ubuntu/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

python tools/prepare_dataset.py \
  --dataset datasets/my_dataset \
  --train-ratio 0.8 --val-ratio 0.1 --test-ratio 0.1 \
  --seed 42 --normalize-xml-paths
```

后续增加图片或类别时，保留旧数据并使用 `--extend-splits`。训练脚本要求显式给出
数据和运行版本名，避免误训练错误的数据集。

完整教程：

```text
docs/YOLO26_采集标注训练与ROS识别教程.md
setup/YOLO26_环境安装教程.md
```
