# YOLO26 通用采集、标注、训练与 ROS 识别教程

本教程用于训练任意单类别或多类别目标检测模型，不限定目标名称。用户可以先训练一个
类别，后续继续增加同类数据，也可以在保持已有类别 ID 不变的情况下追加新类别。

## 1. 完整工作流

```text
Camera_USB_and_CSI 发布 /image_raw
        ↓
collect_picture 采集 JPG
        ↓
LabelImg 保存 Pascal VOC XML
        ↓
prepare_dataset.py 校验并转换为 YOLO 格式
        ↓
train_yolo26.py 训练版本化 best.pt
        ↓
离线图片测试 → ROS PT 实时识别 → TensorRT engine 实时识别
```

最终工程位置：

```text
$HOME/ros2_ws/src/YOLO26
```

数据集结构：

```text
datasets/<dataset_name>/
├── source/
│   ├── JPEGImages/          # 原始 JPG
│   ├── Annotations/         # Pascal VOC XML
│   ├── ImageSets/           # 固定的 train/val/test 清单
│   └── classes.names        # 类别名称，一行一个，顺序就是类别 ID
└── yolo/                    # 工具生成，不要手工修改
    ├── images/{train,val,test}/
    ├── labels/{train,val,test}/
    ├── data.yaml
    └── dataset_report.json
```

只维护 `source`。需要更改数据或标注时，修改 JPG、XML、`classes.names`，再重新运行
转换工具。不要手工修改 `yolo/` 中的文件。

## 2. 新终端必须加载环境

`source` 只在当前终端生效。新开终端、标签页或 SSH 会话后必须重新执行。

仅训练、转换或离线推理：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"
```

运行 ROS 2：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source $HOME/ros2_ws/install/setup.bash
```

运行相机但不运行 YOLO：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash
```

后续命令块均补齐自身需要的环境，可以在新终端中独立执行。

## 3. 迁移、安装和编译

在教程同一文件夹下的 **“资源文件”** 文件夹中找到 `YOLO26`，使用 MobaXterm
将完整文件夹传入 Jetson 的 `~/ros2_ws/src/` 目录。先确认用户主目录并补建
工作空间源码目录：

```bash
echo "$HOME"
mkdir -p "$HOME/ros2_ws/src"
test ! -e "$HOME/ros2_ws/src/YOLO26"
```

如果已经存在同名目录，先核对版本，不要混合覆盖。传入完成后执行：

```bash
test -f "$HOME/ros2_ws/src/YOLO26/ros2/yolo26_ros/package.xml"
test -f "$HOME/ros2_ws/src/YOLO26/setup/wheels/torch-2.7.0-cp310-cp310-linux_aarch64.whl"
```

环境尚未安装时，先按下面教程安装：

```text
$HOME/ros2_ws/src/YOLO26/setup/YOLO26_环境安装教程.md
```

编译 Camera 和 YOLO26 ROS 包：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"

cd $HOME/ros2_ws
colcon list | grep -E 'camera_usb_and_csi|yolo26_ros'
colcon build --symlink-install \
  --packages-select camera_usb_and_csi yolo26_ros
source $HOME/ros2_ws/install/setup.bash

ros2 pkg prefix yolo26_ros
ros2 pkg executables yolo26_ros
```

## 4. 创建自己的数据集

数据集名建议使用小写字母、数字、下划线或连字符。本教程使用通用示例名
`my_dataset`，实际使用时应改为能描述任务的名称。

### 4.1 单类别

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
python tools/create_dataset.py \
  --name "$DATASET_NAME" \
  --classes target_a
```

### 4.2 多类别

如果第一版就需要识别多个类别，比如target_a，target_b，target_c三种，那么在创建时按固定顺序列出：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
python tools/create_dataset.py \
  --name "$DATASET_NAME" \
  --classes target_a target_b target_c
```




确认类别 ID：
```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
nl -ba "datasets/$DATASET_NAME/source/classes.names"
```

第一行类别 ID 为 0，第二行为 1。开始训练后不能重新排序、删除或重命名已有类别；后期
增加类别只能追加到文件末尾。

## 5. 启动相机并采集 JPG

Camera 包默认发布 `/image_raw`。同一时间只启动 CSI 或 USB 中的一个。

首次使用采集软件时，在教程同一文件夹下的 **“资源文件”** 文件夹中找到
`collect_picture` 和 `collect_picture_setup`，使用 MobaXterm 将两个完整文件夹
传入 `~/Downloads/`，再按照
**$HOME/Downloads/collect_picture_setup/collect_picture安装与使用教程.md**
完成安装。两个文件夹的名称和内部结构必须保持不变。

终端 A 启动 CSI：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash

ros2 launch camera_usb_and_csi camera.launch.py camera_type:=CSI
```

或者启动 USB：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash

ros2 launch camera_usb_and_csi camera.launch.py \
  camera_type:=USB usb_device:=/dev/usb_cam
```

终端 B 检查图像话题：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash

ros2 topic info /image_raw
ros2 topic hz /image_raw
```

终端 B 启动采集软件：

```bash
source /opt/ros/humble/setup.bash
source $HOME/ros2_ws/install/setup.bash

$HOME/Software/collect_picture/run_collect_picture.sh
```

在采集软件的“保存路径”选择：

```text
$HOME/ros2_ws/src/YOLO26/datasets/my_dataset/source
```

软件会将图片写入 `source/JPEGImages`。采集时应主动覆盖不同背景、距离、角度、光照、
遮挡、目标尺寸和无目标画面。连续帧高度相似时不要全部保留，否则验证结果会虚高，
真实画面仍可能识别不到。

完成采集后按 `Ctrl+C` 停止相机，避免相机被后续程序重复占用。

## 6. 使用 LabelImg 标注 Pascal VOC XML

首次使用 LabelImg 时，在教程同一文件夹下的 **“资源文件”** 文件夹中找到
`labelimg` 和 `labelimg_setup`，使用 MobaXterm 将两个完整文件夹传入
`~/Downloads/`，再按照 **$HOME/Downloads/labelimg_setup/LabelImg_安装教程.md**
完成安装。两个文件夹的名称和内部结构必须保持不变。

启动 LabelImg：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
$HOME/Software/labelimg/run_labelimg.sh \
  "$YOLO26_ROOT/datasets/$DATASET_NAME/source/JPEGImages"
```

启动器会自动读取 `source/classes.names`，把 XML 保存到 `source/Annotations`，并强制
使用 `PascalVOC`。正常情况下不会弹出图片目录或标注目录选择窗口。如果命令提示路径
不存在，应先检查 `DATASET_NAME`，不要在弹窗中改选其他目录。

在界面中：

1. 确认页眉格式显示 `PascalVOC`。
2. 确认状态栏保存目录为当前数据集的 `source/Annotations`，无需再次选择。
3. 类别名来自当前数据集的 `classes.names`。
4. 一张图片可以包含多个框，也可以同时包含多个不同类别。
5. 图片中所有已声明且可见的目标都要标注，不能只标其中一个。
6. 每张正样本保存后，确认 `Annotations` 中出现同名 XML。

检查图片和 XML 数量：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
find "datasets/$DATASET_NAME/source/JPEGImages" -maxdepth 1 -type f -iname '*.jpg' | wc -l
find "datasets/$DATASET_NAME/source/Annotations" -maxdepth 1 -type f -iname '*.xml' | wc -l
```

不含任何目标类别的图片可以作为负样本，不创建 XML；但只有确认标注完成的无目标图片
才能这样处理。漏标图片不能冒充负样本。

## 7. 首次校验、切分和转换

首次转换会使用固定随机种子生成 train、val、test。通常只执行一次：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
python tools/prepare_dataset.py \
  --dataset "datasets/$DATASET_NAME" \
  --train-ratio 0.8 --val-ratio 0.1 --test-ratio 0.1 \
  --seed 42 --normalize-xml-paths
```

如果数据中包含已经确认的无 XML 负样本，显式增加参数：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
python tools/prepare_dataset.py \
  --dataset "datasets/$DATASET_NAME" \
  --train-ratio 0.8 --val-ratio 0.1 --test-ratio 0.1 \
  --seed 42 --normalize-xml-paths \
  --allow-unannotated-negatives
```

工具默认拒绝缺图、未知类别、非法尺寸、越界框、重复文件和未明确允许的无 XML 图片。
`--normalize-xml-paths` 只删除 XML 中失效的绝对 `<path>` 字段，不改变类别、图片尺寸
或边界框。

查看报告：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
cat "datasets/$DATASET_NAME/yolo/dataset_report.json"
cat "datasets/$DATASET_NAME/yolo/data.yaml"
```

确认 train、val、test 数量合理，并确认每个需要训练的类别在 train 中都有目标。10 张
图片通常只能验证流程，不能说明模型具备实际泛化能力。

## 8. 手动训练第一版模型

训练前先停止 Camera、collect_picture、LabelImg、rqt 和其他使用 GPU 或持续占用
内存的程序。Jetson 使用 CPU/GPU 共享内存，相机和桌面程序的占用会直接减少
可用训练内存。

先做 10 epoch 冒烟训练，确认环境、标签和输出路径正常：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
RUN_NAME=${DATASET_NAME}_v1_smoke
python tools/train_yolo26.py \
  --model models/pretrained/yolo26n.pt \
  --data "datasets/$DATASET_NAME/yolo/data.yaml" \
  --name "$RUN_NAME" \
  --imgsz 640 --batch 1 --epochs 10 \
  --device 0 --workers 1 --seed 42
```

冒烟训练成功后，使用新的运行名进行正式训练，不覆盖冒烟输出：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
RUN_NAME=${DATASET_NAME}_v1
python tools/train_yolo26.py \
  --model models/pretrained/yolo26n.pt \
  --data "datasets/$DATASET_NAME/yolo/data.yaml" \
  --name "$RUN_NAME" \
  --imgsz 640 --batch 1 --epochs 100 \
  --device 0 --workers 1 --seed 42 --patience 20
```

8 GB Jetson 建议保持 `--batch 1`。如果仍出现 `NvMapMemAlloc error 12`、
`CUDA out of memory` 或 `CUDACachingAllocator` 错误，先确认相机和图形程序已停止，
再将 `--imgsz 640` 降为 `--imgsz 512`。不要为了节省显存关闭 AMP，FP32 通常
会占用更多内存。训练输出位于：

```text
runs/<run_name>/weights/best.pt
runs/<run_name>/weights/last.pt
runs/<run_name>/results.csv
runs/<run_name>/confusion_matrix.png
```

训练工具默认开启 CUDA AMP，并会从
`models/pretrained/yolo26n.pt` 完成 AMP 自检。模型路径应保持为上述规范路径，
不需要将模型复制到工程根目录。如果 GPU 或 PyTorch 环境明确不支持 AMP，可在
训练指令末尾添加 `--amp false`；这会改用 FP32 训练，速度和显存占用可能增加。

## 9. 离线测试 best.pt

必须先在未参与训练的 test 图片上验证：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
RUN_NAME=${DATASET_NAME}_v1
python tools/predict_yolo26.py \
  --model "runs/$RUN_NAME/weights/best.pt" \
  --source "datasets/$DATASET_NAME/yolo/images/test" \
  --name "${RUN_NAME}_test" \
  --conf 0.25 --iou 0.45 --device 0
```

结果在 `runs/predict/<predict_name>`。如果完全没有框，依次检查：

1. XML 类别是否与 `classes.names` 完全一致。
2. 目标框是否正确包住目标，是否存在大量漏标。
3. `dataset_report.json` 中各类别在 train、val、test 的数量。
4. 临时将 `--conf` 调到 `0.05`，判断是置信度偏低还是完全没有学到。
5. 测试图片是否与训练图片过于不同。
6. 是否只有少量近似连续帧；这种数据通常无法形成稳定模型。

不要用降低置信度代替补充数据。正式数据应按采集场次隔离，避免同一段视频的近似帧
同时进入训练和测试。

## 10. 使用 PT 模型进行 ROS 实时识别

一个 launch 同时启动相机、检测节点和 rqt。CSI：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source $HOME/ros2_ws/install/setup.bash

RUN_NAME=my_dataset_v1
MODEL_PATH="$YOLO26_ROOT/runs/$RUN_NAME/weights/best.pt"
ros2 launch yolo26_ros camera_detector.launch.py \
  camera_type:=CSI \
  model_path:="$MODEL_PATH" \
  show_rqt:=true
```

USB：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source $HOME/ros2_ws/install/setup.bash

RUN_NAME=my_dataset_v1
MODEL_PATH="$YOLO26_ROOT/runs/$RUN_NAME/weights/best.pt"
ros2 launch yolo26_ros camera_detector.launch.py \
  camera_type:=USB usb_device:=/dev/usb_cam \
  model_path:="$MODEL_PATH" \
  show_rqt:=true
```



如果相机已由其他终端启动，只启动检测节点：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source $HOME/ros2_ws/install/setup.bash

RUN_NAME=my_dataset_v1
MODEL_PATH="$YOLO26_ROOT/runs/$RUN_NAME/weights/best.pt"
ros2 launch yolo26_ros detector.launch.py \
  image_topic:=/image_raw \
  model_path:="$MODEL_PATH" \
  show_rqt:=true
```

公共接口：

```text
输入图像：/image_raw
带框图像：/yolo26/annotated_image
检测消息：/yolo26/detections
启动推理：/yolo26/start
停止推理：/yolo26/stop
```

检查检测结果：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source $HOME/ros2_ws/install/setup.bash

ros2 topic echo --once /yolo26/detections
```

## 11. 增加同类数据并训练下一版

第一版效果不理想时，应保留全部已有 JPG/XML，继续把新图片和新 XML 加入同一个
`source`。不要只用新增图片训练，否则模型可能遗忘已有场景。

新数据标注完成后保持已有切分，只有新样本被分配：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
python tools/prepare_dataset.py \
  --dataset "datasets/$DATASET_NAME" \
  --train-ratio 0.8 --val-ratio 0.1 --test-ratio 0.1 \
  --seed 42 --extend-splits --normalize-xml-paths
```

从上一版 `best.pt` 训练新版本：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
PREVIOUS_RUN=${DATASET_NAME}_v1
NEW_RUN=${DATASET_NAME}_v2
python tools/train_yolo26.py \
  --model "runs/$PREVIOUS_RUN/weights/best.pt" \
  --data "datasets/$DATASET_NAME/yolo/data.yaml" \
  --name "$NEW_RUN" \
  --imgsz 640 --batch 1 --epochs 100 \
  --device 0 --workers 1 --seed 42 --patience 20
```

以后继续使用 `v2 → v3`。每一版都重新执行离线测试和真实相机测试，不覆盖已有结果。

## 12. 后期增加新类别

假设已有 `target_a`，下一版需要增加 `target_b` 和 `target_c`。使用工具追加，原类别
顺序和 ID 不变：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
python tools/create_dataset.py \
  --name "$DATASET_NAME" \
  --add-classes target_b target_c
nl -ba "datasets/$DATASET_NAME/source/classes.names"
```

然后必须完成以下工作：

1. 采集并标注包含新类别的图片。
2. 回看已有图片，已有图片中出现新类别时补标。
3. 确保每张图片中所有已声明类别都完整标注。
4. 使用 `--extend-splits` 重新生成 YOLO 数据。
5. 检查报告中每个新类别在 train 中都有实例。
6. 从上一版 `best.pt` 训练新的版本名。

转换前先确认新类别已经保存到 XML。下面的 `NEW_CLASS` 必须与
`classes.names` 中的新类别完全一致：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

DATASET_NAME=my_dataset
NEW_CLASS=target_b
grep -rl --include='*.xml' "<name>${NEW_CLASS}</name>" \
  "datasets/$DATASET_NAME/source/Annotations" | wc -l
```

结果必须大于 0。如果结果为 0，不要运行转换或训练；先采集包含新类别
的图片，用 LabelImg 选择新类别画框并保存 XML。建议为每个新类别准备多个
不同背景、角度和距离的实例，不要只使用一张图片。

转换命令：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
python tools/prepare_dataset.py \
  --dataset "datasets/$DATASET_NAME" \
  --train-ratio 0.8 --val-ratio 0.1 --test-ratio 0.1 \
  --seed 42 --extend-splits --normalize-xml-paths
```

训练命令与第 11 节相同。Ultralytics 会使用上一版模型的可迁移权重，并根据新数据集类别
数量构建新的检测头。

## 13. 导出 TensorRT engine

只有 PT 离线和 ROS 实时结果都正确后，才导出 engine。engine 与导出机器的 Jetson、
TensorRT 和 CUDA 环境相关，不建议跨平台复制。

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

RUN_NAME=my_dataset_v1
ENGINE_NAME=${RUN_NAME}.engine
python tools/export_yolo26.py \
  --model "runs/$RUN_NAME/weights/best.pt" \
  --format engine \
  --output "models/deployed/$ENGINE_NAME" \
  --imgsz 640 --device 0 --half
```

使用 engine 离线测试：

```bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
cd "$YOLO26_ROOT"

# 注意：my_dataset 只是教程示例名。请替换为实际创建的数据集目录名，后续命令保持一致。
DATASET_NAME=my_dataset
RUN_NAME=${DATASET_NAME}_v1
python tools/predict_yolo26.py \
  --model "models/deployed/${RUN_NAME}.engine" \
  --source "datasets/$DATASET_NAME/yolo/images/test" \
  --name "${RUN_NAME}_engine_test" \
  --conf 0.25 --device 0
```

使用 engine 启动 USB 实时识别：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source $HOME/ros2_ws/install/setup.bash

RUN_NAME=my_dataset_v1
ENGINE_PATH="$YOLO26_ROOT/models/deployed/${RUN_NAME}.engine"
ros2 launch yolo26_ros camera_detector.launch.py \
  camera_type:=USB usb_device:=/dev/usb_cam \
  model_path:="$ENGINE_PATH" show_rqt:=true
```

使用 engine 启动 CSI 实时识别：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source $HOME/ros2_ws/install/setup.bash

RUN_NAME=my_dataset_v1
ENGINE_PATH="$YOLO26_ROOT/models/deployed/${RUN_NAME}.engine"
ros2 launch yolo26_ros camera_detector.launch.py \
  camera_type:=CSI \
  model_path:="$ENGINE_PATH" \
  show_rqt:=true
```

如果相机已经由其他终端启动，只使用 engine 启动检测节点：

```bash
source /opt/ros/humble/setup.bash
export YOLO26_ROOT=$HOME/ros2_ws/src/YOLO26
source "$YOLO26_ROOT/setup/activate_yolo26.sh"
source $HOME/ros2_ws/install/setup.bash

RUN_NAME=my_dataset_v1
ENGINE_PATH="$YOLO26_ROOT/models/deployed/${RUN_NAME}.engine"
ros2 launch yolo26_ros detector.launch.py \
  image_topic:=/image_raw \
  model_path:="$ENGINE_PATH" \
  show_rqt:=true
```

## 14. 最终检查清单

- `classes.names` 中类别唯一、顺序稳定，XML 类别完全一致。
- 正样本 JPG 与 XML 同名，负样本经过明确确认。
- train、val、test 不混入同一采集序列的近似帧。
- `dataset_report.json` 中每个类别在 train 中都有足够实例。
- 每轮训练使用新运行名，已有 `best.pt` 和结果得到保留。
- 先验证 test 图片，再验证真实 `/image_raw`，最后导出 engine。
- 新终端在运行命令前重新执行对应 `source`。
